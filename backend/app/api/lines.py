from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Line
router = APIRouter(prefix="/lines", tags=["lines"])

class LineUpdate(BaseModel):
    planned_headway_min: float
    bunch_threshold: float
    large_threshold: float

def line_dict(r: Line) -> dict:
    return {"id": r.id, "code": r.code, "name": r.name, "planned_headway_min": r.planned_headway_min,
            "bunch_threshold": r.bunch_threshold, "large_threshold": r.large_threshold}

@router.get("")
def list_lines(db: Session = Depends(get_db)):
    rows = db.scalars(select(Line).order_by(Line.id)).all()
    return [line_dict(r) for r in rows]

@router.put("/{line_id}")
def update_line(line_id: int, body: LineUpdate, db: Session = Depends(get_db)):
    line = db.get(Line, line_id)
    if not line: raise HTTPException(404, "线路不存在")
    if body.planned_headway_min <= 0:
        raise HTTPException(422, "计划发车间隔必须为正数")
    if body.bunch_threshold < 0 or body.large_threshold <= 0:
        raise HTTPException(422, "阈值不能为负，大间隔阈值必须为正数")
    if body.bunch_threshold > body.large_threshold:
        raise HTTPException(422, "串车阈值不能大于大间隔阈值")
    line.planned_headway_min = body.planned_headway_min
    line.bunch_threshold = body.bunch_threshold
    line.large_threshold = body.large_threshold
    db.commit(); db.refresh(line)
    return line_dict(line)
