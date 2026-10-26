"""Knowledge indexing does not require a model service or a network connection."""
from fastapi.testclient import TestClient
from nespa.app import create_app


def test_vault_sync_search_links_and_revision(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Temperature.md").write_text("PT100 sensing uses [[ITO]] heaters.", encoding="utf-8")
    (vault / "ITO.md").write_text("ITO heater current control.", encoding="utf-8")
    monkeypatch.setenv("NESPA_VAULT_PATH", str(vault))
    with TestClient(create_app(tmp_path / "test.db")) as client:
        status = client.post("/api/knowledge/sync").json()
        assert status["documents"] == 2
        g = client.get("/api/knowledge/graph").json()
        assert len(g["nodes"]) == 2
        assert any(e["kind"] == "wikilink" for e in g["edges"])
        hits = client.get("/api/knowledge/search", params={"q":"PT100"}).json()["results"]
        assert hits and hits[0]["title"] == "Temperature"
        assert client.post("/api/knowledge/sync").json()["changed_in_last_scan"] == 0
        (vault / "Temperature.md").write_text("Updated PT100 experiment [[ITO]].", encoding="utf-8")
        assert client.post("/api/knowledge/sync").json()["changed_in_last_scan"] == 1
        assert next(n for n in client.get("/api/knowledge/graph").json()["nodes"] if n["title"] == "Temperature")["version"] == 2
        (vault / "ITO.md").unlink()
        assert client.post("/api/knowledge/sync").json()["documents"] == 1
        assert client.get("/knowledge").status_code == 200


def test_no_results_are_not_invented(tmp_path, monkeypatch):
    monkeypatch.setenv("NESPA_VAULT_PATH", str(tmp_path / "vault"))
    with TestClient(create_app(tmp_path / "db.db")) as client:
        data = client.get("/api/knowledge/search", params={"q":"unrecorded result"}).json()
        assert data["results"] == []
        assert "尚未" in data["answer"]
