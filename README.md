# Commutr AI Agent

Local Ollama-powered AI agent for read-only Commutr API queries. Zero cloud cost — all inference runs on your machine.

```
You: "show me drivers assigned to schedule 42"
    ↓
Ollama (qwen2.5:7b) — local inference
    ↓
Read-only Commutr API tools
    ↓
Go API → PostgreSQL
```

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com/) with a tool-capable model
- Running Commutr Go API (typically `http://localhost:8080`)

## Setup

### 1. Install Ollama and pull a model

```bash
ollama pull qwen2.5:7b   # ~4GB, good function calling
# or
ollama pull llama3.2     # ~2GB, lighter but less capable
```

### 2. Install dependencies

```bash
pip install ollama requests
# or
pip install -e ".[dev]"  # includes pytest
```

### 3. Configure credentials

```bash
cp .env.example .env
```

Edit `.env` with your Commutr API credentials:

```
COMMUTR_API_BASE=http://localhost:8080
COMMUTR_EMAIL=your-manager@buscompany.com
COMMUTR_PASSWORD=your-password
```

The agent stores a cached JWT in `~/.commutr/token.json` (chmod 600) and auto-refreshes before expiry.

## Usage

### One-shot queries

```bash
python -m agent "show me drivers assigned to schedule 42"
python -m agent "list active schedules for today"
python -m agent "how many bookings on schedule 42"
python -m agent "which vehicles are currently assigned"
python -m agent "show the manifest for trip assignment 15"
```

### Interactive mode

```bash
python -m agent -i
# or
python -m agent --interactive
```

### Override model

```bash
python -m agent --model llama3.2 "show all drivers"
```

## Available Tools

| Tool | API endpoint | Description |
|---|---|---|
| `get_schedules` | `GET /schedules` | List schedules (filter by route, date, status) |
| `get_schedule` | `GET /schedules/{id}` | Get single schedule |
| `get_schedule_bookings` | `GET /schedules/{id}/bookings` | Bookings on a schedule |
| `get_routes` | `GET /routes` | List all routes |
| `get_route` | `GET /routes/{id}` | Get single route |
| `get_trip_assignments` | `GET /trips/assignments` | List assignments (filter by schedule, vehicle, driver) |
| `get_trip_assignment` | `GET /trips/assignments/{id}` | Get single assignment |
| `get_users` | `GET /users` | List users (filter by role) |
| `get_user` | `GET /users/{id}` | Get single user |
| `get_vehicles` | `GET /vehicles` | List vehicles (filter by status) |
| `get_vehicle` | `GET /vehicles/{id}` | Get single vehicle |
| `get_boarding_manifest` | `GET /boarding/manifest/{id}` | Passenger manifest |
| `get_admin_bookings` | `GET /admin/bookings` | List all bookings |
| `get_reports_revenue` | `GET /reports/revenue` | Revenue report |
| `get_bus_classes` | `GET /bus-classes` | List bus classes |

## Security

- **Read-only**: every tool function calls `requests.get` — POST, PUT, DELETE are architecturally impossible.
- **Local**: all model inference runs locally via Ollama. No data leaves your machine.
- **Token isolation**: JWT cached in `~/.commutr/token.json` with `chmod 600`.
- **Credentials**: stored in local `.env` (gitignored), never committed.

## Architecture

```
agent.py          → Ollama chat loop + tool dispatch
tools.py          → Typed read-only API wrappers
auth.py           → JWT login, caching, refresh
tests/test_agent.py → Tool dispatch, auth, params, read-only enforcement
```

## Running tests

```bash
pip install pytest pytest-mock
python -m pytest tests/ -v
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `Cannot reach Commutr API` | Ensure Go API is running: `cd src/backend-go && go run ./cmd/api` |
| `Invalid credentials` | Check `.env` has correct `COMMUTR_EMAIL` and `COMMUTR_PASSWORD` |
| `Session expired` | Agent auto-reauthenticates; if persistent, check token expiry config |
| `ollama: command not found` | Install Ollama: `brew install ollama` (macOS) or see [ollama.com](https://ollama.com) |
| Model not pulling | `ollama list` to see installed models, `ollama pull qwen2.5:7b` to download |
