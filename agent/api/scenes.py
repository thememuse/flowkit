from fastapi import APIRouter, HTTPException
from agent.models.scene import Scene, SceneCreate, SceneUpdate
from agent.db import crud
import json

router = APIRouter(prefix="/scenes", tags=["scenes"])


def _parse_scene(row: dict) -> dict:
    """Parse character_names from JSON string to list."""
    if row and row.get("character_names") and isinstance(row["character_names"], str):
        try:
            row["character_names"] = json.loads(row["character_names"])
        except json.JSONDecodeError:
            row["character_names"] = None
    return row


@router.post("", response_model=Scene)
async def create(body: SceneCreate):
    data = body.model_dump(exclude_none=True)
    return _parse_scene(await crud.create_scene(**data))


@router.get("", response_model=list[Scene])
async def list_by_video(video_id: str):
    rows = await crud.list_scenes(video_id)
    return [_parse_scene(r) for r in rows]


@router.get("/{sid}", response_model=Scene)
async def get(sid: str):
    s = await crud.get_scene(sid)
    if not s:
        raise HTTPException(404, "Scene not found")
    return _parse_scene(s)


@router.patch("/{sid}", response_model=Scene)
async def update(sid: str, body: SceneUpdate):
    data = body.model_dump(exclude_none=True)
    if "character_names" in data and isinstance(data["character_names"], list):
        data["character_names"] = json.dumps(data["character_names"])
    s = await crud.update_scene(sid, **data)
    if not s:
        raise HTTPException(404, "Scene not found")
    return _parse_scene(s)


@router.delete("/{sid}")
async def delete(sid: str):
    if not await crud.delete_scene(sid):
        raise HTTPException(404, "Scene not found")
    return {"ok": True}
