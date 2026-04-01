from pydantic import BaseModel
from typing import Optional


class CharacterCreate(BaseModel):
    name: str
    description: Optional[str] = None
    reference_image_url: Optional[str] = None
    media_gen_id: Optional[str] = None


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    reference_image_url: Optional[str] = None
    media_gen_id: Optional[str] = None


class Character(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    reference_image_url: Optional[str] = None
    media_gen_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
