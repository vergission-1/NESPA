"""FastAPI application. REST reads never wait for a demonstration worker to finish."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .reception import Reception
from .knowledge import KnowledgeEngine
from .store import Store
from .worker import Worker


class NewTask(BaseModel):
    title: str = Field(default="文献初筛（模拟）", min_length=1, max_length=120)
    total_steps: int = Field(default=12, ge=2, le=100)
    interval_ms: int = Field(default=750, ge=50, le=10000)


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    task_id: str | None = None


class NoteInput(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    task_id: str | None = None


def create_app(db_path: str | Path | None = None) -> FastAPI:
    store = Store(db_path or os.getenv("NESPA_DB_PATH", "./data/nespa.db"))
    worker = Worker(store)
    reception = Reception(store)
    knowledge = KnowledgeEngine(store, os.getenv("NESPA_VAULT_PATH", "./vault"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.init()
        knowledge.init()
        watcher = __import__("asyncio").create_task(knowledge.watch())
        yield
        watcher.cancel()
        await __import__("asyncio").gather(watcher, return_exceptions=True)
        await worker.close()

    app = FastAPI(title="Nespa", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.worker = worker
    app.state.knowledge = knowledge

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": "0.1.0"}

    @app.get("/api/tasks")
    def tasks():
        return store.list_tasks()

    @app.post("/api/tasks", status_code=201)
    async def create_task(data: NewTask):
        task = store.create_task(data.title, data.total_steps, data.interval_ms)
        worker.start(task["id"])
        return task

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str):
        task = store.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @app.get("/api/tasks/{task_id}/events")
    def events(task_id: str):
        if not store.get_task(task_id):
            raise HTTPException(status_code=404, detail="Task not found")
        return store.events(task_id)

    @app.post("/api/chat")
    async def chat(data: ChatInput):
        if data.task_id and not store.get_task(data.task_id):
            raise HTTPException(status_code=404, detail="Task not found")
        return await reception.reply(data.message, data.task_id)

    @app.get("/api/knowledge/status")
    def knowledge_status():
        return knowledge.status()

    @app.post("/api/knowledge/sync")
    async def knowledge_sync():
        import asyncio
        return await asyncio.to_thread(knowledge.sync)

    @app.get("/api/knowledge/graph")
    def knowledge_graph():
        return knowledge.graph()

    @app.get("/api/knowledge/search")
    def knowledge_search(q: str = ""):
        return knowledge.search(q)

    @app.get("/knowledge")
    def knowledge_page():
        return FileResponse(static / "knowledge.html")

    @app.get("/api/notes")
    def notes():
        return store.list_notes()

    @app.post("/api/notes", status_code=201)
    def add_note(data: NoteInput):
        if data.task_id and not store.get_task(data.task_id):
            raise HTTPException(status_code=404, detail="Task not found")
        return store.add_note(data.content, data.task_id)

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    return app


app = create_app()
