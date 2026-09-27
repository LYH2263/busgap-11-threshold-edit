from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Arrival, Line, Trip

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SessionTest = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db():
    db = SessionTest()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def db_setup():
    Base.metadata.create_all(bind=engine)
    db = SessionTest()
    line = Line(code="B12", name="城东环线", planned_headway_min=8.0, bunch_threshold=3.0, large_threshold=15.0)
    db.add(line)
    db.flush()
    base = datetime(2026, 9, 17, 7, 0, 0)
    # 市民中心到站时刻：间隔 2 / 16 / 8 分钟
    for trip_no, off in {"T01": 6, "T02": 8, "T03": 24, "T04": 32}.items():
        t = Trip(line_id=line.id, trip_no=trip_no, planned_depart=base)
        db.add(t)
        db.flush()
        db.add(Arrival(trip_id=t.id, stop_name="市民中心", stop_seq=1,
                       actual_arrive=base + timedelta(minutes=off)))
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


def put_line(line_id, headway, bunch, large):
    return client.put(f"/api/lines/{line_id}", json={
        "planned_headway_min": headway, "bunch_threshold": bunch, "large_threshold": large})


def get_line(line_id=1):
    return next(x for x in client.get("/api/lines").json() if x["id"] == line_id)


def run_statuses():
    events = client.post("/api/reports/run?line_id=1").json()["events"]
    return [e["status"] for e in events if e["stop_name"] == "市民中心"]


def test_update_thresholds_persists():
    r = put_line(1, 10.0, 4.0, 18.0)
    assert r.status_code == 200
    line = get_line()
    assert line["planned_headway_min"] == 10.0
    assert line["bunch_threshold"] == 4.0
    assert line["large_threshold"] == 18.0


def test_reject_bunch_greater_than_large():
    assert put_line(1, 8.0, 20.0, 15.0).status_code == 400
    line = get_line()
    assert line["bunch_threshold"] == 3.0
    assert line["large_threshold"] == 15.0


def test_reject_negative_headway():
    assert put_line(1, -5.0, 3.0, 15.0).status_code == 400
    assert get_line()["planned_headway_min"] == 8.0


def test_reject_negative_threshold():
    assert put_line(1, 8.0, -1.0, 15.0).status_code == 400
    assert put_line(1, 8.0, 3.0, -15.0).status_code == 400
    line = get_line()
    assert line["bunch_threshold"] == 3.0
    assert line["large_threshold"] == 15.0


def test_update_missing_line_404():
    assert put_line(999, 8.0, 3.0, 15.0).status_code == 404


def test_detection_uses_saved_thresholds():
    # 默认 3/15：间隔 2 串车、16 大间隔、8 正常
    assert run_statuses() == ["bunching", "large_gap", "normal"]

    # 放宽串车阈值到 1：市民中心原串车变为正常
    assert put_line(1, 8.0, 1.0, 15.0).status_code == 200
    assert run_statuses() == ["normal", "large_gap", "normal"]

    # 收紧到 5：原串车仍为串车
    assert put_line(1, 8.0, 5.0, 15.0).status_code == 200
    assert run_statuses() == ["bunching", "large_gap", "normal"]

    # 收紧到 10：串车更多（间隔 8 也判为串车）
    assert put_line(1, 8.0, 10.0, 15.0).status_code == 200
    assert run_statuses() == ["bunching", "large_gap", "bunching"]


def test_reports_accumulate_and_survive_threshold_change():
    client.post("/api/reports/run?line_id=1")
    assert put_line(1, 8.0, 1.0, 15.0).status_code == 200
    client.post("/api/reports/run?line_id=1")
    reports = client.get("/api/reports").json()
    assert len(reports) == 2  # 改阈值不清旧报告
    newest, oldest = reports[0], reports[1]  # 列表按 id 倒序
    assert "bunching" in [e["status"] for e in oldest["events"]]
    assert "bunching" not in [e["status"] for e in newest["events"]]
