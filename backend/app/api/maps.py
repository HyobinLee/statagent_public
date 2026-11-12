from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.errors import success_response
from app.dependencies import get_current_user
from app.models.user import User
from app.services.color_scales import (
    DEFAULT_SCALE,
    MAX_CLASSES,
    MIN_CLASSES,
    SCALE_TYPE_HINTS,
    SCALE_TYPE_LABELS,
    list_scales,
)
from app.services.map_service import MapService

router = APIRouter(prefix="/api/maps", tags=["maps"])


class ChoroplethRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1)
    region_column: str = Field(..., min_length=1)
    value_column: str = Field(..., min_length=1)
    level: str = Field(default="sido", pattern="^(sido|sigungu|emd)$")
    parent_region: str | None = Field(default=None, max_length=60)
    time_column: str | None = Field(default=None, max_length=80)
    time_point: str | None = Field(default=None, max_length=40)
    n_classes: int = Field(default=5, ge=3, le=7)
    color_scale: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=120)


class RegionLookupRequest(BaseModel):
    region_names: list[str] = Field(..., min_length=1, max_length=500)
    level: str = Field(default="sido", pattern="^(sido|sigungu|emd)$")


@router.get("/levels")
def map_levels(_user: User = Depends(get_current_user)) -> dict:
    levels = MapService().available_map_levels()
    return success_response(levels, {"count": len(levels)})


@router.get("/color-scales")
def map_color_scales(
    n_classes: int = 5,
    _user: User = Depends(get_current_user),
) -> dict:
    scales = list_scales(min(max(n_classes, MIN_CLASSES), MAX_CLASSES))
    groups = [
        {
            "type": kind,
            "type_label": SCALE_TYPE_LABELS[kind],
            "type_hint": SCALE_TYPE_HINTS[kind],
            "scales": [scale for scale in scales if scale["type"] == kind],
        }
        for kind in ("sequential", "diverging")
    ]
    return success_response(groups, {"count": len(scales), "default": DEFAULT_SCALE})


@router.get("/regions")
def map_child_regions(
    level: str = "sido",
    parent_region: str | None = None,
    _user: User = Depends(get_current_user),
) -> dict:
    regions = MapService().child_regions(level, parent_region)
    return success_response(regions, {"count": len(regions), "level": level})


@router.post("/choropleth")
def generate_choropleth(
    payload: ChoroplethRequest,
    _user: User = Depends(get_current_user),
) -> dict:
    result = MapService().generate_choropleth(
        dataset_id=payload.dataset_id,
        region_column=payload.region_column,
        value_column=payload.value_column,
        level=payload.level,
        parent_region=payload.parent_region,
        time_column=payload.time_column,
        time_point=payload.time_point,
        n_classes=payload.n_classes,
        color_scale=payload.color_scale,
        title=payload.title,
    )
    return success_response(result)


@router.post("/region-lookup")
def region_lookup(
    payload: RegionLookupRequest,
    _user: User = Depends(get_current_user),
) -> dict:
    result = MapService().region_code_lookup(
        region_names=payload.region_names,
        level=payload.level,
    )
    return success_response(result)
