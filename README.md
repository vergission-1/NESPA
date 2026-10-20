# NESPA — Neo-Study-Partner

**Think while your agents work.**

Nespa is an experimental workspace for uninterrupted human–AI collaboration. Its first milestone is intentionally small: keep Reception responsive while an independent Worker carries out a long task.

> **v0.1 is a proof of concept.** The Worker simulates progress; it does not actually analyze papers, execute research, or autonomously write software.

## Features

- Non-blocking Reception and simulated Worker
- Durable task progress, events, and ideas in SQLite
- Honest task-state explanations without invented reasoning
- Optional OpenAI-compatible chat endpoint (for example, DeepSeek)
- Automated behavioral tests

## Quick start

Requires Python 3.10+.

```powershell
git clone https://github.com/vergission-1/NESPA.git
cd NESPA
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m nespa
```

Open http://127.0.0.1:8000. No API key is needed for the demo.

### Optional model connection

Set the following environment variables before launching:

```powershell
$env:NESPA_LLM_API_KEY="your_api_key"
$env:NESPA_LLM_BASE_URL="https://api.deepseek.com/v1"
$env:NESPA_LLM_MODEL="deepseek-chat"
py -m nespa
```

An external model receives chat content and a brief task-state snapshot. Do not enter confidential project information without reviewing the provider's privacy policy. Never commit API keys.

## Tests

```powershell
py -m pip install -r requirements-dev.txt
py -m pytest -q
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/tasks` | Start demo work |
| `GET /api/tasks` | List saved work |
| `GET /api/tasks/{id}/events` | Read worker events |
| `POST /api/chat` | Ask Reception independently |
| `POST /api/notes` | Save ideas |
| `GET /api/notes` | Read ideas |

## Roadmap

0.1 Non-blocking chat + demo work → 0.2 task-aware chat and intent routing → 0.3 checkpoints and safe edits → 0.4 real isolated workers and review.

See [architecture](docs/architecture.md). MIT licensed.
