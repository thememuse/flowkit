"""Background worker — processes pending requests via Chrome extension.

Workflow audit:
- W5 (image gen): sync — API returns result immediately → extract mediaGenId + imageUri
- W6 (video gen): async — API returns operations[] → must poll check_video_status until done
- W7 (video chain): same as W6 but with endImage in payload
- W8 (upscale): async — same as video, returns operations[] → poll
- W9 (status poll): poll_operation() handles this for W6/W7/W8
- W11 (retry): on error, increment retry_count, re-queue as PENDING
"""
import asyncio
import json
import logging
from agent.db import crud
from agent.services.flow_client import get_flow_client
from agent.config import POLL_INTERVAL, MAX_RETRIES, VIDEO_POLL_TIMEOUT

logger = logging.getLogger(__name__)


async def process_pending_requests():
    """Main worker loop."""
    client = get_flow_client()

    while True:
        try:
            if not client.connected:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            pending = await crud.list_pending_requests()
            for req in pending:
                await _process_one(client, req)
        except Exception as e:
            logger.exception("Worker loop error: %s", e)

        await asyncio.sleep(POLL_INTERVAL)


async def _process_one(client, req: dict):
    """Process a single request."""
    rid = req["id"]
    req_type = req["type"]
    orientation = req.get("orientation", "VERTICAL")

    logger.info("Processing request %s type=%s", rid[:8], req_type)
    await crud.update_request(rid, status="PROCESSING")

    try:
        if req_type == "GENERATE_IMAGES":
            result = await _handle_generate_image(client, req, orientation)
        elif req_type == "GENERATE_VIDEO":
            result = await _handle_generate_video(client, req, orientation)
        elif req_type == "UPSCALE_VIDEO":
            result = await _handle_upscale_video(client, req, orientation)
        elif req_type == "GENERATE_CHARACTER_IMAGE":
            result = await _handle_generate_character_image(client, req)
        else:
            result = {"error": f"Unknown request type: {req_type}"}

        if _is_error(result):
            await _handle_failure(rid, req, result)
        else:
            media_gen_id = _extract_media_gen_id(result, req_type)
            output_url = _extract_output_url(result, req_type)
            await crud.update_request(rid, status="COMPLETED", media_gen_id=media_gen_id, output_url=output_url)
            await _update_scene_from_result(req, orientation, media_gen_id, output_url)
            logger.info("Request %s COMPLETED: media=%s", rid[:8], media_gen_id[:20] if media_gen_id else "?")

    except Exception as e:
        logger.exception("Request %s exception: %s", rid[:8], e)
        await _handle_failure(rid, req, {"error": str(e)})


async def _handle_failure(rid: str, req: dict, result: dict):
    """Handle request failure with retry logic."""
    error_msg = result.get("error") or result.get("data", {}).get("error", {}).get("message", "Unknown error")
    if isinstance(error_msg, dict):
        error_msg = json.dumps(error_msg)[:200]

    retry = req.get("retry_count", 0) + 1
    if retry < MAX_RETRIES:
        # Back to PENDING for retry
        await crud.update_request(rid, status="PENDING", retry_count=retry, error_message=str(error_msg))
        logger.warning("Request %s failed (retry %d/%d): %s", rid[:8], retry, MAX_RETRIES, error_msg)
    else:
        await crud.update_request(rid, status="FAILED", error_message=str(error_msg))
        # Also mark scene status as FAILED
        await _mark_scene_failed(req)
        logger.error("Request %s FAILED permanently: %s", rid[:8], error_msg)


async def _mark_scene_failed(req: dict):
    """Mark the relevant scene field as FAILED."""
    scene_id = req.get("scene_id")
    if not scene_id:
        return
    orientation = req.get("orientation", "VERTICAL")
    prefix = "vertical" if orientation == "VERTICAL" else "horizontal"
    req_type = req["type"]
    updates = {}
    if req_type == "GENERATE_IMAGES":
        updates[f"{prefix}_image_status"] = "FAILED"
    elif req_type == "GENERATE_VIDEO":
        updates[f"{prefix}_video_status"] = "FAILED"
    elif req_type == "UPSCALE_VIDEO":
        updates[f"{prefix}_upscale_status"] = "FAILED"
    if updates:
        await crud.update_scene(scene_id, **updates)


# ─── Error Detection ────────────────────────────────────────

def _is_error(result: dict) -> bool:
    if result.get("error"):
        return True
    status = result.get("status")
    if isinstance(status, int) and status >= 400:
        return True
    # Check nested error in data
    data = result.get("data", {})
    if isinstance(data, dict) and data.get("error"):
        return True
    return False


# ─── Response Parsing ────────────────────────────────────────

def _extract_media_gen_id(result: dict, req_type: str) -> str:
    data = result.get("data", result)

    if req_type == "GENERATE_IMAGES":
        # batchGenerateImages → data.media[].image.generatedImage.mediaGenerationId
        media = data.get("media", [])
        if media:
            gen = media[0].get("image", {}).get("generatedImage", {})
            return gen.get("mediaGenerationId", "")

    if req_type in ("GENERATE_VIDEO", "UPSCALE_VIDEO"):
        # After polling: data.operations[].response.generatedVideos[].mediaGenerationId
        ops = data.get("operations", [])
        if ops:
            # Check if poll completed (has response)
            resp = ops[0].get("response", {})
            vids = resp.get("generatedVideos", [])
            if vids:
                return vids[0].get("mediaGenerationId", "")
            # Fallback: operation-level mediaGenerationId (pre-poll)
            return ops[0].get("mediaGenerationId", "")

    return data.get("mediaGenerationId", "")


def _extract_output_url(result: dict, req_type: str) -> str:
    data = result.get("data", result)

    if req_type == "GENERATE_IMAGES":
        media = data.get("media", [])
        if media:
            gen = media[0].get("image", {}).get("generatedImage", {})
            return gen.get("imageUri", gen.get("fifeUrl", ""))

    if req_type in ("GENERATE_VIDEO", "UPSCALE_VIDEO"):
        ops = data.get("operations", [])
        if ops:
            resp = ops[0].get("response", {})
            vids = resp.get("generatedVideos", [])
            if vids:
                return vids[0].get("videoUri", "")

    return data.get("videoUri", data.get("imageUri", ""))


def _extract_operations(result: dict) -> list[dict]:
    """Extract operations list from video gen / upscale submit response."""
    data = result.get("data", result)
    return data.get("operations", [])


# ─── W9: Video/Upscale Status Polling ────────────────────────

async def _poll_operations(client, operations: list[dict], timeout: int = VIDEO_POLL_TIMEOUT) -> dict:
    """
    Poll check_video_status until all operations are done or timeout.

    Production response format:
    {
      "operations": [
        {
          "done": true,
          "response": {
            "generatedVideos": [{"mediaGenerationId": "...", "videoUri": "..."}]
          }
        }
      ]
    }
    """
    if not operations:
        return {"error": "No operations to poll"}

    poll_interval = POLL_INTERVAL
    elapsed = 0

    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        status_result = await client.check_video_status(operations)
        if _is_error(status_result):
            logger.warning("Status poll error: %s", status_result.get("error"))
            continue

        data = status_result.get("data", status_result)
        ops = data.get("operations", [])

        if not ops:
            continue

        # Check if all operations are done
        all_done = all(op.get("done", False) for op in ops)
        if all_done:
            logger.info("All %d operations completed after %ds", len(ops), elapsed)
            return {"data": data}

        # Check for errors in individual operations
        for op in ops:
            if op.get("error"):
                error_msg = op["error"].get("message", str(op["error"]))
                logger.error("Operation error: %s", error_msg)
                return {"error": error_msg}

        logger.debug("Poll %ds/%ds: %d/%d done", elapsed, timeout,
                      sum(1 for o in ops if o.get("done")), len(ops))

    return {"error": f"Polling timeout after {timeout}s"}


# ─── W5: Image Generation (sync) ────────────────────────────

async def _handle_generate_image(client, req: dict, orientation: str) -> dict:
    scene = await crud.get_scene(req["scene_id"]) if req.get("scene_id") else None
    if not scene:
        return {"error": "Scene not found"}

    project = await crud.get_project(req["project_id"]) if req.get("project_id") else None
    aspect = "IMAGE_ASPECT_RATIO_PORTRAIT" if orientation == "VERTICAL" else "IMAGE_ASPECT_RATIO_LANDSCAPE"
    prompt = scene.get("image_prompt") or scene.get("prompt", "")
    tier = project.get("user_paygate_tier", "PAYGATE_TIER_TWO") if project else "PAYGATE_TIER_TWO"
    pid = req.get("project_id", "0")

    # Image gen is synchronous — result returned immediately
    return await client.generate_images(prompt=prompt, project_id=pid, aspect_ratio=aspect, user_paygate_tier=tier)


# ─── W6/W7: Video Generation (async — needs polling) ────────

async def _handle_generate_video(client, req: dict, orientation: str) -> dict:
    scene = await crud.get_scene(req["scene_id"]) if req.get("scene_id") else None
    if not scene:
        return {"error": "Scene not found"}

    prefix = "vertical" if orientation == "VERTICAL" else "horizontal"
    image_media_id = scene.get(f"{prefix}_image_media_gen_id")
    if not image_media_id:
        return {"error": f"No {prefix} image media_gen_id for scene"}

    project = await crud.get_project(req["project_id"]) if req.get("project_id") else None
    aspect = "VIDEO_ASPECT_RATIO_PORTRAIT" if orientation == "VERTICAL" else "VIDEO_ASPECT_RATIO_LANDSCAPE"
    prompt = scene.get("video_prompt") or scene.get("prompt", "")
    tier = project.get("user_paygate_tier", "PAYGATE_TIER_TWO") if project else "PAYGATE_TIER_TWO"
    end_id = scene.get(f"{prefix}_end_scene_media_gen_id")

    # Step 1: Submit video generation
    submit_result = await client.generate_video(
        start_image_media_id=image_media_id,
        prompt=prompt,
        project_id=req.get("project_id", "0"),
        scene_id=req.get("scene_id", ""),
        aspect_ratio=aspect,
        end_image_media_id=end_id,
        user_paygate_tier=tier,
    )

    if _is_error(submit_result):
        return submit_result

    # Step 2: Extract operations and poll for completion
    operations = _extract_operations(submit_result)
    if not operations:
        return {"error": "Video gen returned no operations"}

    # Store operation name for tracking
    op_name = operations[0].get("name", "")
    await crud.update_request(req["id"], request_id=op_name)

    logger.info("Video gen submitted, polling %d operations...", len(operations))
    return await _poll_operations(client, operations)


# ─── W8: Upscale Video (async — needs polling) ──────────────

async def _handle_upscale_video(client, req: dict, orientation: str) -> dict:
    scene = await crud.get_scene(req["scene_id"]) if req.get("scene_id") else None
    if not scene:
        return {"error": "Scene not found"}

    prefix = "vertical" if orientation == "VERTICAL" else "horizontal"
    video_media_id = scene.get(f"{prefix}_video_media_gen_id")
    if not video_media_id:
        return {"error": f"No {prefix} video media_gen_id for scene"}

    aspect = "VIDEO_ASPECT_RATIO_PORTRAIT" if orientation == "VERTICAL" else "VIDEO_ASPECT_RATIO_LANDSCAPE"

    # Step 1: Submit upscale
    submit_result = await client.upscale_video(
        media_gen_id=video_media_id,
        scene_id=req.get("scene_id", ""),
        aspect_ratio=aspect,
    )

    if _is_error(submit_result):
        return submit_result

    # Step 2: Poll for completion
    operations = _extract_operations(submit_result)
    if not operations:
        return {"error": "Upscale returned no operations"}

    op_name = operations[0].get("name", "")
    await crud.update_request(req["id"], request_id=op_name)

    logger.info("Upscale submitted, polling %d operations...", len(operations))
    return await _poll_operations(client, operations, timeout=300)


# ─── Character Image (sync, like W5) ────────────────────────

async def _handle_generate_character_image(client, req: dict) -> dict:
    char = await crud.get_character(req["character_id"]) if req.get("character_id") else None
    if not char:
        return {"error": "Character not found"}

    pid = req.get("project_id", "0")
    result = await client.generate_images(
        prompt=f"Character reference: {char['name']}. {char.get('description', '')}",
        project_id=pid,
        aspect_ratio="IMAGE_ASPECT_RATIO_PORTRAIT",
    )

    if not _is_error(result):
        media_gen_id = _extract_media_gen_id(result, "GENERATE_IMAGES")
        output_url = _extract_output_url(result, "GENERATE_IMAGES")
        if media_gen_id:
            await crud.update_character(char["id"], media_gen_id=media_gen_id, reference_image_url=output_url)

    return result


# ─── Scene Update ────────────────────────────────────────────

async def _update_scene_from_result(req: dict, orientation: str, media_gen_id: str, output_url: str):
    """Update scene fields based on completed request."""
    scene_id = req.get("scene_id")
    if not scene_id:
        return

    prefix = "vertical" if orientation == "VERTICAL" else "horizontal"
    req_type = req["type"]
    updates = {}

    if req_type == "GENERATE_IMAGES":
        updates[f"{prefix}_image_media_gen_id"] = media_gen_id
        updates[f"{prefix}_image_url"] = output_url
        updates[f"{prefix}_image_status"] = "COMPLETED"
    elif req_type == "GENERATE_VIDEO":
        updates[f"{prefix}_video_media_gen_id"] = media_gen_id
        updates[f"{prefix}_video_url"] = output_url
        updates[f"{prefix}_video_status"] = "COMPLETED"
    elif req_type == "UPSCALE_VIDEO":
        updates[f"{prefix}_upscale_media_gen_id"] = media_gen_id
        updates[f"{prefix}_upscale_url"] = output_url
        updates[f"{prefix}_upscale_status"] = "COMPLETED"

    if updates:
        await crud.update_scene(scene_id, **updates)
