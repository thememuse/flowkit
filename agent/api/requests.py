from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
from agent.models.request import Request, RequestCreate
from agent.models.enums import StatusType
from agent.db import crud
from agent.utils.orientation import normalize_orientation

router = APIRouter(prefix="/requests", tags=["requests"])

_TYPE_ALIASES: dict[str, set[str]] = {
    "GENERATE_CHARACTER_IMAGE": {"GENERATE_CHARACTER_IMAGE", "REGENERATE_CHARACTER_IMAGE", "EDIT_CHARACTER_IMAGE"},
    "GENERATE_IMAGE": {"GENERATE_IMAGE", "REGENERATE_IMAGE", "EDIT_IMAGE"},
    "GENERATE_VIDEO": {"GENERATE_VIDEO", "REGENERATE_VIDEO", "GENERATE_VIDEO_REFS"},
    "UPSCALE_VIDEO": {"UPSCALE_VIDEO", "UPSCALE_VIDEO_LOCAL"},
}

_STAGE_BY_TYPE: dict[str, str] = {
    "GENERATE_CHARACTER_IMAGE": "character_image",
    "REGENERATE_CHARACTER_IMAGE": "character_image",
    "EDIT_CHARACTER_IMAGE": "character_image",
    "GENERATE_IMAGE": "scene_image",
    "REGENERATE_IMAGE": "scene_image",
    "EDIT_IMAGE": "scene_image",
    "GENERATE_VIDEO": "scene_video",
    "REGENERATE_VIDEO": "scene_video",
    "GENERATE_VIDEO_REFS": "scene_video",
    "UPSCALE_VIDEO": "scene_upscale",
    "UPSCALE_VIDEO_LOCAL": "scene_upscale",
}

_CAPTCHA_TYPES: set[str] = {
    "GENERATE_CHARACTER_IMAGE",
    "REGENERATE_CHARACTER_IMAGE",
    "EDIT_CHARACTER_IMAGE",
    "GENERATE_IMAGE",
    "REGENERATE_IMAGE",
    "EDIT_IMAGE",
    "GENERATE_VIDEO",
    "REGENERATE_VIDEO",
    "GENERATE_VIDEO_REFS",
}


def _stage_of(req_type: str | None) -> str:
    return _STAGE_BY_TYPE.get(str(req_type or ""), str(req_type or ""))


def _matches_logical_request(
    row: dict,
    *,
    req_type: str,
    scene_id: str | None,
    character_id: str | None,
    orientation: str | None,
) -> bool:
    """Compare by logical stage (not raw type) to avoid GENERATE/REGENERATE duplicates."""
    if _stage_of(row.get("type")) != _stage_of(req_type):
        return False

    if scene_id:
        if row.get("scene_id") != scene_id:
            return False
        req_orient = normalize_orientation(orientation) if orientation else "NONE"
        row_orient = normalize_orientation(row.get("orientation")) if row.get("orientation") else "NONE"
        return req_orient == row_orient

    if character_id:
        return row.get("character_id") == character_id

    return False


def _expand_types(type_filter: str | None) -> set[str] | None:
    if not type_filter:
        return None
    return _TYPE_ALIASES.get(type_filter, {type_filter})


def _request_stage_key(row: dict) -> str:
    """Build a stable key to collapse retries/regenerations into latest stage state."""
    req_type = row.get("type")
    stage = _STAGE_BY_TYPE.get(req_type, req_type or "unknown")
    orientation = normalize_orientation(row.get("orientation")) if row.get("orientation") else "NONE"
    scene_id = row.get("scene_id")
    character_id = row.get("character_id")
    if scene_id:
        return f"scene:{scene_id}:{stage}:{orientation}"
    if character_id:
        return f"character:{character_id}:{stage}"
    return f"request:{row.get('id')}"


def _latest_rows_per_stage(rows: list[dict]) -> list[dict]:
    """Keep only latest request per logical stage key (scene+stage+orientation or character+stage)."""
    latest: dict[str, dict] = {}
    for row in rows:
        key = _request_stage_key(row)
        prev = latest.get(key)
        if not prev:
            latest[key] = row
            continue
        prev_ts = prev.get("updated_at") or prev.get("created_at") or ""
        cur_ts = row.get("updated_at") or row.get("created_at") or ""
        if cur_ts >= prev_ts:
            latest[key] = row
    return list(latest.values())


def _parse_utc(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _status_hint(error_message: str | None) -> str | None:
    if not error_message:
        return None
    em = error_message.lower()
    if "public_error_unsafe_generation" in em or "unsafe_generation" in em:
        return "Prompt bị bộ lọc an toàn của Google Flow chặn. Hãy giảm nội dung nhạy cảm/bạo lực rồi tạo lại."
    if (
        "flow_tab_not_ready" in em
        or "no_flow_tab" in em
        or "no flow tab" in em
        or "flow tab not ready" in em
        or "grecaptcha not available" in em
        or "token expired" in em
    ):
        return "Flow tab chưa sẵn sàng. Hãy mở đúng trang Google Flow rồi thử lại."
    if "captcha_failed" in em or "recaptcha" in em or "captcha" in em:
        if "must request permission to access the respective host" in em or "cannot access contents of the page" in em:
            return "Captcha failed: extension không truy cập được đúng tab Flow."
        return "Captcha failed: đang chờ retry."
    if "extension not connected" in em or "extension disconnected" in em:
        return "Extension mất kết nối."
    if "google_sorry_page" in em or "unusual traffic" in em:
        return "Google chặn tạm thời do traffic bất thường. Hệ thống đã chuyển sang retry chậm để giảm captcha."
    if "model_access_denied" in em:
        return "Tài khoản hiện tại không có quyền dùng model này. Hãy đổi model hoặc đổi account/tier."
    if "quota_reached" in em or "public_error_user_quota_reached" in em or "public_error_per_model_daily_quota_reached" in em:
        return "Tài khoản đã chạm quota của Google Flow. Chờ reset quota hoặc đổi account rồi thử lại."
    if "api_403" in em:
        return "Google Flow từ chối request (API_403). Hệ thống sẽ retry ngắn để tự phục hồi phiên; nếu còn lỗi, kiểm tra quyền model/quota/account."
    if "api_429" in em:
        return "Google Flow trả API_429 (quá nhiều request hoặc hết quota tạm thời). Hãy chờ rồi thử lại."
    if "api_500" in em:
        return "Google Flow đang lỗi nội bộ (API_500). Hệ thống sẽ tự retry."
    if (
        "api_401" in em
        or "http_401" in em
        or "invalid authentication credentials" in em
        or "missing required authentication credential" in em
    ):
        return "Token Google Flow đã hết hạn/không hợp lệ. Hệ thống đang tự làm mới token và sẽ retry."
    if "local_upscale_setup_required" in em:
        return "Thiếu công cụ upscale local (ffmpeg/ffprobe/realesrgan/model). Cần cấu hình trước khi chạy 4K local."
    if "no local source video available for local upscale" in em:
        return "Upscale local cần video nguồn đã lưu trên máy. Hãy tải video local trước rồi chạy lại."
    if "dispatch timeout" in em and "upscale" in em:
        return "Upscale local bị timeout khi xử lý nặng. Hệ thống đã dừng request để tránh treo máy."
    return error_message


def _is_recent_traffic_block(row: dict, now: datetime, window_sec: int = 900) -> bool:
    if not row:
        return False
    err = str(row.get("error_message") or "").lower()
    if not err:
        return False
    if "google_sorry_page" not in err and "unusual traffic" not in err:
        return False
    updated = _parse_utc(row.get("updated_at")) or _parse_utc(row.get("created_at"))
    if not updated:
        return False
    age_sec = max(0, int((now - updated).total_seconds()))
    return age_sec <= max(60, int(window_sec))


async def _nudge_pending_request_now(row: dict) -> dict:
    """Force an existing pending request (possibly in retry wait) to run ASAP."""
    if not row:
        return row
    if row.get("status") != "PENDING":
        return row
    err = str(row.get("error_message") or "").lower()
    # Respect cooldown/backoff for captcha/traffic/auth blocks.
    protected_markers = (
        "google_sorry_page",
        "unusual traffic",
        "captcha",
        "recaptcha",
        "traffic cooldown",
        "token expired",
        "api_401",
        "invalid authentication credentials",
        "flow_tab_not_ready",
        "no_flow_tab",
        "extension not connected",
    )
    if any(marker in err for marker in protected_markers):
        return row
    now = datetime.now(timezone.utc)
    next_retry = _parse_utc(row.get("next_retry_at"))
    if next_retry and next_retry > now:
        updated = await crud.update_request(
            row["id"],
            next_retry_at=None,
            error_message="manual retry now",
        )
        return updated or row
    return row


async def _project_traffic_cooldown_until(project_id: str | None) -> str | None:
    if not project_id:
        return None
    rows = await crud.list_requests(project_id=project_id)
    if not rows:
        return None
    now = datetime.now(timezone.utc)
    latest: datetime | None = None
    recent_traffic_seen = False
    for row in rows:
        err = str(row.get("error_message") or "").lower()
        if "google_sorry_page" not in err and "unusual traffic" not in err:
            continue
        if _is_recent_traffic_block(row, now):
            recent_traffic_seen = True
        nr = _parse_utc(row.get("next_retry_at"))
        if not nr or nr <= now:
            continue
        if not latest or nr > latest:
            latest = nr
    if latest:
        return latest.strftime("%Y-%m-%dT%H:%M:%SZ")
    if recent_traffic_seen:
        return (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


class RequestUpdate(BaseModel):
    status: Optional[StatusType] = None
    media_id: Optional[str] = None
    output_url: Optional[str] = None
    error_message: Optional[str] = None
    request_id: Optional[str] = None


class BatchRequestCreate(BaseModel):
    requests: list[RequestCreate]


class BatchStatus(BaseModel):
    total: int
    pending: int
    queued_pending: int = 0
    retry_waiting: int = 0
    processing: int
    completed: int
    failed: int
    done: bool
    all_succeeded: bool
    orientation: Optional[str] = None
    next_retry_at: Optional[str] = None
    next_retry_in_sec: Optional[int] = None
    status_hint: Optional[str] = None
    oldest_processing_sec: Optional[int] = None


async def _validate_request_scope(data: dict) -> dict:
    """Ensure request references stay inside the declared project/video scope.

    This prevents accidental cross-project generation when stale IDs are mixed.
    Returns possibly enriched data (auto-filled project_id/video_id from scene).
    """
    project_id = data.get("project_id")
    video_id = data.get("video_id")
    scene_id = data.get("scene_id")
    character_id = data.get("character_id")

    if project_id:
        project = await crud.get_project(project_id)
        if not project:
            raise HTTPException(404, f"Project not found: {project_id}")

    video = None
    if video_id:
        video = await crud.get_video(video_id)
        if not video:
            raise HTTPException(404, f"Video not found: {video_id}")
        if project_id and video.get("project_id") != project_id:
            raise HTTPException(
                400,
                f"video_id {video_id} does not belong to project_id {project_id}",
            )

    if scene_id:
        scene = await crud.get_scene(scene_id)
        if not scene:
            raise HTTPException(404, f"Scene not found: {scene_id}")

        if video_id and scene.get("video_id") != video_id:
            raise HTTPException(
                400,
                f"scene_id {scene_id} does not belong to video_id {video_id}",
            )

        if not video:
            video = await crud.get_video(scene.get("video_id"))
            if not video:
                raise HTTPException(
                    404, f"Video not found for scene_id {scene_id}: {scene.get('video_id')}"
                )

        if project_id and video.get("project_id") != project_id:
            raise HTTPException(
                400,
                f"scene_id {scene_id} does not belong to project_id {project_id}",
            )

        data.setdefault("video_id", scene.get("video_id"))
        data.setdefault("project_id", video.get("project_id"))
        project_id = data.get("project_id")

    if character_id:
        char = await crud.get_character(character_id)
        if not char:
            raise HTTPException(404, f"Character not found: {character_id}")
        if project_id:
            linked = await crud.get_project_characters(project_id)
            if not any(c.get("id") == character_id for c in linked):
                raise HTTPException(
                    400,
                    f"character_id {character_id} does not belong to project_id {project_id}",
                )

    return data


@router.post("", response_model=Request)
async def create(body: RequestCreate):
    data = body.model_dump(exclude_none=True)
    data["req_type"] = data.pop("type")
    if data["req_type"] == "UPSCALE_VIDEO":
        data["req_type"] = "UPSCALE_VIDEO_LOCAL"
    if data.get("orientation"):
        data["orientation"] = normalize_orientation(data["orientation"])
    data = await _validate_request_scope(data)

    # Reject if there's already an active request for the same scene + type
    scene_id = data.get("scene_id")
    character_id = data.get("character_id")
    req_type = data.get("req_type")
    cooldown_until = await _project_traffic_cooldown_until(data.get("project_id"))
    if scene_id and req_type:
        existing = await crud.list_requests(scene_id=scene_id)
        active = [
            r for r in existing
            if r.get("status") in ("PENDING", "PROCESSING")
            and _matches_logical_request(
                r,
                req_type=req_type,
                scene_id=scene_id,
                character_id=None,
                orientation=data.get("orientation"),
            )
        ]
        if active:
            reused = active[0]
            raise HTTPException(
                409,
                f"Active {req_type} request already exists for scene {scene_id[:8]} "
                f"(status={reused['status']}, id={reused['id'][:8]})"
            )
        now = datetime.now(timezone.utc)
        recent_traffic = next(
            (
                r for r in existing
                if r.get("status") in ("FAILED", "PENDING")
                and _matches_logical_request(
                    r,
                    req_type=req_type,
                    scene_id=scene_id,
                    character_id=None,
                    orientation=data.get("orientation"),
                )
                and _is_recent_traffic_block(r, now)
            ),
            None,
        )
        if recent_traffic:
            # Reuse instead of creating new rows that would immediately fail again.
            revived = await crud.update_request(
                recent_traffic["id"],
                status="PENDING",
                next_retry_at=recent_traffic.get("next_retry_at") or None,
                error_message=recent_traffic.get("error_message") or "traffic cooldown",
            )
            return revived or recent_traffic
    if character_id and req_type:
        existing = await crud.list_requests(project_id=data.get("project_id"))
        active = [
            r for r in existing
            if r.get("status") in ("PENDING", "PROCESSING")
            and _matches_logical_request(
                r,
                req_type=req_type,
                scene_id=None,
                character_id=character_id,
                orientation=None,
            )
        ]
        if active:
            reused = active[0]
            raise HTTPException(
                409,
                f"Active {req_type} request already exists for character {character_id[:8]} "
                f"(status={reused['status']}, id={reused['id'][:8]})"
            )
        now = datetime.now(timezone.utc)
        recent_traffic = next(
            (
                r for r in existing
                if r.get("status") in ("FAILED", "PENDING")
                and _matches_logical_request(
                    r,
                    req_type=req_type,
                    scene_id=None,
                    character_id=character_id,
                    orientation=None,
                )
                and _is_recent_traffic_block(r, now)
            ),
            None,
        )
        if recent_traffic:
            revived = await crud.update_request(
                recent_traffic["id"],
                status="PENDING",
                next_retry_at=recent_traffic.get("next_retry_at") or None,
                error_message=recent_traffic.get("error_message") or "traffic cooldown",
            )
            return revived or recent_traffic

    # Auto-set video orientation (symmetric with batch endpoint)
    vid = data.get("video_id")
    orient = data.get("orientation")
    if vid and orient:
        await crud.update_video(vid, orientation=orient)

    if cooldown_until and req_type in _CAPTCHA_TYPES:
        data["status"] = "PENDING"
        data["next_retry_at"] = cooldown_until
        data["error_message"] = "traffic cooldown (project-wide): waiting for retry window"

    return await crud.create_request(**data)


@router.post("/batch", response_model=list[Request])
async def create_batch(body: BatchRequestCreate):
    """Submit multiple requests atomically. Server handles throttling (max 5 concurrent, 10s cooldown).
    Duplicate active requests for the same scene+type are skipped (not errors)."""
    scene_regen_types = {"REGENERATE_IMAGE", "REGENERATE_VIDEO"}
    scene_regen_count = sum(
        1 for item in body.requests if getattr(item, "type", None) in scene_regen_types
    )
    if scene_regen_count > 1 or (
        scene_regen_count == 1 and len(body.requests) > 1
    ):
        raise HTTPException(
            400,
            "Đã khóa tạo lại hàng loạt ảnh/video để tránh ghi đè nhầm. "
            "Hãy tạo lại thủ công từng cảnh.",
        )

    results = []
    _seen_vids: set[str] = set()
    cooldown_by_project: dict[str, str | None] = {}
    for item in body.requests:
        data = item.model_dump(exclude_none=True)
        data["req_type"] = data.pop("type")
        if data["req_type"] == "UPSCALE_VIDEO":
            data["req_type"] = "UPSCALE_VIDEO_LOCAL"
        if data.get("orientation"):
            data["orientation"] = normalize_orientation(data["orientation"])
        data = await _validate_request_scope(data)
        vid = data.get("video_id")
        orient = data.get("orientation")
        if vid and orient and vid not in _seen_vids:
            _seen_vids.add(vid)
            await crud.update_video(vid, orientation=orient)
        scene_id = data.get("scene_id")
        character_id = data.get("character_id")
        req_type = data.get("req_type")
        pid = str(data.get("project_id") or "")
        if pid not in cooldown_by_project:
            cooldown_by_project[pid] = await _project_traffic_cooldown_until(pid or None)
        cooldown_until = cooldown_by_project[pid]
        # Idempotent: skip if active request already exists
        if scene_id and req_type:
            existing = await crud.list_requests(scene_id=scene_id)
            active = [
                r for r in existing
                if r.get("status") in ("PENDING", "PROCESSING")
                and _matches_logical_request(
                    r,
                    req_type=req_type,
                    scene_id=scene_id,
                    character_id=None,
                    orientation=data.get("orientation"),
                )
            ]
            if active:
                results.append(active[0])
                continue
            now = datetime.now(timezone.utc)
            recent_traffic = next(
                (
                    r for r in existing
                    if r.get("status") in ("FAILED", "PENDING")
                    and _matches_logical_request(
                        r,
                        req_type=req_type,
                        scene_id=scene_id,
                        character_id=None,
                        orientation=data.get("orientation"),
                    )
                    and _is_recent_traffic_block(r, now)
                ),
                None,
            )
            if recent_traffic:
                revived = await crud.update_request(
                    recent_traffic["id"],
                    status="PENDING",
                    next_retry_at=recent_traffic.get("next_retry_at") or None,
                    error_message=recent_traffic.get("error_message") or "traffic cooldown",
                )
                results.append(revived or recent_traffic)
                continue
        if character_id and req_type:
            existing = await crud.list_requests(project_id=data.get("project_id"))
            active = [
                r for r in existing
                if r.get("status") in ("PENDING", "PROCESSING")
                and _matches_logical_request(
                    r,
                    req_type=req_type,
                    scene_id=None,
                    character_id=character_id,
                    orientation=None,
                )
            ]
            if active:
                results.append(active[0])
                continue
            now = datetime.now(timezone.utc)
            recent_traffic = next(
                (
                    r for r in existing
                    if r.get("status") in ("FAILED", "PENDING")
                    and _matches_logical_request(
                        r,
                        req_type=req_type,
                        scene_id=None,
                        character_id=character_id,
                        orientation=None,
                    )
                    and _is_recent_traffic_block(r, now)
                ),
                None,
            )
            if recent_traffic:
                revived = await crud.update_request(
                    recent_traffic["id"],
                    status="PENDING",
                    next_retry_at=recent_traffic.get("next_retry_at") or None,
                    error_message=recent_traffic.get("error_message") or "traffic cooldown",
                )
                results.append(revived or recent_traffic)
                continue
        if cooldown_until and req_type in _CAPTCHA_TYPES:
            data["status"] = "PENDING"
            data["next_retry_at"] = cooldown_until
            data["error_message"] = "traffic cooldown (project-wide): waiting for retry window"
        results.append(await crud.create_request(**data))
    return results


@router.get("", response_model=list[Request])
async def list_all(scene_id: str = None, status: str = None,
                   video_id: str = None, project_id: str = None):
    return await crud.list_requests(scene_id=scene_id, status=status,
                                    video_id=video_id, project_id=project_id)


@router.get("/pending", response_model=list[Request])
async def list_pending():
    return await crud.list_pending_requests()


@router.get("/batch-status", response_model=BatchStatus)
async def batch_status(video_id: str = None, project_id: str = None,
                       type: str = None, orientation: str = None):
    """Aggregate status for all requests matching the filter.
    Poll this instead of polling N individual request IDs."""
    rows = await crud.list_requests(video_id=video_id, project_id=project_id)
    type_filter = _expand_types(type)
    if type_filter:
        rows = [r for r in rows if r.get("type") in type_filter]
    if orientation:
        normalized_orientation = normalize_orientation(orientation)
        rows = [r for r in rows if normalize_orientation(r.get("orientation")) == normalized_orientation]
    rows = _latest_rows_per_stage(rows)
    counts = {"PENDING": 0, "PROCESSING": 0, "COMPLETED": 0, "FAILED": 0}
    now = datetime.now(timezone.utc)
    queued_pending = 0
    retry_waiting = 0
    next_retry_ts: datetime | None = None
    hint: str | None = None
    oldest_processing_sec: int | None = None
    processing_types: set[str] = set()

    for r in rows:
        s = r.get("status", "PENDING")
        counts[s] = counts.get(s, 0) + 1
        if s == "PROCESSING":
            rt = r.get("type")
            if isinstance(rt, str) and rt:
                processing_types.add(rt)
            updated_at = _parse_utc(r.get("updated_at")) or _parse_utc(r.get("created_at"))
            if updated_at:
                age = max(0, int((now - updated_at).total_seconds()))
                if oldest_processing_sec is None or age > oldest_processing_sec:
                    oldest_processing_sec = age
            continue
        if s != "PENDING":
            continue
        nr = _parse_utc(r.get("next_retry_at"))
        if nr and nr > now:
            retry_waiting += 1
            if not next_retry_ts or nr < next_retry_ts:
                next_retry_ts = nr
                hint = _status_hint(r.get("error_message"))
        else:
            queued_pending += 1
    total = len(rows)
    next_retry_at = next_retry_ts.strftime("%Y-%m-%dT%H:%M:%SZ") if next_retry_ts else None
    next_retry_in_sec = None
    if next_retry_ts:
        next_retry_in_sec = max(0, int((next_retry_ts - now).total_seconds()))
    if not hint and oldest_processing_sec is not None:
        upscale_types = {"UPSCALE_VIDEO", "UPSCALE_VIDEO_LOCAL"}
        if processing_types and processing_types.issubset(upscale_types):
            if oldest_processing_sec >= 300:
                hint = (
                    f"Upscale local đang chạy ({oldest_processing_sec}s). "
                    "Tác vụ này có thể mất vài phút tùy độ dài clip."
                )
        elif oldest_processing_sec > 120:
            hint = f"Có request đang PROCESSING lâu ({oldest_processing_sec}s), có thể đang kẹt captcha/tab Flow."
    return BatchStatus(
        total=total,
        pending=counts["PENDING"],
        queued_pending=queued_pending,
        retry_waiting=retry_waiting,
        processing=counts["PROCESSING"],
        orientation=orientation,
        completed=counts["COMPLETED"],
        failed=counts["FAILED"],
        done=(counts["PENDING"] == 0 and counts["PROCESSING"] == 0),
        all_succeeded=(counts["COMPLETED"] == total and total > 0),
        next_retry_at=next_retry_at,
        next_retry_in_sec=next_retry_in_sec,
        status_hint=hint,
        oldest_processing_sec=oldest_processing_sec,
    )


@router.get("/failed")
async def list_failed(video_id: str = None, project_id: str = None, type: str = None, orientation: str = None):
    """Return failed request details (scene_id, error_message, type) for error display."""
    rows = await crud.list_requests(video_id=video_id, project_id=project_id)
    type_filter = _expand_types(type)
    if type_filter:
        rows = [r for r in rows if r.get("type") in type_filter]
    if orientation:
        normalized = normalize_orientation(orientation)
        rows = [r for r in rows if normalize_orientation(r.get("orientation")) == normalized]
    rows = [r for r in _latest_rows_per_stage(rows) if r.get("status") == "FAILED"]
    return [
        {
            "id": r.get("id"),
            "scene_id": r.get("scene_id"),
            "character_id": r.get("character_id"),
            "type": r.get("type"),
            "error_message": r.get("error_message") or "Lỗi không xác định",
            "retry_count": r.get("retry_count", 0),
            "updated_at": r.get("updated_at"),
        }
        for r in rows
    ]


@router.get("/{rid}", response_model=Request)
async def get(rid: str):
    r = await crud.get_request(rid)
    if not r:
        raise HTTPException(404, "Request not found")
    return r


@router.patch("/{rid}", response_model=Request)
async def update(rid: str, body: RequestUpdate):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "No fields to update")
    r = await crud.update_request(rid, **data)
    if not r:
        raise HTTPException(404, "Request not found")
    return r
