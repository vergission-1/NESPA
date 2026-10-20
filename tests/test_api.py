"""Behavioral checks for independent reception and honest task status."""
import time
from fastapi.testclient import TestClient
from nespa.app import create_app


def test_nonblocking_chat_and_progress(tmp_path):
    with TestClient(create_app(tmp_path / "nespa.db")) as client:
        task = client.post("/api/tasks", json={"title":"Demo","total_steps":8,"interval_ms":120}).json()
        tid = task["id"]
        start = time.monotonic()
        reply = client.post("/api/chat", json={"message":"当前进度？","task_id":tid})
        assert reply.status_code == 200
        assert time.monotonic() - start < 0.8
        assert client.get("/api/tasks/" + tid).json()["status"] in ("queued","running")
        saved = client.post("/api/chat",json={"message":"想到一个新的温控方案","task_id":tid})
        assert "保存" in saved.json()["reply"]
        assert client.get("/api/notes").json()[0]["task_id"] == tid
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and client.get("/api/tasks/" + tid).json()["status"] != "completed":
            time.sleep(0.05)
        assert client.get("/api/tasks/" + tid).json()["completed_steps"] == 8


def test_no_fabricated_research(tmp_path):
    with TestClient(create_app(tmp_path / "db.db")) as client:
        task = client.post("/api/tasks",json={"total_steps":5,"interval_ms":80}).json()
        reply = client.post("/api/chat",json={"message":"为什么这一步？","task_id":task["id"]}).json()
        assert "没有执行真实研究" in reply["reply"]


def test_invalid_references(tmp_path):
    with TestClient(create_app(tmp_path / "db.db")) as client:
        assert client.get("/api/tasks/missing/events").status_code == 404
        assert client.post("/api/notes",json={"content":"idea","task_id":"missing"}).status_code == 404


def test_restart_marks_interrupted(tmp_path):
    db = tmp_path / "restart.db"
    with TestClient(create_app(db)) as client:
        task = client.post("/api/tasks",json={"total_steps":50,"interval_ms":200}).json()
    with TestClient(create_app(db)) as client:
        assert client.get("/api/tasks/" + task["id"]).json()["status"] == "interrupted"
        assert client.get("/").status_code == 200
