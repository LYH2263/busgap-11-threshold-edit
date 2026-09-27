from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Arrival, Line, Trip


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # 与 seed.py 一致的数据：市民中心 T01→T02 实际间隔 2 分钟
    db = TestingSessionLocal()
    base = datetime(2026, 9, 17, 7, 0, 0)
    line = Line(code="B12", name="城东环线", planned_headway_min=8.0, bunch_threshold=3.0, large_threshold=15.0)
    db.add(line); db.flush()
    specs = [("T01", "粤A1001", 0), ("T02", "粤A1002", 2), ("T03", "粤A1003", 18), ("T04", "粤A1004", 26)]
    stops = ["起点站", "市民中心", "火车站", "终点站"]
    for trip_no, vehicle, offset in specs:
        trip = Trip(line_id=line.id, trip_no=trip_no, planned_depart=base + timedelta(minutes=offset), vehicle_no=vehicle)
        db.add(trip); db.flush()
        for seq, stop in enumerate(stops):
            arrive = base + timedelta(minutes=offset + seq * 6)
            if stop == "市民中心" and trip_no == "T02":
                arrive = base + timedelta(minutes=8)
            if stop == "火车站" and trip_no == "T03":
                arrive = base + timedelta(minutes=30)
            db.add(Arrival(trip_id=trip.id, stop_name=stop, stop_seq=seq, actual_arrive=arrive))
    db.commit(); db.close()

    def override_get_db():
        s = TestingSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)  # 不用 with，避免 lifespan 连接真实数据库
    app.dependency_overrides.clear()


def put_line(client, planned=8.0, bunch=3.0, large=15.0, line_id=1):
    return client.put(f"/api/lines/{line_id}", json={
        "planned_headway_min": planned, "bunch_threshold": bunch, "large_threshold": large})


def civic_center_gap2(client):
    r = client.post("/api/reports/run", params={"line_id": 1, "stop_name": "市民中心"})
    assert r.status_code == 200
    return [e for e in r.json()["events"] if e["earlier_trip"] == "T01" and e["later_trip"] == "T02"]


def test_update_line_persists(client):
    r = put_line(client, planned=10.0, bunch=2.0, large=20.0)
    assert r.status_code == 200
    assert r.json()["planned_headway_min"] == 10.0
    got = client.get("/api/lines").json()  # 离开再进重新拉取
    assert got[0]["planned_headway_min"] == 10.0
    assert got[0]["bunch_threshold"] == 2.0
    assert got[0]["large_threshold"] == 20.0


def test_update_missing_line(client):
    assert put_line(client, line_id=999).status_code == 404


def test_detection_uses_new_thresholds(client):
    assert civic_center_gap2(client)[0]["status"] == "bunching"  # 默认阈值 3.0，间隔 2 分钟

    assert put_line(client, bunch=1.5).status_code == 200  # 放宽阈值
    assert civic_center_gap2(client)[0]["status"] == "normal"

    assert put_line(client, bunch=5.0).status_code == 200  # 收紧阈值
    assert civic_center_gap2(client)[0]["status"] == "bunching"


def test_threshold_change_keeps_old_reports(client):
    client.post("/api/reports/run", params={"line_id": 1})
    before = client.get("/api/reports").json()
    assert put_line(client, bunch=1.5).status_code == 200
    assert len(client.get("/api/reports").json()) == len(before)  # 改阈值不清旧报告
    client.post("/api/reports/run", params={"line_id": 1, "stop_name": "市民中心"})
    latest = client.get("/api/reports").json()[0]
    gap2 = [e for e in latest["events"] if e["earlier_trip"] == "T01" and e["later_trip"] == "T02"]
    assert gap2[0]["status"] == "normal"  # 新检测按新阈值


@pytest.mark.parametrize("planned,bunch,large", [
    (8.0, 20.0, 15.0),   # 串车阈值 > 大间隔阈值
    (-5.0, 3.0, 15.0),   # 计划间隔为负
    (0.0, 3.0, 15.0),    # 计划间隔为零
    (8.0, -1.0, 15.0),   # 串车阈值为负
    (8.0, 3.0, -15.0),   # 大间隔阈值为负
])
def test_invalid_update_rejected(client, planned, bunch, large):
    r = put_line(client, planned=planned, bunch=bunch, large=large)
    assert r.status_code in (400, 422)
    got = client.get("/api/lines").json()[0]  # 数值保持改前
    assert got["planned_headway_min"] == 8.0
    assert got["bunch_threshold"] == 3.0
    assert got["large_threshold"] == 15.0
