"""Pydantic models, enums, and dataclasses for testing."""

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel


class UserStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"


class UserCreate(BaseModel):
    name: str
    email: str
    status: UserStatus = UserStatus.ACTIVE


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    status: UserStatus


@dataclass
class CacheEntry:
    key: str
    value: str
    ttl: int = 300
