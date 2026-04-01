from fastapi import APIRouter, HTTPException
from agent.models.character import Character, CharacterCreate, CharacterUpdate
from agent.db import crud

router = APIRouter(prefix="/characters", tags=["characters"])


@router.post("", response_model=Character)
async def create(body: CharacterCreate):
    return await crud.create_character(**body.model_dump(exclude_none=True))


@router.get("", response_model=list[Character])
async def list_all():
    return await crud.list_characters()


@router.get("/{cid}", response_model=Character)
async def get(cid: str):
    c = await crud.get_character(cid)
    if not c:
        raise HTTPException(404, "Character not found")
    return c


@router.patch("/{cid}", response_model=Character)
async def update(cid: str, body: CharacterUpdate):
    c = await crud.update_character(cid, **body.model_dump(exclude_unset=True))
    if not c:
        raise HTTPException(404, "Character not found")
    return c


@router.delete("/{cid}")
async def delete(cid: str):
    if not await crud.delete_character(cid):
        raise HTTPException(404, "Character not found")
    return {"ok": True}
