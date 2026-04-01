from pydantic import BaseModel
from typing import Optional
from agent.models.enums import ProjectStatus, PaygateTier


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    language: str = "en"
    user_paygate_tier: PaygateTier = "PAYGATE_TIER_TWO"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    language: Optional[str] = None
    status: Optional[ProjectStatus] = None
    user_paygate_tier: Optional[PaygateTier] = None


class Project(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    language: str = "en"
    status: str = "ACTIVE"
    user_paygate_tier: str = "PAYGATE_TIER_TWO"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
