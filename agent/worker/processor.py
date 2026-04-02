"""Background worker — processes pending requests via Chrome extension.

Thin dispatcher: picks up PENDING requests, delegates to OperationService
for actual API work, handles status transitions + retry + scene updates.
"""
import asyncio
import json
import logging
import time

from agent.db import crud
from agent.services.flow_client import get_flow_client
from agent.config import POLL_INTERVAL, MAX_RETRIES, API_COOLDOWN
from agent.worker._parsing import _is_error, _extract_media_id, _extract_output_url

logger = logging.getLogger(__name__)

_retry_state: dict[str, tuple[int, float]] = {}

_API_CALL_TYPES = {"GENERATE_IMAGE", "GENERATE_VIDEO", "GENERATE_VIDEO_REFS",
                   "UPSCALE_VIDEO", "GENERATE_CHARACTER_IMAGE", "EDIT_IMAGE"}


async def process_pending_requests():
    """Main worker loop — dispatches pending requests concurrently."""
    client = get_flow_client()
    active: set[str] = set()

    while True:
        try:
            if not client.connected:
                await asyncio.sleep(POLL_INTERVAL)
                continue
            for req in await crud.list_pending_requests():
                rid = req["id"]
                if rid not in active:
                    active.add(rid)
                    asyncio.create_task(_tracked(req, active))
        except Exception as e:
            logger.exception("Worker loop error: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


async def _tracked(req: dict, active: set):
    try:
        await _process_one(req)
    finally:
        active.discard(req["id"])


async def _process_one(req: dict):
    rid, req_type = req["id"], req["type"]
    orientation = req.get("orientation", "VERTICAL")

    if await _is_already_completed(req, orientation):
        logger.info("Request %s skipped — already COMPLETED", rid[:8])
        await crud.update_request(rid, status="COMPLETED", error_message="skipped: already completed")
        return

    logger.info("Processing request %s type=%s", rid[:8], req_type)
    await crud.update_request(rid, status="PROCESSING")

    if req_type in _API_CALL_TYPES and API_COOLDOWN > 0:
        await asyncio.sleep(API_COOLDOWN)

    try:
        result = await _dispatch(req, orientation)
        if _is_error(result):
            await _handle_failure(rid, req, result)
        else:
            media_id = _extract_media_id(result, req_type)
            output_url = _extract_output_url(result, req_type)
            await crud.update_request(rid, status="COMPLETED", media_id=media_id, output_url=output_url)
            await _update_scene_from_result(req, orientation, media_id, output_url)
            logger.info("Request %s COMPLETED: media=%s", rid[:8], media_id[:20] if media_id else "?")
    except Exception as e:
        logger.exception("Request %s exception: %s", rid[:8], e)
        await _handle_failure(rid, req, {"error": str(e)})


async def _dispatch(req: dict, orientation: str) -> dict:
    """Route request to the appropriate OperationService method."""
    from agent.sdk.services.operations import get_operations
    ops = get_operations()
    req_type, rid = req["type"], req["id"]
    pid = req.get("project_id", "0")

    # Scene-based operations
    if req_type in ("GENERATE_IMAGE", "EDIT_IMAGE", "GENERATE_VIDEO",
                    "GENERATE_VIDEO_REFS", "UPSCALE_VIDEO"):
        scene = await crud.get_scene(req.get("scene_id"))
        if not scene:
            return {"error": "Scene not found"}
        scene["_project_id"] = pid

        if req_type == "GENERATE_IMAGE":
            return await ops.generate_scene_image(scene, orientation)
        if req_type == "EDIT_IMAGE":
            return await ops.edit_scene_image(scene, orientation, source_media_id=req.get("source_media_id"))
        if req_type == "GENERATE_VIDEO":
            return await ops.generate_scene_video(scene, orientation, request_id=rid)
        if req_type == "GENERATE_VIDEO_REFS":
            return await ops.generate_scene_video_refs(scene, orientation, request_id=rid)
        if req_type == "UPSCALE_VIDEO":
            return await ops.upscale_scene_video(scene, orientation, request_id=rid)

    # Character operations
    if req_type == "GENERATE_CHARACTER_IMAGE":
        char = await crud.get_character(req.get("character_id"))
        if not char:
            return {"error": "Character not found"}
        return await ops.generate_reference_image(char, pid)

    return {"error": f"Unknown request type: {req_type}"}


async def _handle_failure(rid: str, req: dict, result: dict):
    error_msg = result.get("error")
    if not error_msg:
        data = result.get("data", {})
        if isinstance(data, dict):
            ef = data.get("error", "Unknown error")
            error_msg = ef.get("message", json.dumps(ef)[:200]) if isinstance(ef, dict) else str(ef)
        else:
            error_msg = "Unknown error"
    if isinstance(error_msg, dict):
        error_msg = json.dumps(error_msg)[:200]

    retry = req.get("retry_count", 0) + 1
    if retry < MAX_RETRIES:
        _, retry_after = _retry_state.get(rid, (0, 0.0))
        now = time.time()
        if retry_after > now:
            return
        _retry_state[rid] = (retry, now + min(2 ** retry * 10, 300))
        await crud.update_request(rid, status="PENDING", retry_count=retry, error_message=str(error_msg))
        logger.warning("Request %s failed (retry %d/%d): %s", rid[:8], retry, MAX_RETRIES, error_msg)
    else:
        await crud.update_request(rid, status="FAILED", error_message=str(error_msg))
        await _mark_scene_failed(req)
        logger.error("Request %s FAILED permanently: %s", rid[:8], error_msg)


async def _mark_scene_failed(req: dict):
    scene_id = req.get("scene_id")
    if not scene_id:
        return
    prefix = "vertical" if req.get("orientation", "VERTICAL") == "VERTICAL" else "horizontal"
    req_type = req["type"]
    updates = {}
    if req_type in ("GENERATE_IMAGE", "EDIT_IMAGE"):
        updates[f"{prefix}_image_status"] = "FAILED"
    elif req_type in ("GENERATE_VIDEO", "GENERATE_VIDEO_REFS"):
        updates[f"{prefix}_video_status"] = "FAILED"
    elif req_type == "UPSCALE_VIDEO":
        updates[f"{prefix}_upscale_status"] = "FAILED"
    if updates:
        await crud.update_scene(scene_id, **updates)


async def _is_already_completed(req: dict, orientation: str) -> bool:
    scene_id = req.get("scene_id")
    req_type = req.get("type", "")
    if not scene_id or req_type == "GENERATE_CHARACTER_IMAGE":
        return False
    scene = await crud.get_scene(scene_id)
    if not scene:
        return False
    prefix = "vertical" if orientation == "VERTICAL" else "horizontal"
    if req_type in ("GENERATE_IMAGE", "EDIT_IMAGE"):
        return scene.get(f"{prefix}_image_status") == "COMPLETED"
    if req_type in ("GENERATE_VIDEO", "GENERATE_VIDEO_REFS"):
        return scene.get(f"{prefix}_video_status") == "COMPLETED"
    if req_type == "UPSCALE_VIDEO":
        return scene.get(f"{prefix}_upscale_status") == "COMPLETED"
    return False


async def _update_scene_from_result(req: dict, orientation: str, media_id: str, output_url: str):
    """Update scene fields + cascade-clear downstream on regen."""
    scene_id = req.get("scene_id")
    if not scene_id:
        return
    p = "vertical" if orientation == "VERTICAL" else "horizontal"
    req_type = req["type"]
    updates = {}

    if req_type in ("GENERATE_IMAGE", "EDIT_IMAGE"):
        updates.update({
            f"{p}_image_media_id": media_id, f"{p}_image_url": output_url,
            f"{p}_image_status": "COMPLETED",
            f"{p}_video_media_id": None, f"{p}_video_url": None, f"{p}_video_status": "PENDING",
            f"{p}_upscale_media_id": None, f"{p}_upscale_url": None, f"{p}_upscale_status": "PENDING",
        })
    elif req_type in ("GENERATE_VIDEO", "GENERATE_VIDEO_REFS"):
        updates.update({
            f"{p}_video_media_id": media_id, f"{p}_video_url": output_url,
            f"{p}_video_status": "COMPLETED",
            f"{p}_upscale_media_id": None, f"{p}_upscale_url": None, f"{p}_upscale_status": "PENDING",
        })
    elif req_type == "UPSCALE_VIDEO":
        updates.update({
            f"{p}_upscale_media_id": media_id, f"{p}_upscale_url": output_url,
            f"{p}_upscale_status": "COMPLETED",
        })

    if updates:
        await crud.update_scene(scene_id, **updates)
