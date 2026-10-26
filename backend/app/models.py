import re
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

_PLATE_RE = re.compile(r"^[A-Z0-9]{4,12}$")


def normalize_plate(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _clean_plate(v: str) -> str:
    plate = normalize_plate(v)
    if not _PLATE_RE.match(plate):
        raise ValueError("plate must be 4-12 letters/digits after normalization")
    return plate


def _require_tz(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("timestamp must include a timezone, e.g. 2026-10-22T09:14:32+05:30")
    return v


class DetectionIn(BaseModel):
    """One voted plate read, sent by the CV service."""
    site_id: UUID
    gate_id: UUID
    plate: str
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    captured_at: datetime          # camera capture time, NOT server time
    image: Optional[str] = None    # path to the saved plate crop

    _plate = field_validator("plate")(_clean_plate)
    _tz = field_validator("captured_at")(_require_tz)


class VehicleIn(BaseModel):
    plate: str
    owner_name: Optional[str] = None
    role: Literal["resident", "staff", "blacklisted"]
    unit: Optional[str] = None

    _plate = field_validator("plate")(_clean_plate)


class PassIn(BaseModel):
    plate: str
    visitor_name: Optional[str] = None
    host_name: Optional[str] = None
    host_unit: Optional[str] = None
    valid_from: datetime
    valid_until: datetime

    _plate = field_validator("plate")(_clean_plate)
    _tz = field_validator("valid_from", "valid_until")(_require_tz)

    @model_validator(mode="after")
    def _window(self):
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        return self


class LoginIn(BaseModel):
    email: str
    password: str
