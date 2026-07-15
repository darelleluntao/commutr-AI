"""Commutr AI Agent — local Ollama-powered query interface.

Usage:
    python -m agent "show me drivers assigned to schedule 42"
    python -m agent --interactive
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import ollama

import tools as api

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

SYSTEM_PROMPT = """You are a read-only AI agent for Commutr, a Philippine bus booking and operations platform.

## Your job
Answer questions about schedules, routes, trips, drivers, conductors, vehicles, bookings, and boarding manifests. You can call tools to look up data. Never fabricate anything — if a tool returns nothing, say so.

## Core concepts
- A **Schedule** represents a bus trip on a specific route, date, and departure time. Status: scheduled/active/ongoing/delayed/completed/cancelled.
- A **TripAssignment** links a schedule to a specific vehicle, driver, and conductor. Status: pending/in_progress/completed/cancelled. This is different from the schedule status.
- A **Route** connects an origin to a destination (e.g., "Manila → Baguio").
- **Users** have roles: driver, conductor, manager, staff, commuter. A driver is a user with role=driver.
- **Vehicles** have a plate number, model, capacity, and status (active/inactive/maintenance/decommissioned).

## How to handle vague or ambiguous questions

### 1. Gather context first
When the user is vague, collect data before answering. Do NOT ask "which schedule?" immediately — instead, look at what's available:
- "show me the drivers" → get all users with role=driver first, then show them.
- "what's happening today" → get today's schedules, then get their assignments.
- "tell me about the Manila route" → get all routes, find the ones with "Manila" in origin or destination, then show details for the best match.

### 2. Infer from partial info
- "schedule 42" → call get_schedule(42) directly. The user gave you an ID.
- "the Baguio trip" → first get all routes, find Baguio routes, then get schedules for those routes.
- "driver Juan" → get all users with role=driver, match by first_name or last_name.
- "vehicle ABC-123" → get all vehicles, match by plate_number.
- "yesterday" / "tomorrow" / "this week" → compute the date. Today is the current date.

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
- For schedules: "Schedule 42 — Manila → Baguio, Jul 16, 6:00 AM → 12:00 PM, ₱800, 32 seats"
- For assignments: "Driver: Juan Dela Cruz | Conductor: Pedro Santos | Vehicle: ABC-1234 | Status: in_progress"
- For users: "Juan Dela Cruz (id: 15) — driver, active"
- Use tables for 3+ results. Use bullet points for 1-2 results.

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
  get_reports_revenue(date_from="YYYY-MM-01", date_to="YYYY-MM-DD")"""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_schedules",
            "description": "List schedules. Use params: route_id, date (YYYY-MM-DD), status, limit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "route_id": {"type": "integer"},
                    "date": {"type": "string"},
                    "status": {"type": "string"},
                    "limit": {"type": "integer"},
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
}


def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
    handler = TOOL_DISPATCH.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return handler(arguments)
    except api.ApiError as e:
        return {"error": str(e), "status_code": e.status_code, "body": e.body}


def _run_conversation(question: str) -> str:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    max_turns = 8
    for _turn in range(max_turns):
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
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
            messages.append({
                "role": "tool",
                "content": json.dumps(result, default=str),
            })

    return "Agent reached the maximum number of tool-calling turns."


def _interactive() -> None:
    print(f"Commutr AI Agent [model: {OLLAMA_MODEL}]")
    print(f"API: {os.getenv('COMMUTR_API_BASE', 'http://localhost:8080')}")
    print('Type your question or "exit".\n')

    try:
        while True:
            q = input("> ").strip()
            if q.lower() in ("exit", "quit", "q"):
                break
            if not q:
                continue
            print()
            answer = _run_conversation(q)
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
