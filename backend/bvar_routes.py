from fastapi import APIRouter, HTTPException
from . import bvar_data as bd

router = APIRouter(prefix="/bvar")


def _tag(src):
    if src not in ("precip", "soil"):
        raise HTTPException(400, "src must be precip or soil")
    return "" if src == "precip" else f"_{src}"


def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except bd.Missing as e:
        raise HTTPException(404, str(e))


@router.get("/map")
def bvar_map(src: str = "precip"):
    return _guard(bd.map_payload, tag=_tag(src))


@router.get("/cell")
def bvar_cell(lat: float, lon: float, src: str = "precip"):
    return _guard(bd.cell_payload, lat, lon, tag=_tag(src))


@router.get("/summary")
def bvar_summary(src: str = "precip"):
    return _guard(bd.summary_payload, tag=_tag(src))