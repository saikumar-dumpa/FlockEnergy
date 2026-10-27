"""Public response models for the wrapper API."""

from datetime import datetime

from pydantic import BaseModel, Field


class MeterDetails(BaseModel):
    meter_id: str
    serial_no: str | None = None
    make: str | None = None
    phase_type: str | None = None
    installation_status: str | None = None
    installation_type: str | None = None
    dt_id: str | None = None
    zone: str | None = None
    location_lat: float | None = None
    location_long: float | None = None
    full_hierarchy: str | None = None


class MeterSummary(BaseModel):
    meter_id: str
    serial_no: str | None = None
    make: str | None = None
    phase_type: str | None = None
    installation_status: str | None = None
    dt_id: str | None = None


class MeterListResponse(BaseModel):
    meters: list[MeterSummary]
    page: int = Field(ge=1)
    limit: int = Field(ge=1)


class ConsumptionRecord(BaseModel):
    timestamp: datetime
    kwh: float
    kvah: float


class ErrorResponse(BaseModel):
    detail: str
