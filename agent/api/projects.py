from fastapi import APIRouter, HTTPException
from agent.models.project import Project, ProjectCreate, ProjectUpdate
from agent.models.character import Character
from agent.db import crud

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=Project)
async def create(body: ProjectCreate):
    return await crud.create_project(**body.model_dump(exclude_none=True))


@router.get("", response_model=list[Project])
async def list_all(status: str = None):
    return await crud.list_projects(status)


@router.get("/{pid}", response_model=Project)
async def get(pid: str):
    p = await crud.get_project(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.patch("/{pid}", response_model=Project)
async def update(pid: str, body: ProjectUpdate):
    p = await crud.update_project(pid, **body.model_dump(exclude_unset=True))
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.delete("/{pid}")
async def delete(pid: str):
    if not await crud.delete_project(pid):
        raise HTTPException(404, "Project not found")
    return {"ok": True}


@router.post("/{pid}/characters/{cid}")
async def link_character(pid: str, cid: str):
    if not await crud.link_character_to_project(pid, cid):
        raise HTTPException(400, "Failed to link character")
    return {"ok": True}


@router.delete("/{pid}/characters/{cid}")
async def unlink_character(pid: str, cid: str):
    if not await crud.unlink_character_from_project(pid, cid):
        raise HTTPException(404, "Link not found")
    return {"ok": True}


@router.get("/{pid}/characters", response_model=list[Character])
async def get_characters(pid: str):
    return await crud.get_project_characters(pid)
