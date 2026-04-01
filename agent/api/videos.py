from fastapi import APIRouter, HTTPException
from agent.models.video import Video, VideoCreate, VideoUpdate
from agent.db import crud

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("", response_model=Video)
async def create(body: VideoCreate):
    return await crud.create_video(**body.model_dump(exclude_none=True))


@router.get("", response_model=list[Video])
async def list_by_project(project_id: str):
    return await crud.list_videos(project_id)


@router.get("/{vid}", response_model=Video)
async def get(vid: str):
    v = await crud.get_video(vid)
    if not v:
        raise HTTPException(404, "Video not found")
    return v


@router.patch("/{vid}", response_model=Video)
async def update(vid: str, body: VideoUpdate):
    v = await crud.update_video(vid, **body.model_dump(exclude_unset=True))
    if not v:
        raise HTTPException(404, "Video not found")
    return v


@router.delete("/{vid}")
async def delete(vid: str):
    if not await crud.delete_video(vid):
        raise HTTPException(404, "Video not found")
    return {"ok": True}
