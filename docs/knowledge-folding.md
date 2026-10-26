# Knowledge Folding v0.2 — design contract

This is an inspectable, local-first prototype built on the existing Nespa v0.1 branch. It is **not** autonomous research or a protein-folding model.

## Data flow

Obsidian/Markdown vault -> constrained filesystem scanner -> SHA-256 change detection -> SQLite documents and text index -> deterministic lexical feature vectors -> explicit wiki edges + optional similarity edges -> JSON endpoints -> fold/unfold browser graph.

The lexical hashing baseline supports English tokens and Chinese character bigrams. This is NOT semantic embedding; vectors have no model-trained understanding. Similarity links are retrieval suggestions only, never evidence of causal, scientific, or logical relations.

SQLite documents preserve path, source content, content hash, version and timestamps. Only the source Markdown files are authoritative. Document deletion from the vault deletes its current index record; external backups/version control remain the user's responsibility. A sync scans the whole vault, but only changed documents are re-vectorized. For simplicity the v0.2 link graph is rebuilt after changes, so large vaults need a later incremental edge rebuild.

## Endpoints
- `GET /api/knowledge/status`: counts, mode and sync diagnostics.
- `POST /api/knowledge/sync`: manually refresh local Markdown index.
- `GET /api/knowledge/graph`: read graph nodes/typed edges.
- `GET /api/knowledge/search?q=...`: source excerpts and similarity ranking; not synthesized answers.
- `GET /knowledge`: live graph browser with group folding.

## Security boundaries

Set `NESPA_VAULT_PATH` explicitly to a dedicated directory, not your whole home folder. The crawler skips hidden paths, rejects symlink escapes and files over 500 KB, caps scanning at 3000 .md files. This is a LOCAL development service; do not expose it to a public network without adding authentication, CSRF protection, access controls and secret management. The default server should bind localhost. Never put credentials in notes; a future cloud embedding backend will require deliberate consent before data transmission.

## Next milestone

Replace the lexical baseline behind a versioned `Embedder` interface, add a queued checkpointing worker, immutable evidence events, task-linked provisional claims, and proper hybrid FTS/vector search. Validate recall, retrieval accuracy and stability of clusters before calling the view knowledge folding in a scientific sense.
