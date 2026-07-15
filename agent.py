"""Commutr AI Agent — local Ollama-powered query interface.

Usage:
    python -m agent "show me drivers assigned to schedule 42"
    python -m agent --interactive
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any

import ollama

import tools as api

DEFAULT_MODEL = "qwen2.5:7b"

# Tool results larger than this get compacted before they reach the model —
# a 7B local model has a small context window and list endpoints can return
# tens of thousands of rows.
MAX_TOOL_ITEMS = 40
MAX_TOOL_CHARS = 12000


def _model() -> str:
    return os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)


def _ollama_options() -> dict[str, Any]:
    # Ollama defaults num_ctx to 4096, which the system prompt + tool
    # definitions alone exceed — the prompt gets silently truncated and the
    # model loses its instructions. qwen2.5 supports 32k.
    return {"num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "16384"))}


SYSTEM_PROMPT = """You are a read-only AI agent for Commutr, a Philippine bus booking and operations platform.

## Your job
Answer questions about schedules, routes, trips, drivers, conductors, vehicles, bookings, and boarding manifests. You can call tools to look up data. Never fabricate anything — if a tool returns nothing, say so.

## Core concepts
- A **Schedule** represents a bus trip on a specific route, date, and departure time. Status: scheduled/active/ongoing/delayed/completed/cancelled.
- A **TripAssignment** links a schedule to a specific vehicle, driver, and conductor. Status: pending/in_progress/completed/cancelled. This is different from the schedule status.
- A **Route** connects an origin to a destination (e.g., "Manila → Baguio").
- **Users** have roles: driver, conductor, manager, staff, commuter. A driver is a user with role=driver.
- **Vehicles** have a plate number, model, capacity, and status (active/inactive/maintenance/decommissioned).

## How the app actually flows (use this to reason about state)

### Booking lifecycle
Commuter searches by origin/destination/date → picks a schedule, segment, and seat → the server computes the fare and creates a **pending booking with a time-limited seat lease** → payment (PayMongo) confirms it → confirmed booking gets a **QR ticket**. Bookings can therefore be pending (lease not yet paid), confirmed, cancelled, or expired (lease lapsed). A "full" schedule means confirmed + leased seats, not just confirmed.

### Trip lifecycle
Manager creates a TripAssignment (schedule + vehicle + driver + conductor), status **pending** → driver starts the trip, status **in_progress**, GPS broadcasting begins → driver marks arrivals per stop (trip events) → confirming the final stop completes the trip, status **completed**, GPS stops. So: schedule status describes the timetable entry; assignment status describes the crew's execution of it. A schedule can be "active" while its assignment is still "pending" (crew hasn't started).

### Boarding
The conductor loads the assignment-scoped manifest and scans passenger QR tickets. Each scan validates booking, duplicate state, and capacity. The manifest (get_boarding_manifest, keyed by **assignment_id**, not schedule_id) shows who actually boarded vs no-shows. Offline scans reconcile in batches, so a manifest may briefly lag reality.

### Data relationships (traversal map)
route 1→N schedules; schedule 1→1 trip_assignment (usually); schedule 1→N bookings; assignment 1→N trip_events; assignment 1→1 boarding manifest; assignment references driver_id/conductor_id (users) and vehicle_id. To go from a route to its passengers: route → schedules → bookings, or route → schedules → assignment → manifest for boarded-only.

## API response shapes
- List endpoints return a paginated envelope: {"data": [...], "total": N, "limit": 20, "offset": 0}. "data" may be null when empty. If total > limit, there are more rows — page with offset or narrow the filters.
- By-ID endpoints return the bare object directly.
- Large results may include a "_note" field saying they were truncated — refine with filters (date, status, route_id, limit) instead of asking for everything.

## How to handle vague or ambiguous questions

### 1. Gather context first
When the user is vague, collect data before answering. Do NOT ask "which schedule?" immediately — instead, look at what's available:
- "show me the drivers" → get all users with role=driver first, then show them.
- "what's happening today" → get today's schedules, then get their assignments.
- Do NOT filter by status unless the user asks for a specific status. "Today's schedules" means ALL of today's schedules — most sit at status "scheduled" until departure, so filtering by "active" wrongly returns nothing.
- "tell me about the Manila route" → get all routes, find the ones with "Manila" in origin or destination, then show details for the best match.

### 2. Infer from partial info
- "schedule 42" → call get_schedule(42) directly. The user gave you an ID.
- "the Baguio trip" → first get all routes, find Baguio routes, then get schedules for those routes.
- "driver Juan" → get all users with role=driver, match by first_name or last_name.
- "vehicle ABC-123" → get all vehicles, match by plate_number.
- "yesterday" / "tomorrow" / "this week" → compute the date from the current date given at the top of this prompt.

### 3. Resolve ambiguity with data
When multiple matches exist, present the options clearly:
- "I found 3 routes going to Baguio: Route 5 (Cubao → Baguio), Route 12 (Pasay → Baguio), Route 18 (Manila → Baguio). Which one?"
- "Driver Juan matches two people: Juan Dela Cruz (id: 15) and Juan Santos (id: 23). Which one?"

### 4. When data is missing
- If a schedule has no assignment yet: "Schedule 42 has no driver assigned yet."
- If a route has no schedules today: "There are no schedules for the Manila → Baguio route today. Here are the upcoming ones this week instead..."

### 5. Think in steps
Break complex questions into a plan:
- "who's driving the earliest trip tomorrow" → (1) get tomorrow's schedules, (2) sort by departure time, (3) get the assignment for the earliest one, (4) get the driver's name.
- "compare occupancy across today's active trips" → (1) get today's active schedules, (2) get bookings for each, (3) summarize.

## Formatting rules
- Be concise. Show key identifiers (IDs, names, plate numbers) so the user can ask follow-ups.
- For schedules: "Schedule <id> — <origin> → <destination>, <date>, <depart> → <arrive>, ₱<fare>, <n> seats"
- For assignments: "Driver: <driver_name> | Conductor: <conductor_name> | Vehicle: <plate> | Status: <status>"
- For users: "<full name> (id: <id>) — <role>, <active/inactive>"
- Use tables for 3+ results. Use bullet points for 1-2 results.
- NEVER invent field values. Assignment results contain vehicle_id but NOT the plate number — if you want to show a plate, call get_vehicle(vehicle_id) first, otherwise show "Vehicle ID <id>". Only state values that literally appeared in a tool result.

## Query strategy reference
These are common question patterns. Use them as templates for similar queries:

"show me drivers on schedule X" →
  get_schedule(X) to confirm it exists, then
  get_trip_assignments(schedule_id=X), then
  get_user(driver_id) and get_user(conductor_id)

"which trips did driver John take" →
  get_users(role=driver), match "John" in names, then
  get_trip_assignments(driver_id=matched_id), then
  get_schedule(schedule_id) for each assignment

"are there any active schedules going to Baguio" →
  get_routes(), find routes whose destination includes "Baguio", then
  get_schedules(route_id=X, status=active) for each matching route

"how full is schedule 42" →
  get_schedule(42) for total seats, then
  get_schedule_bookings(42) for occupied count, then
  compute percentage

"show me the passenger list for the 6am Manila-Baguio trip" →
  get_routes(), find the Manila→Baguio route, then
  get_schedules(route_id=X, date=today), filter by departure_time, then
  get_schedule_bookings(schedule_id), or
  get_trip_assignments(schedule_id) then get_boarding_manifest(assignment_id)

"which vehicles need maintenance" →
  get_vehicles(status=maintenance) or, if no results,
  get_vehicles() and check which are not active

"recent trip completions this week" →
  get_trip_assignments(status=completed), then
  get_schedule(schedule_id) for each to show route/date

"who's unassigned / idle" →
  get_users(role=driver), then
  get_trip_assignments(status=in_progress), then
  cross-reference — drivers NOT in any in_progress assignment are idle

"revenue for this month" →
  get_reports_revenue(date_from="YYYY-MM-01", date_to="YYYY-MM-DD")

"where is the bus for schedule X right now" →
  get_trip_assignments(schedule_id=X), then
  get_trip_tracking(assignment_id) — only meaningful while status=in_progress

"what happened on trip / assignment X" →
  get_trip_events(assignment_id=X) for arrivals, delays, and reported issues"""


def _live_context() -> str:
    """Fetch a small snapshot of live data so the model knows what exists
    (real route names/IDs) instead of guessing. Degrades gracefully."""
    lines: list[str] = []
    try:
        routes = api.get_routes({"limit": 100})
        items = routes.get("data", routes) if isinstance(routes, dict) else routes
        total = routes.get("total", len(items or [])) if isinstance(routes, dict) else len(items or [])
        if isinstance(items, list) and items:
            shown = items[:80]
            lines.append(f"### Routes in this company ({total} total):")
            for r in shown:
                rid = r.get("route_id", r.get("id"))
                lines.append(
                    f"- Route {rid}: {r.get('origin')} → {r.get('destination')}"
                )
            if total > len(shown):
                lines.append(f"- ...and {total - len(shown)} more (use get_routes)")
    except Exception:
        lines.append(
            "### Live route snapshot unavailable — call get_routes to discover routes."
        )
    return "\n".join(lines)


def build_system_prompt() -> str:
    now = datetime.now().astimezone()
    header = (
        f"Current date/time: {now.strftime('%A, %B %d, %Y %I:%M %p %Z')} "
        f"(ISO: {now.strftime('%Y-%m-%d')}). "
        "Use this for 'today', 'tomorrow', 'yesterday', 'this week'.\n\n"
    )
    return header + SYSTEM_PROMPT + "\n\n## Live data snapshot\n" + _live_context()


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_schedules",
            "description": (
                "List schedules for a date and/or route. OMIT the status param "
                "unless the user explicitly asks for one specific status — "
                "most schedules are 'scheduled' and multi-status values are "
                "invalid. Results are paginated (check 'total')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "route_id": {"type": "integer"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "status": {
                        "type": "string",
                        "description": "Exactly one of: scheduled, ongoing, delayed, completed, cancelled. Usually omit.",
                    },
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule",
            "description": "Get a single schedule by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "integer"},
                },
                "required": ["schedule_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule_bookings",
            "description": "List all bookings on a schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "integer"},
                },
                "required": ["schedule_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_routes",
            "description": "List all bus routes.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_route",
            "description": "Get a single route by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "route_id": {"type": "integer"},
                },
                "required": ["route_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trip_assignments",
            "description": "List trip assignments. Use params: schedule_id, vehicle_id, driver_id, conductor_id, status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "integer"},
                    "vehicle_id": {"type": "integer"},
                    "driver_id": {"type": "integer"},
                    "conductor_id": {"type": "integer"},
                    "status": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trip_assignment",
            "description": "Get a single trip assignment by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignment_id": {"type": "integer"},
                },
                "required": ["assignment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_users",
            "description": "List company users. Use params: role, is_active.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "is_active": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user",
            "description": "Get a single user by their ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vehicles",
            "description": "List vehicles. Use params: status (active/inactive/maintenance/decommissioned).",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_vehicle",
            "description": "Get a single vehicle by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vehicle_id": {"type": "integer"},
                },
                "required": ["vehicle_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_boarding_manifest",
            "description": "Get the passenger manifest (boarding status) for a trip assignment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignment_id": {"type": "integer"},
                },
                "required": ["assignment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_admin_bookings",
            "description": "List all bookings (admin view). Use params: status, schedule_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "schedule_id": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_reports_revenue",
            "description": "Get revenue report. Use params: date_from, date_to.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bus_classes",
            "description": "List bus classes (e.g. Regular AC, Deluxe, Super Deluxe).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_route_stops",
            "description": "List the ordered stops on a route (names, sequence, distances).",
            "parameters": {
                "type": "object",
                "properties": {
                    "route_id": {"type": "integer"},
                },
                "required": ["route_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule_seats",
            "description": "Get seat availability map for a schedule (which seats are taken/free).",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "integer"},
                },
                "required": ["schedule_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trip_tracking",
            "description": "Get the latest GPS tracking data for a trip assignment (only meaningful while in_progress).",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignment_id": {"type": "integer"},
                },
                "required": ["assignment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trip_events",
            "description": "List events on a trip assignment: stop arrivals, delays, reported issues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignment_id": {"type": "integer"},
                },
                "required": ["assignment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_admin_booking",
            "description": "Get a single booking by its ID (admin view, includes payment state).",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {"type": "integer"},
                },
                "required": ["booking_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_reports_bookings",
            "description": "Get bookings report (counts/trends). Use params: date_from, date_to (YYYY-MM-DD).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_reports_trips",
            "description": "Get trips report (completed/cancelled counts). Use params: date_from, date_to (YYYY-MM-DD).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_seat_layouts",
            "description": "List seat layout templates (rows/columns per bus class).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_amenities",
            "description": "List vehicle amenities (WiFi, AC, restroom, etc.).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOL_DISPATCH = {
    "get_schedules": lambda args: api.get_schedules(args),
    "get_schedule": lambda args: api.get_schedule(args["schedule_id"]),
    "get_schedule_bookings": lambda args: api.get_schedule_bookings(
        args["schedule_id"]
    ),
    "get_routes": lambda args: api.get_routes(args),
    "get_route": lambda args: api.get_route(args["route_id"]),
    "get_trip_assignments": lambda args: api.get_trip_assignments(args),
    "get_trip_assignment": lambda args: api.get_trip_assignment(
        args["assignment_id"]
    ),
    "get_users": lambda args: api.get_users(args),
    "get_user": lambda args: api.get_user(args["user_id"]),
    "get_vehicles": lambda args: api.get_vehicles(args),
    "get_vehicle": lambda args: api.get_vehicle(args["vehicle_id"]),
    "get_boarding_manifest": lambda args: api.get_boarding_manifest(
        args["assignment_id"]
    ),
    "get_admin_bookings": lambda args: api.get_admin_bookings(args),
    "get_reports_revenue": lambda args: api.get_reports_revenue(args),
    "get_bus_classes": lambda args: api.get_bus_classes(args),
    "get_route_stops": lambda args: api.get_route_stops(args["route_id"]),
    "get_schedule_seats": lambda args: api.get_schedule_seats(args["schedule_id"]),
    "get_trip_tracking": lambda args: api.get_trip_tracking(args["assignment_id"]),
    "get_trip_events": lambda args: api.get_trip_events(args["assignment_id"]),
    "get_admin_booking": lambda args: api.get_admin_booking(args["booking_id"]),
    "get_reports_bookings": lambda args: api.get_reports_bookings(args),
    "get_reports_trips": lambda args: api.get_reports_trips(args),
    "get_seat_layouts": lambda args: api.get_seat_layouts(args),
    "get_amenities": lambda args: api.get_amenities(args),
}


def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
    handler = TOOL_DISPATCH.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return handler(arguments)
    except api.ApiError as e:
        return {"error": str(e), "status_code": e.status_code, "body": e.body}


def _compact_result(result: Any) -> str:
    """Serialize a tool result, capping list size and total characters so a
    large response can't blow out the local model's context window."""
    if isinstance(result, dict) and isinstance(result.get("data"), list):
        items = result["data"]
        if len(items) > MAX_TOOL_ITEMS:
            result = {
                **result,
                "data": items[:MAX_TOOL_ITEMS],
                "_note": (
                    f"showing {MAX_TOOL_ITEMS} of {len(items)} items — "
                    "refine with filters (date, status, route_id, limit)"
                ),
            }
    text = json.dumps(result, default=str)
    if len(text) > MAX_TOOL_CHARS:
        text = text[:MAX_TOOL_CHARS] + '"... [truncated — refine the query with filters]'
    return text


def _run_conversation(question: str, system_prompt: str | None = None) -> str:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt or build_system_prompt()},
        {"role": "user", "content": question},
    ]

    max_turns = 8
    for _turn in range(max_turns):
        response = ollama.chat(
            model=_model(),
            messages=messages,
            tools=TOOL_DEFINITIONS,
            options=_ollama_options(),
        )

        msg = response["message"]

        if not msg.get("tool_calls"):
            return msg.get("content", "").strip()

        messages.append(msg)

        for tc in msg["tool_calls"]:
            fn = tc["function"]
            name = fn["name"]
            arguments = fn.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            result = _call_tool(name, arguments)
            content = _compact_result(result)
            if os.getenv("COMMUTR_AGENT_DEBUG"):
                print(f"[debug] {name}({arguments}) -> {content[:300]}", file=sys.stderr)
            messages.append({
                "role": "tool",
                "content": content,
            })

    # Out of tool budget — ask for a final answer from what was gathered.
    messages.append({
        "role": "user",
        "content": (
            "Stop calling tools. Answer the original question now using only "
            "the data already gathered; say what is still unknown."
        ),
    })
    response = ollama.chat(
        model=_model(), messages=messages, options=_ollama_options()
    )
    return response["message"].get("content", "").strip()


def _interactive() -> None:
    print(f"Commutr AI Agent [model: {_model()}]")
    print(f"API: {os.getenv('COMMUTR_API_BASE', 'http://localhost:8080')}")
    print('Type your question or "exit".\n')

    # Build once per session: fetches the live route snapshot a single time.
    system_prompt = build_system_prompt()

    try:
        while True:
            q = input("> ").strip()
            if q.lower() in ("exit", "quit", "q"):
                break
            if not q:
                continue
            print()
            answer = _run_conversation(q, system_prompt)
            print(answer)
            print()
    except KeyboardInterrupt:
        print()
    except api.ApiError as e:
        print(f"\nError: {e}", file=sys.stderr)


def main() -> None:
    args = sys.argv[1:]

    if len(args) >= 2 and args[0] == "--model":
        os.environ["OLLAMA_MODEL"] = args[1]
        args = args[2:]

    if not args or args[0] in ("--interactive", "-i"):
        _interactive()
        return

    question = " ".join(args)
    try:
        answer = _run_conversation(question)
        print(answer)
    except api.ApiError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
