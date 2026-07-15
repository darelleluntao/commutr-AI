"""Read-only Commutr API tool wrappers.

Every function here only calls GET. Mutations (POST, PUT, PATCH, DELETE)
are architecturally impossible through this module.
"""

from __future__ import annotations

from typing import Any

import requests

import auth


class ApiError(Exception):
    def __init__(self, status_code: int, message: str, body: str = ""):
        self.status_code = status_code
        self.message = message
        self.body = body
        super().__init__(f"[{status_code}] {message}")


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    token = auth.get_token()
    url = f"{auth.get_api_base()}/api/v1{path}"
    try:
        resp = requests.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except requests.exceptions.RequestException as e:
        raise ApiError(0, f"API unreachable: {e}") from e

    if resp.status_code == 404:
        raise ApiError(404, "Resource not found")
    if resp.status_code == 403:
        raise ApiError(403, "Access denied (company scope)")
    if resp.status_code == 401:
        auth.clear_token()
        raise ApiError(401, "Session expired — re-authenticate and retry")
    if not resp.ok:
        raise ApiError(
            resp.status_code,
            f"API error",
            resp.text[:500],
        )
    return resp.json()


# ── Routes ────────────────────────────────────────────────────────────────────


def get_routes(params: dict[str, Any] | None = None) -> Any:
    return _get("/routes", params)


def get_route(route_id: int) -> Any:
    return _get(f"/routes/{route_id}")


def get_route_stops(route_id: int) -> Any:
    return _get(f"/routes/{route_id}/stops")


# ── Schedules ─────────────────────────────────────────────────────────────────


def get_schedules(params: dict[str, Any] | None = None) -> Any:
    return _get("/schedules", params)


def get_schedule(schedule_id: int) -> Any:
    return _get(f"/schedules/{schedule_id}")


def get_schedule_seats(schedule_id: int) -> Any:
    return _get(f"/schedules/{schedule_id}/seats")


def get_schedule_bookings(schedule_id: int) -> Any:
    return _get(f"/schedules/{schedule_id}/bookings")


# ── Trip Assignments ──────────────────────────────────────────────────────────


def get_trip_assignments(params: dict[str, Any] | None = None) -> Any:
    return _get("/trips/assignments", params)


def get_trip_assignment(assignment_id: int) -> Any:
    return _get(f"/trips/assignments/{assignment_id}")


def get_trip_tracking(assignment_id: int) -> Any:
    return _get(f"/trips/assignments/{assignment_id}/tracking")


def get_trip_events(assignment_id: int) -> Any:
    return _get(f"/trips/assignments/{assignment_id}/events")


# ── Users ─────────────────────────────────────────────────────────────────────


def get_users(params: dict[str, Any] | None = None) -> Any:
    return _get("/users", params)


def get_user(user_id: int) -> Any:
    return _get(f"/users/{user_id}")


# ── Vehicles ──────────────────────────────────────────────────────────────────


def get_vehicles(params: dict[str, Any] | None = None) -> Any:
    return _get("/vehicles", params)


def get_vehicle(vehicle_id: int) -> Any:
    return _get(f"/vehicles/{vehicle_id}")


def get_vehicle_seats(vehicle_id: int) -> Any:
    return _get(f"/vehicles/{vehicle_id}/seats")


# ── Boarding ──────────────────────────────────────────────────────────────────


def get_boarding_manifest(assignment_id: int) -> Any:
    return _get(f"/boarding/manifest/{assignment_id}")


# ── Bookings ──────────────────────────────────────────────────────────────────


def get_admin_bookings(params: dict[str, Any] | None = None) -> Any:
    return _get("/admin/bookings", params)


def get_admin_booking(booking_id: int) -> Any:
    return _get(f"/admin/bookings/{booking_id}")


# ── Bus Classes / Seat Layouts / Amenities ────────────────────────────────────


def get_bus_classes(params: dict[str, Any] | None = None) -> Any:
    return _get("/bus-classes", params)


def get_seat_layouts(params: dict[str, Any] | None = None) -> Any:
    return _get("/seat-layouts", params)


def get_amenities(params: dict[str, Any] | None = None) -> Any:
    return _get("/amenities", params)


# ── Reports ───────────────────────────────────────────────────────────────────


def get_reports_revenue(params: dict[str, Any] | None = None) -> Any:
    return _get("/reports/revenue", params)


def get_reports_bookings(params: dict[str, Any] | None = None) -> Any:
    return _get("/reports/bookings", params)


def get_reports_trips(params: dict[str, Any] | None = None) -> Any:
    return _get("/reports/trips", params)
