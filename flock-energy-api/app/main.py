"""FastAPI application exposing normalized, read-only portal data."""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, TypeVar

from fastapi import FastAPI, HTTPException, Query, Request

from app.client import (
    AuthenticationError,
    PortalError,
    PortalNotFound,
    SessionExpired,
    UrjaPortalClient,
)
from app.config import get_settings
from app.models import (
    ConsumptionRecord,
    ErrorResponse,
    MeterDetails,
    MeterListResponse,
    MeterSummary,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if not settings.portal_user or not settings.portal_pass:
        raise RuntimeError("PORTAL_USER and PORTAL_PASS must be set before starting the API.")
    client = UrjaPortalClient(settings.portal_url)
    try:
        client.login(settings.portal_user, settings.portal_pass)
        app.state.portal_client = client
        app.state.portal_url = settings.portal_url
        yield
    finally:
        client.close()


app = FastAPI(
    title="Flock Energy - Urja Meter Ops API",
    version="1.0.0",
    description="A read-only JSON wrapper over the legacy Urja Meter Ops portal.",
    lifespan=lifespan,
)

Result = TypeVar("Result")


def get_client(request: Request) -> UrjaPortalClient:
    return request.app.state.portal_client


def portal_call(callable_: Callable[..., Result], *args: object) -> Result:
    try:
        return callable_(*args)
    except PortalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (AuthenticationError, SessionExpired) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except PortalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/", tags=["health"])
def health(request: Request) -> dict[str, str]:
    return {"status": "ok", "portal": request.app.state.portal_url}


@app.get(
    "/api/v1/meters",
    response_model=MeterListResponse,
    responses={502: {"model": ErrorResponse}},
    tags=["meters"],
)
def list_meters(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
) -> MeterListResponse:
    meters = portal_call(get_client(request).list_meters, page, limit)
    return MeterListResponse(
        meters=[MeterSummary(**meter) for meter in meters], page=page, limit=limit
    )


@app.get(
    "/api/v1/meters/{meter_id}",
    response_model=MeterDetails,
    responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    tags=["meters"],
)
def meter_details(request: Request, meter_id: str) -> MeterDetails:
    return MeterDetails(**portal_call(get_client(request).get_meter_details, meter_id))


@app.get(
    "/api/v1/meters/{meter_id}/consumption",
    response_model=list[ConsumptionRecord],
    responses={404: {"model": ErrorResponse}, 502: {"model": ErrorResponse}},
    tags=["consumption"],
)
def meter_consumption(
    request: Request,
    meter_id: str,
    limit: int = Query(default=100, ge=1, le=100),
) -> list[ConsumptionRecord]:
    records = portal_call(get_client(request).get_consumption, meter_id, limit)
    return [ConsumptionRecord(**record) for record in records]
