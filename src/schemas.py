from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def serialize_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class CapsuleCreate(CamelModel):
    title: str = Field(..., min_length=1, max_length=120)
    content: str = Field(..., min_length=1)
    unlock_at: datetime = Field(..., alias="unlockAt")


class CapsuleUpdate(CamelModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    content: str | None = Field(default=None, min_length=1)
    unlock_at: datetime | None = Field(default=None, alias="unlockAt")


class CapsuleRead(CamelModel):
    id: int
    title: str
    content: str
    unlock_at: datetime = Field(alias="unlockAt")
    public_code: str = Field(alias="publicCode")
    is_deleted: bool = Field(alias="isDeleted")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_serializer("unlock_at", "created_at")
    def serialize_dates(self, value: datetime) -> str:
        return serialize_utc(value)


class CapsuleCreateResponse(CamelModel):
    id: int
    public_code: str = Field(alias="publicCode")
    open_url: str = Field(alias="openUrl")
    qr_url: str = Field(alias="qrUrl")


class LockedCapsuleResponse(CamelModel):
    status: Literal["locked"] = "locked"
    message: str
    unlock_at: datetime = Field(alias="unlockAt")

    @field_serializer("unlock_at")
    def serialize_unlock_at(self, value: datetime) -> str:
        return serialize_utc(value)


class UnlockedCapsuleResponse(CamelModel):
    status: Literal["unlocked"] = "unlocked"
    title: str
    content: str
    public_code: str = Field(alias="publicCode")


class HealthResponse(CamelModel):
    status: str
    database: str
