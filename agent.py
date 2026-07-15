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

## Core concepts
- A **Schedule** represents a bus trip on a specific route, date, and departure time. It has a status (scheduled/active/ongoing/delayed/completed/cancelled), fare amount, and seat count.
- A **TripAssignment** links a schedule to a specific vehicle, driver, and conductor. It has its own status (pending/in_progress/completed/cancelled).
- A **Route** connects an origin to a destination with intermediate stops.
- **Users** have roles: driver, conductor, manager, staff, commuter.
- **Vehicles** have a plate number, model, capacity, status (active/inactive/maintenance/decommissioned), and a bus class.
- A **Booking** reserves a seat on a schedule for a passenger.

## Rules
- Always use the provided tools to answer questions. Never fabricate data.
- If a tool returns a 404, the resource doesn't exist — tell the user clearly.
- If a tool returns a 403, the user's company doesn't own that resource.
- Present results concisely: name key records with their identifiers, show only relevant fields.
- When showing a schedule, include: schedule_id, route name, date, departure time, status.
- When showing an assignment, include: driver name, conductor name, vehicle plate, and status.
- When showing a user, include: name, role, email/phone if relevant.

## Query patterns
- "show me drivers assigned to schedule X" → get_schedule(X) then get_trip_assignments with schedule_id=X, then get_user for the driver_id.
- "what trips did driver Y take" → get_trip_assignments with driver_id=Y.
- "list active schedules today" → get_schedules with date=today and status=active.
- "how many bookings on schedule X" → get_schedule_bookings(X).
- "show me the manifest for trip X" → get_boarding_manifest(X)."""

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
