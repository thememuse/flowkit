from fastapi import APIRouter, HTTPException
from agent.models.scene import Scene, SceneCreate, SceneUpdate
from agent.sdk.persistence.sqlite_repository import SQLiteRepository
import json

router = APIRouter(prefix="/scenes", tags=["scenes"])

_repo = SQLiteRepository()


def _scene_to_flat(sdk_scene) -> dict:
    """Convert SDK Scene domain model to flat dict matching API response shape."""
    repo = SQLiteRepository()
    flat = repo._scene_to_updates(sdk_scene)
    flat["id"] = sdk_scene.id
    flat["video_id"] = sdk_scene.video_id
    flat["display_order"] = sdk_scene.display_order
    flat["parent_scene_id"] = sdk_scene.parent_scene_id
    flat["chain_type"] = sdk_scene.chain_type
    flat["character_names"] = sdk_scene.character_names
    flat["created_at"] = sdk_scene.created_at
    flat["updated_at"] = sdk_scene.updated_at
    return flat


@router.post("", response_model=Scene)
async def create(body: SceneCreate):
    data = body.model_dump(exclude_none=True)
    sdk_scene = await _repo.create_scene(**data)
    return _scene_to_flat(sdk_scene)


@router.get("", response_model=list[Scene])
async def list_by_video(video_id: str):
    scenes = await _repo.list_scenes(video_id)
    return [_scene_to_flat(s) for s in scenes]


@router.get("/{sid}", response_model=Scene)
async def get(sid: str):
    sdk_scene = await _repo.get_scene(sid)
    if not sdk_scene:
        raise HTTPException(404, "Scene not found")
    return _scene_to_flat(sdk_scene)


@router.patch("/{sid}", response_model=Scene)
async def update(sid: str, body: SceneUpdate):
    # Use exclude_unset (not exclude_none) so explicit null clears fields
    # e.g. {"vertical_video_url": null} → sets DB column to NULL
    data = body.model_dump(exclude_unset=True)
    if "character_names" in data and isinstance(data["character_names"], list):
        data["character_names"] = json.dumps(data["character_names"])
    row = await _repo.update("scene", sid, **data)
    if not row:
        raise HTTPException(404, "Scene not found")
    sdk_scene = _repo._row_to_scene(row)
    return _scene_to_flat(sdk_scene)


@router.delete("/{sid}")
async def delete(sid: str):
    if not await _repo.delete("scene", sid):
        raise HTTPException(404, "Scene not found")
    return {"ok": True}
