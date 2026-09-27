from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Line

router = APIRouter(prefix="/lines", tags=["lines"])


class LineThresholds(BaseModel):
    planned_headway_min: float
    bunch_threshold: float
    large_threshold: float


def line_dict(r: Line) -> dict:
    return {"id": r.id, "code": r.code, "name": r.name, "planned_headway_min": r.planned_headway_min,
            "bunch_threshold": r.bunch_threshold, "large_threshold": r.large_threshold}


def validate_thresholds(p: LineThresholds) -> None:
    if p.planned_headway_min <= 0:
        raise HTTPException(400, "计划发车间隔必须大于 0")
    if p.bunch_threshold < 0 or p.large_threshold < 0:
        raise HTTPException(400, "阈值不能为负数")
    if p.bunch_threshold > p.large_threshold:
        raise HTTPException(400, "串车阈值不能大于大间隔阈值")


@router.get("")
def list_lines(db: Session = Depends(get_db)):
    rows = db.scalars(select(Line).order_by(Line.id)).all()
    return [line_dict(r) for r in rows]


@router.put("/{line_id}")
def update_line(line_id: int, payload: LineThresholds, db: Session = Depends(get_db)):
    line = db.get(Line, line_id)
    if not line:
        raise HTTPException(404, "线路不存在")
    validate_thresholds(payload)
    line.planned_headway_min = payload.planned_headway_min
    line.bunch_threshold = payload.bunch_threshold
    line.large_threshold = payload.large_threshold
    db.commit()
    db.refresh(line)
    return line_dict(line)
