from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.hatch.preprocessing import InvalidHatchImageError
from app.schemas.hatch_feature_set import ComputeFeaturesRequest, HatchFeatureSetResponse
from app.services.hatch_feature_service import (
    HatchFeatureService,
    LegendEntryNotConfirmedError,
    NoPatternCropError,
)
from app.services.legend_service import LegendEntryNotFoundError
from app.services.plan_service import PlanNotFoundError, PlanPageNotFoundError
from app.services.project_service import ProjectNotFoundError

router = APIRouter(
    prefix="/api/projects/{project_id}/plans/{plan_id}/legend-entries/{legend_entry_id}/features",
    tags=["hatch-features"],
)


def get_hatch_feature_service(db: Session = Depends(get_db)) -> HatchFeatureService:
    return HatchFeatureService(db)


def _not_found(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return HTTPException(status_code=404, detail="Project not found")
    if isinstance(exc, PlanNotFoundError):
        return HTTPException(status_code=404, detail="Plan not found")
    if isinstance(exc, PlanPageNotFoundError):
        return HTTPException(status_code=404, detail="Page not found")
    return HTTPException(status_code=404, detail="Legend entry not found")


@router.post("", response_model=HatchFeatureSetResponse, status_code=status.HTTP_201_CREATED)
async def compute_hatch_features(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    payload: ComputeFeaturesRequest = ComputeFeaturesRequest(),
    service: HatchFeatureService = Depends(get_hatch_feature_service),
) -> HatchFeatureSetResponse:
    try:
        return service.compute_features(  # type: ignore[return-value]
            project_id, plan_id, legend_entry_id, force=payload.force
        )
    except (ProjectNotFoundError, PlanNotFoundError, PlanPageNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    except LegendEntryNotConfirmedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NoPatternCropError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InvalidHatchImageError as exc:
        # Never leak a raw OpenCV/numpy stack trace to the API caller --
        # this is the one controlled, documented failure mode for a crop
        # that exists but cannot be analyzed.
        raise HTTPException(status_code=400, detail=f"Pattern crop is not a usable image: {exc}") from exc


@router.get("", response_model=HatchFeatureSetResponse)
async def get_hatch_features(
    project_id: uuid.UUID,
    plan_id: uuid.UUID,
    legend_entry_id: uuid.UUID,
    service: HatchFeatureService = Depends(get_hatch_feature_service),
) -> HatchFeatureSetResponse:
    try:
        result = service.get_features(project_id, plan_id, legend_entry_id)
    except (ProjectNotFoundError, PlanNotFoundError, PlanPageNotFoundError, LegendEntryNotFoundError) as exc:
        raise _not_found(exc) from exc
    if result is None:
        # A plain GET never triggers computation -- an entry that is
        # confirmed but has no feature set yet (or isn't confirmed at
        # all) simply has nothing to return.
        raise HTTPException(status_code=404, detail="No hatch features computed for this legend entry yet")
    return result  # type: ignore[return-value]
