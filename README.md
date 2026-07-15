# Commutr AI Agent

Local Ollama-powered AI agent for read-only Commutr API queries. Zero cloud cost — all inference runs on your machine.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Your Terminal                             │
│                                                                  │
│   $ python -m agent "show me drivers on schedule 42"            │
│                                                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  agent.py                                                        │
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │  System      │   │  Tool-calling│   │  Tool dispatch       │ │
│  │  Prompt       │──▶│  loop        │──▶│  (read-only)         │ │
│  │  (Commutr    │   │  (max 8      │   │                      │ │
│  │   concepts)  │   │   turns)     │   │  get_schedules       │ │
│  └──────────────┘   └──────┬───────┘   │  get_trip_assignments│ │
│                            │           │  get_users           │ │
│                            ▼           │  get_vehicles        │ │
│                     ┌──────────────┐   │  get_boarding_manifest│ │
│                     │  Ollama      │   │  get_admin_bookings  │ │
│                     │  qwen2.5:7b  │   │  get_reports_revenue │ │
│                     │  (local)     │   │  ...16 tools total   │ │
│                     └──────────────┘   └──────────┬───────────┘ │
│                                                    │             │
└────────────────────────────────────────────────────┼─────────────┘
                                                     │
                                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  tools.py                                                        │
│                                                                  │
│  api_get(path, params) ──▶ requests.get(url, Bearer token)       │
│                                                                  │
│  Only GET is possible. POST, PUT, DELETE are excluded.           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  auth.py                                                         │
│                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │  Login          │    │  Token cache    │                     │
│  │  POST /auth/    │───▶│  ~/.commutr/    │                     │
│  │  login          │    │  token.json     │                     │
│  │                 │    │  (chmod 600)    │                     │
│  └─────────────────┘    └────────┬────────┘                     │
│                                  │                               │
│  Token lifecycle:                │                               │
│  1. Check cache → valid? ────────┘                               │
│  2. Expired → try refresh → POST /auth/refresh                   │
│  3. Refresh fails → re-login → POST /auth/login                  │
│                                                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Commutr Go API (localhost:8080)                                 │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Auth        │  │  Schedules  │  │  Trip Assignments      │  │
│  │  middleware  │  │  /api/v1/   │  │  /api/v1/trips/        │  │
│  │  JWT HMAC    │  │  schedules  │  │  assignments           │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Users      │  │  Vehicles   │  │  Boarding / Bookings    │  │
│  │  /api/v1/   │  │  /api/v1/   │  │  /api/v1/boarding/      │  │
│  │  users      │  │  vehicles   │  │  /api/v1/admin/bookings │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                                                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  PostgreSQL │
                    └─────────────┘
```

### Component stack

| Layer | File | Responsibility |
|---|---|---|
| CLI / interactive loop | `agent.py` | Parse user input, run Ollama conversation, dispatch tool calls, format output |
| System prompt | `agent.py:SYSTEM_PROMPT` | Teach the model Commutr terminology (schedule vs assignment, status values, role, route) |
| Tool definitions | `agent.py:TOOL_DEFINITIONS` | Ollama function-calling schema for 16 read-only API endpoints |
| Tool dispatch | `agent.py:TOOL_DISPATCH` | Map tool names to `tools.py` functions, catch API errors |
| API wrappers | `tools.py` | Typed `requests.get` calls with JWT auth, timeout, error mapping |
| Auth manager | `auth.py` | Login → cache JWT → auto-refresh → re-login on expiry |
| Token storage | `~/.commutr/token.json` | Cached JWT with `chmod 600`, expires in 24h |

### Data flow (per query)

```
1. User types a question
2. agent.py sends question + system prompt to Ollama
3. Ollama decides which tool(s) to call and with what arguments
4. agent.py dispatches each tool call → tools.py
5. tools.py gets a valid JWT from auth.py → calls Commutr Go API
6. Go API validates JWT, enforces company scope, runs PostgreSQL query
7. JSON response flows back: tools.py → agent.py → Ollama
8. Ollama synthesizes a natural language answer from the JSON
9. agent.py prints the answer
```

### Security model

```
┌──────────────────────────────────────────────────────────────┐
│  Architecture-level enforcement                              │
│                                                              │
│  tools.py: only GET is callable — no POST/PUT/DELETE exist  │
│  auth.py:   JWT stored with chmod 600 outside the repo      │
│  agent.py:  no mutation tools in TOOL_DISPATCH              │
│  Ollama:    runs locally — zero data exfiltration           │
│  Go API:    JWT + RBAC + company scope on every request     │
│                                                              │
│  The agent cannot mutate state even if the model             │
│  hallucinates a POST request — the code path doesn't exist. │
└──────────────────────────────────────────────────────────────┘
```

## Prerequisites

| Dependency | How to check | Install |
|---|---|---|
| Python 3.11+ | `python3 --version` | `brew install python@3.14` |
| Ollama | `ollama --version` | `brew install ollama` |
| Ollama model | `ollama list` | `ollama pull qwen2.5:7b` |
| Commutr Go API | `curl localhost:8080/health` | `cd src/backend-go && go run ./cmd/api` |

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/darelleluntao/commutr-AI.git
cd commutr-AI

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install ollama requests

# Run tests (optional)
pip install pytest pytest-mock
python -m pytest tests/ -v
```

### 2. Install Ollama and pull the model

```bash
# macOS
brew install ollama
brew services start ollama

# Pull the recommended model (~4.7GB, good function calling)
ollama pull qwen2.5:7b

# Verify
ollama list
```

### 3. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` with your Commutr API credentials:

```bash
# .env
COMMUTR_API_BASE=http://localhost:8080
COMMUTR_EMAIL=your-manager@buscompany.com
COMMUTR_PASSWORD=your-password

# Optional: use a different model
# OLLAMA_MODEL=llama3.2
```

> The agent caches the JWT in `~/.commutr/token.json` (chmod 600) and auto-refreshes before expiry.

### 4. Start the Commutr API

```bash
cd src/backend-go
go run ./cmd/api
```

Verify it's running:

```bash
curl http://localhost:8080/health
# → {"status":"ok"}
```

### 5. Run the agent

```bash
cd commutr-AI
source .venv/bin/activate

# Interactive mode
python -m agent -i

# Or one-shot queries
python -m agent "show me drivers assigned to schedule 42"
```

## Usage

### One-shot queries

```bash
python -m agent "show me drivers assigned to schedule 42"
python -m agent "list active schedules for today"
python -m agent "how many bookings on schedule 42"
python -m agent "which vehicles are currently assigned"
python -m agent "show the manifest for trip assignment 15"
python -m agent "what trips did driver John take this week"
python -m agent "show me all routes from Manila"
python -m agent "what's the revenue for this month"
```

### Interactive mode

```bash
python -m agent -i
# or
python -m agent --interactive
```

```
Commutr AI Agent [model: qwen2.5:7b]
API: http://localhost:8080
Type your question or "exit".

> show me drivers assigned to schedule 42

Schedule 42 (Manila → Baguio, 2026-07-16)
Driver: Juan Dela Cruz
Conductor: Pedro Santos
Vehicle: ABC-1234
Status: in_progress

> exit
```

### Override model

```bash
python -m agent --model llama3.2 "show all drivers"
```

Configure the default model in `.env`:

```bash
OLLAMA_MODEL=llama3.2
```

## Available tools

### Schedules & routes

| Tool | API endpoint | Parameters |
|---|---|---|
| `get_schedules` | `GET /schedules` | `route_id`, `date`, `status`, `limit` |
| `get_schedule` | `GET /schedules/{id}` | `schedule_id` (required) |
| `get_schedule_bookings` | `GET /schedules/{id}/bookings` | `schedule_id` (required) |
| `get_routes` | `GET /routes` | — |
| `get_route` | `GET /routes/{id}` | `route_id` (required) |

### Trip assignments

| Tool | API endpoint | Parameters |
|---|---|---|
| `get_trip_assignments` | `GET /trips/assignments` | `schedule_id`, `vehicle_id`, `driver_id`, `conductor_id`, `status` |
| `get_trip_assignment` | `GET /trips/assignments/{id}` | `assignment_id` (required) |

### Users & vehicles

| Tool | API endpoint | Parameters |
|---|---|---|
| `get_users` | `GET /users` | `role` (driver/conductor/manager/staff), `is_active` |
| `get_user` | `GET /users/{id}` | `user_id` (required) |
| `get_vehicles` | `GET /vehicles` | `status` (active/inactive/maintenance/decommissioned) |
| `get_vehicle` | `GET /vehicles/{id}` | `vehicle_id` (required) |

### Boarding & bookings

| Tool | API endpoint | Parameters |
|---|---|---|
| `get_boarding_manifest` | `GET /boarding/manifest/{id}` | `assignment_id` (required) |
| `get_admin_bookings` | `GET /admin/bookings` | `status`, `schedule_id` |

### Reports & metadata

| Tool | API endpoint | Parameters |
|---|---|---|
| `get_reports_revenue` | `GET /reports/revenue` | `date_from`, `date_to` |
| `get_bus_classes` | `GET /bus-classes` | — |

## Example query patterns

| Question | Model's tool usage |
|---|---|
| "show me drivers on schedule 42" | `get_schedule(42)` → `get_trip_assignments(schedule_id=42)` → `get_user(driver_id)` |
| "what trips did driver 15 take" | `get_trip_assignments(driver_id=15)` → `get_schedule()` per result |
| "list active schedules today" | `get_schedules(date="2026-07-16", status="active")` → `get_route()` per schedule |
| "show me the manifest for trip 8" | `get_boarding_manifest(8)` |
| "how many pending trips are there" | `get_trip_assignments(status="pending")` |
| "which vehicles are in maintenance" | `get_vehicles(status="maintenance")` |
| "revenue for July 2026" | `get_reports_revenue(date_from="2026-07-01", date_to="2026-07-31")` |

## Project structure

```
commutr-AI/
├── agent.py               # CLI + Ollama chat loop + tool definitions + dispatch
├── tools.py               # 20 read-only API wrapper functions (GET only)
├── auth.py                # JWT login, caching, auto-refresh
├── tests/
│   └── test_agent.py      # 9 tests: tool dispatch, auth, 404/403, params, read-only enforcement
├── pyproject.toml         # Dependencies (ollama, requests)
├── .env.example           # Credential template (copy to .env)
├── .gitignore
└── README.md
```

## Running tests

```bash
source .venv/bin/activate
pip install pytest pytest-mock
python -m pytest tests/ -v
```

```
tests/test_agent.py::test_tool_dispatch_covers_all_definitions PASSED
tests/test_agent.py::test_call_unknown_tool PASSED
tests/test_agent.py::TestAuth::test_missing_credentials PASSED
tests/test_agent.py::TestToolsReadOnly::test_no_mutation_functions PASSED
tests/test_agent.py::TestToolsReadOnly::test_api_get_only_calls_get PASSED
tests/test_agent.py::TestToolRouting::test_get_schedule_404 PASSED
tests/test_agent.py::TestToolRouting::test_get_schedule_403 PASSED
tests/test_agent.py::TestToolsParams::test_get_schedules_passes_query_params PASSED
tests/test_agent.py::TestToolsParams::test_get_users_passes_role PASSED
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `Cannot reach Commutr API` | Ensure Go API is running: `curl localhost:8080/health` |
| `Invalid credentials` | Check `.env` has correct `COMMUTR_EMAIL` and `COMMUTR_PASSWORD` |
| `Session expired` | Agent auto-reauthenticates. Clear cache: `rm ~/.commutr/token.json` |
| `ollama: command not found` | Install: `brew install ollama` (macOS) |
| Model not downloaded | `ollama list` — if empty, run `ollama pull qwen2.5:7b` |
| `ModuleNotFoundError: No module named 'ollama'` | Activate venv: `source .venv/bin/activate` |
| Agent hangs | Ensure Ollama is running: `brew services restart ollama` |
| Slow first response | Model loads into RAM on first query (~2-3s), subsequent queries are fast |
| Memory pressure | 7B model uses ~5GB RAM. If tight, try `ollama pull llama3.2` (~2GB) |
