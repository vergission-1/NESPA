"""Local-first Obsidian knowledge index and inspectable graph.

The default feature vectors are deterministic *lexical hashes*, NOT a learned
embedding model. Edges marked "similarity" suggest retrieval associations,
not scientific or causal claims. No vault content leaves this machine.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import threading
from collections import Counter
from pathlib import Path

from .store import Store, utc_now

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
TOKENS = re.compile(r"[a-zA-Z0-9_]{2,}|[\u3400-\u9fff]")
CJK = re.compile(r"[\u3400-\u9fff]+")
VECTOR_DIMS = 256
MAX_FILE_BYTES = 512_000
MAX_FILES = 3000


def features(text: str) -> list[str]:
    """Word features for Latin text, character bigrams for CJK text."""
    text = text.lower()
    tokens = TOKENS.findall(text)
    for chunk in CJK.findall(text):
        if len(chunk) > 1:
            tokens.extend(chunk[i:i + 2] for i in range(len(chunk) - 1))
    return tokens


def lexical_vector(text: str) -> list[float]:
    counts = Counter(features(text[:40_000]))
    out = [0.0] * VECTOR_DIMS
    for term, count in counts.items():
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=4).digest()
        bucket = int.from_bytes(digest[:2], "big") % VECTOR_DIMS
        # Log-scaled positive counts: this is a lexical baseline, not an LLM embedding.
        out[bucket] += 1.0 + math.log(count)
    norm = math.sqrt(sum(v * v for v in out))
    return [v / norm for v in out] if norm else out


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def snippet(text: str, q: str, size: int = 230) -> str:
    pos = text.casefold().find(q.casefold())
    if pos < 0:
        pos = 0
    start = max(0, pos - 55)
    return text[start:start + size].replace("\n", " ").strip()


class KnowledgeEngine:
    def __init__(self, store: Store, vault: str | Path):
        self.store = store
        self.vault = Path(vault).expanduser().resolve()
        self._lock = threading.Lock()
        self._syncing = False
        self._last_scan: str | None = None
        self._last_error: str | None = None
        self._changed = 0

    def init(self) -> None:
        self.vault.mkdir(parents=True, exist_ok=True)
        with self.store.connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_edges (
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    weight REAL NOT NULL,
                    PRIMARY KEY (source,target,kind)
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_edges_target ON knowledge_edges(target);
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
                USING fts5(id UNINDEXED, title, body, tokenize='unicode61');
            """)

    def _files(self):
        count = 0
        for path in sorted(self.vault.rglob("*.md")):
            if path.is_symlink() or any(x.startswith(".") for x in path.relative_to(self.vault).parts):
                continue
            # Do not follow a symlinked parent directory outside the approved vault.
            if not path.resolve().is_relative_to(self.vault) or not path.is_file():
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            count += 1
            if count > MAX_FILES:
                raise ValueError(f"Vault contains more than {MAX_FILES} eligible Markdown files")
            yield path

    def sync(self) -> dict:
        if not self._lock.acquire(blocking=False):
            return self.status()
        self._syncing = True
        changed = 0
        try:
            entries = []
            for file in self._files():
                rel = file.relative_to(self.vault).as_posix()
                content = file.read_text(encoding="utf-8-sig")
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                entries.append((rel, content, digest))
            now = utc_now()
            with self.store.connect() as con:
                known = {r["path"]: dict(r) for r in con.execute(
                    "SELECT id,path,digest,version FROM knowledge_documents"
                )}
                seen = set()
                for rel, content, digest in entries:
                    seen.add(rel)
                    if rel in known and known[rel]["digest"] == digest:
                        continue
                    doc_id = hashlib.sha256(rel.encode("utf-8")).hexdigest()[:20]
                    title = Path(rel).stem
                    vec = json.dumps(lexical_vector(title + " " + content))
                    version = known[rel]["version"] + 1 if rel in known else 1
                    con.execute("""
                        INSERT INTO knowledge_documents (id,path,title,body,digest,vector_json,version,updated_at)
                        VALUES (?,?,?,?,?,?,?,?)
                        ON CONFLICT(path) DO UPDATE SET title=excluded.title,
                            body=excluded.body,digest=excluded.digest,
                            vector_json=excluded.vector_json,version=excluded.version,
                            updated_at=excluded.updated_at
                    """, (doc_id, rel, title, content, digest, vec, version, now))
                    con.execute("DELETE FROM knowledge_fts WHERE id=?", (doc_id,))
                    con.execute("INSERT INTO knowledge_fts(id,title,body) VALUES (?,?,?)", (doc_id, title, content))
                    changed += 1
                removed = set(known) - seen
                for rel in removed:
                    doc_id = known[rel]["id"]
                    con.execute("DELETE FROM knowledge_documents WHERE id=?", (doc_id,))
                    con.execute("DELETE FROM knowledge_fts WHERE id=?", (doc_id,))
                    changed += 1
                if changed:
                    self._rebuild_edges(con)
            self._last_error = None
            self._last_scan = now
            self._changed = changed
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
        finally:
            self._syncing = False
            self._lock.release()
        return self.status()

    @staticmethod
    def _rebuild_edges(con):
        rows = [dict(r) for r in con.execute(
            "SELECT id,path,title,body,vector_json FROM knowledge_documents ORDER BY path"
        )]
        con.execute("DELETE FROM knowledge_edges")
        by_path = {Path(r["path"]).with_suffix("").as_posix().casefold(): r["id"] for r in rows}
        title_lists: dict[str, list[str]] = {}
        for r in rows:
            title_lists.setdefault(r["title"].casefold(), []).append(r["id"])
        for r in rows:
            for raw in WIKILINK.findall(r["body"]):
                target_name = raw.split("|", 1)[0].split("#", 1)[0].strip().removesuffix(".md")
                target = by_path.get(target_name.casefold())
                if target is None:
                    candidates = title_lists.get(Path(target_name).name.casefold(), [])
                    if len(candidates) == 1:
                        target = candidates[0]
                if target and target != r["id"]:
                    con.execute("INSERT OR IGNORE INTO knowledge_edges VALUES (?,?,?,?)",
                                (r["id"], target, "wikilink", 1.0))
        vectors = {r["id"]: json.loads(r["vector_json"]) for r in rows}
        for row in rows:
            ranked = sorted(
                ((cosine(vectors[row["id"]], vectors[other["id"]]), other["id"])
                 for other in rows if other["id"] != row["id"]),
                reverse=True,
            )
            for score, target in ranked[:3]:
                if score >= 0.27:
                    src, dst = sorted((row["id"], target))
                    con.execute("INSERT OR REPLACE INTO knowledge_edges VALUES (?,?,?,?)",
                                (src, dst, "lexical_similarity", round(score, 4)))

    def status(self) -> dict:
        with self.store.connect() as con:
            docs = con.execute("SELECT count(*) FROM knowledge_documents").fetchone()[0]
            edges = con.execute("SELECT count(*) FROM knowledge_edges").fetchone()[0]
        return {
            "index_mode": "hashed_lexical_baseline",
            "embedding_model_loaded": False,
            "syncing": self._syncing,
            "last_scan": self._last_scan,
            "last_error": self._last_error,
            "changed_in_last_scan": self._changed,
            "documents": docs,
            "edges": edges,
            "vault": str(self.vault),
        }

    def graph(self) -> dict:
        with self.store.connect() as con:
            docs = [dict(r) for r in con.execute(
                "SELECT id,path,title,body,version,updated_at FROM knowledge_documents ORDER BY path LIMIT 3000"
            )]
            edges = [dict(r) for r in con.execute(
                "SELECT source,target,kind,weight FROM knowledge_edges ORDER BY kind,source,target"
            )]
        return {
            "nodes": [{
                "id": d["id"],
                "title": d["title"],
                "path": d["path"],
                "group": d["path"].split("/")[0] if "/" in d["path"] else "Unsorted",
                "status": "indexed",
                "version": d["version"],
                "updated_at": d["updated_at"],
                "excerpt": snippet(d["body"], "", 280),
            } for d in docs],
            "edges": edges,
            "index_mode": "hashed_lexical_baseline",
        }

    def search(self, query: str, limit: int = 8) -> dict:
        query = query.strip()[:500]
        if not query:
            return {"query": query, "results": [], "answer": "请先输入需要检索的问题。"}
        qvec = lexical_vector(query)
        qtokens = set(features(query))
        with self.store.connect() as con:
            rows = [dict(r) for r in con.execute(
                "SELECT id,path,title,body,vector_json,version,updated_at FROM knowledge_documents"
            )]
        ranked = []
        for row in rows:
            vec_score = cosine(qvec, json.loads(row["vector_json"]))
            title_boost = 0.25 if query.casefold() in row["title"].casefold() else 0
            matched = len(qtokens & set(features(row["title"] + " " + row["body"][:25_000])))
            word_score = min(0.2, matched * 0.035)
            score = vec_score + title_boost + word_score
            if score > 0.025:
                ranked.append((score, row))
        ranked.sort(key=lambda pair: (-pair[0], pair[1]["path"]))
        results = [{
            "id": row["id"], "title": row["title"], "path": row["path"],
            "version": row["version"], "score": round(score, 4),
            "excerpt": snippet(row["body"], query),
            "evidence_state": "source_text_not_verified",
        } for score, row in ranked[:max(1, min(limit, 20))]]
        answer = ("检索到以下本地笔记片段；这不是模型生成的研究结论，请打开原文核对。"
                  if results else "尚未在已索引的本地笔记中找到匹配证据。")
        return {"query": query, "results": results, "answer": answer}

    async def watch(self, seconds: int = 10) -> None:
        while True:
            await asyncio.sleep(seconds)
            try:
                await asyncio.to_thread(self.sync)
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
