"""Background worker — processes pending requests via Chrome extension."""
import asyncio
import json
import logging
from agent.db import crud
from agent.services.flow_client import get_flow_client
from agent.config import POLL_INTERVAL, MAX_RETRIES

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
            error_msg = result.get("error", "Unknown error")
            retry = req.get("retry_count", 0) + 1
            if retry < MAX_RETRIES:
                await crud.update_request(rid, status="PENDING", retry_count=retry, error_message=error_msg)
                logger.warning("Request %s failed (retry %d/%d): %s", rid[:8], retry, MAX_RETRIES, error_msg)
            else:
                await crud.update_request(rid, status="FAILED", error_message=error_msg)
                logger.error("Request %s FAILED permanently: %s", rid[:8], error_msg)
        else:
            media_gen_id = _extract_media_gen_id(result, req_type)
            output_url = _extract_output_url(result, req_type)
            await crud.update_request(rid, status="COMPLETED", media_gen_id=media_gen_id, output_url=output_url)
            await _update_scene_from_result(req, orientation, media_gen_id, output_url)
            logger.info("Request %s COMPLETED", rid[:8])

    except Exception as e:
        logger.exception("Request %s exception: %s", rid[:8], e)
        await crud.update_request(rid, status="FAILED", error_message=str(e))


def _is_error(result: dict) -> bool:
    if result.get("error"):
        return True
    status = result.get("status")
    if isinstance(status, int) and status >= 400:
        return True
    return False


def _extract_media_gen_id(result: dict, req_type: str) -> str:
    data = result.get("data", result)

    if req_type == "GENERATE_IMAGES":
        # batchGenerateImages response
        media = data.get("media", [])
        if media:
            gen = media[0].get("image", {}).get("generatedImage", {})
            return gen.get("mediaGenerationId", "")

    if req_type in ("GENERATE_VIDEO", "UPSCALE_VIDEO"):
        ops = data.get("operations", [])
        if ops:
            return ops[0].get("mediaGenerationId", "")

    return data.get("mediaGenerationId", "")


def _extract_output_url(result: dict, req_type: str) -> str:
    data = result.get("data", result)

    if req_type == "GENERATE_IMAGES":
        media = data.get("media", [])
        if media:
            gen = media[0].get("image", {}).get("generatedImage", {})
            return gen.get("imageUri", gen.get("fifeUrl", ""))

    return data.get("videoUri", data.get("imageUri", ""))


async def _handle_generate_image(client, req: dict, orientation: str) -> dict:
    scene = await crud.get_scene(req["scene_id"]) if req.get("scene_id") else None
    if not scene:
        return {"error": "Scene not found"}

    project = await crud.get_project(req["project_id"]) if req.get("project_id") else None
    aspect = "IMAGE_ASPECT_RATIO_PORTRAIT" if orientation == "VERTICAL" else "IMAGE_ASPECT_RATIO_LANDSCAPE"
    prompt = scene.get("image_prompt") or scene.get("prompt", "")
    tier = project.get("user_paygate_tier", "PAYGATE_TIER_TWO") if project else "PAYGATE_TIER_TWO"
    pid = req.get("project_id", "0")

    return await client.generate_images(prompt=prompt, project_id=pid, aspect_ratio=aspect, user_paygate_tier=tier)


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

    return await client.generate_video(
        start_image_media_id=image_media_id,
        prompt=prompt,
        project_id=req.get("project_id", "0"),
        scene_id=req.get("scene_id", ""),
        aspect_ratio=aspect,
        end_image_media_id=end_id,
        user_paygate_tier=tier,
    )


async def _handle_upscale_video(client, req: dict, orientation: str) -> dict:
    scene = await crud.get_scene(req["scene_id"]) if req.get("scene_id") else None
    if not scene:
        return {"error": "Scene not found"}

    prefix = "vertical" if orientation == "VERTICAL" else "horizontal"
    video_media_id = scene.get(f"{prefix}_video_media_gen_id")
    if not video_media_id:
        return {"error": f"No {prefix} video media_gen_id for scene"}

    aspect = "VIDEO_ASPECT_RATIO_PORTRAIT" if orientation == "VERTICAL" else "VIDEO_ASPECT_RATIO_LANDSCAPE"

    return await client.upscale_video(
        media_gen_id=video_media_id,
        scene_id=req.get("scene_id", ""),
        aspect_ratio=aspect,
    )


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


async def _update_scene_from_result(req: dict, orientation: str, media_gen_id: str, output_url: str):
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
        updates[f"{prefix}_video_status"] = "COMPLETED"
    elif req_type == "UPSCALE_VIDEO":
        updates[f"{prefix}_upscale_media_gen_id"] = media_gen_id
        updates[f"{prefix}_upscale_url"] = output_url
        updates[f"{prefix}_upscale_status"] = "COMPLETED"

    if updates:
        await crud.update_scene(scene_id, **updates)
