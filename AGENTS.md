# commutr-AI

## What this is

`commutr-AI` is Commutr's local, Ollama-powered assistant for answering operational questions against the Commutr API. It authenticates as a manager, then exposes read-only API tools for schedules, trip assignments, drivers and conductors, vehicles, boarding, bookings, and reports. It is one part of the Commutr provincial bus booking and operations platform for the Philippines: sibling repositories contain the Flutter mobile app, Go API backend, Next.js web admin, infrastructure, and the broader AI-assistant work.

## Run and test

- See [README.md](README.md) for prerequisites and the command-line workflow. Copy `.env.example` to `.env`; this repo loads that file itself. It needs a reachable Commutr API, Ollama, and an installed model.
- Run the CLI with `python -m agent -i`, or send a one-shot question with `python -m agent "..."`. The entry point is `agent.py:main`.
- Run the HTTP server with `./start.sh`; it uses `.venv`, writes `.server.pid` and `server.log`, and checks `GET /health`. Use `./stop.sh` to stop it. `./commutr-ai.sh` starts the server if needed and opens the interactive HTTP client.
- Run tests with `python -m pytest tests/ -v`. Test dependencies are the `dev` optional dependencies in `pyproject.toml`.
- There is no build target, container configuration, CI workflow, or deployment automation in this repository. `docs/deployment-specs.md` only records machine-sizing guidance; do not treat it as a deployment procedure.

## Layout

- `agent.py` — CLI, system prompt, Ollama conversation/tool-calling loop, and tool dispatch.
- `tools.py` — API wrappers. Their public functions are deliberately GET-only.
- `auth.py` — API login, refresh, and token cache management.
- `server.py` — FastAPI wrapper for dashboard integration (`/health`, `/ask`, and `/ask/stream`).
- `start.sh`, `stop.sh`, `commutr-ai.sh` — local HTTP-server lifecycle and interactive client.
- `tests/test_agent.py` — regression tests for tool mapping, read-only enforcement, API errors, adaptive prompt, and result compacting.

## Conventions and gotchas

- Preserve the read-only boundary: `tools.py` must not gain mutation methods. Authentication itself uses POST only for login/refresh; the query wrappers only use GET.
- Keep credentials in ignored `.env`; never commit it. JWTs are cached outside the repo at `~/.commutr/token.json` with mode `600`.
- The default API base is `http://localhost:8080`; `.env` may override it with `COMMUTR_API_BASE`. `OLLAMA_MODEL` and the other Ollama tuning variables are read from the environment; see `.env.example` and `agent.py`.
- `start.sh` requires an already-created `.venv` and binds to `127.0.0.1:8765` by default. `COMMUTR_AGENT_HOST` and `COMMUTR_AGENT_PORT` override that. Do not deploy it exposed to a network without making the security decision outside this repo: the FastAPI CORS policy currently allows all origins.
- Although `pyproject.toml` declares a `commutr-agent` console script, editable installation currently fails because setuptools auto-discovery rejects the flat multi-module layout. Use the module commands above unless packaging configuration is fixed separately.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
