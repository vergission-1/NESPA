"""Low-latency reception with transparent fallback and optional LLM."""

import os
import httpx
from .store import Store


class Reception:
    def __init__(self, store: Store):
        self.store = store

    async def reply(self, message: str, task_id: str | None) -> dict:
        task = self.store.get_task(task_id) if task_id else (self.store.list_tasks() or [None])[0]
        tid = task["id"] if task else None
        if any(word in message for word in ("记住", "灵感", "想法", "想到", "note", "remember")):
            note = self.store.add_note(message, tid)
            return {"reply": "我已保存这条灵感；不会修改当前 Worker 任务。", "mode": "local", "note_id": note["id"]}
        if any(word in message for word in ("进度", "状态", "做到哪", "完成了", "怎么样了", "status", "progress")):
            if not task:
                return {"reply": "目前没有任务。可以先点击『开始模拟任务』。", "mode": "local"}
            return {"reply": f"任务「{task['title']}」当前状态：{task['status']}；已完成 {task['completed_steps']}/{task['total_steps']} 步。", "mode": "local"}
        if any(word in message for word in ("为什么", "含义", "具体步骤", "解释", "这一步", "why")):
            if not task:
                return {"reply": "还没有正在跟踪的任务。", "mode": "local"}
            return {"reply": f"目前记录到 {task['completed_steps']}/{task['total_steps']} 步。这是并发机制演示，Worker 没有执行真实研究，因此我不能声称它作出了某项科研决策。可以在事件记录中核对实际步骤。", "mode": "local"}

        key = os.getenv("NESPA_LLM_API_KEY", "").strip()
        if key:
            model = os.getenv("NESPA_LLM_MODEL", "deepseek-chat")
            base = os.getenv("NESPA_LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
            events = self.store.events(tid, 8) if tid else []
            context = f"Current task snapshot: {task!r}; recent factual events: {events!r}."
            system = (
                "You are Nespa Reception, a research partner. Answer briefly in the user's language. "
                "Do not claim a simulated worker did actual research. Only treat explicit events as facts. "
                "Never infer hidden model reasoning. Proposals do not change ongoing tasks. " + context
            )
            try:
                async with httpx.AsyncClient(timeout=18) as client:
                    response = await client.post(
                        f"{base}/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": message}]},
                    )
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                return {"reply": content, "mode": "llm"}
            except (httpx.HTTPError, KeyError, IndexError, ValueError):
                return {"reply": "模型服务暂时不可用，但 Worker 仍独立运行。你可以询问『进度』或『为什么这一步』。", "mode": "local"}
        return {"reply": "我正在本地演示模式。可以问『当前进度？』『这一步什么意思？』，或说『我有个灵感……』。配置 .env 中的模型 API 后可进行开放式讨论。", "mode": "local"}
