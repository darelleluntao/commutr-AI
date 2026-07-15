from __future__ import annotations

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from agent import _call_tool, TOOL_DISPATCH


@pytest.fixture(autouse=True)
def _mock_auth():
    with patch("auth.get_token", return_value="test-token"):
        yield


def test_tool_dispatch_covers_all_definitions():
    from agent import TOOL_DEFINITIONS

    defined = {td["function"]["name"] for td in TOOL_DEFINITIONS}
    dispatched = set(TOOL_DISPATCH.keys())
    undefined = dispatched - defined
    unmapped = defined - dispatched

    assert not undefined, f"Dispatched tools not in definitions: {undefined}"
    assert not unmapped, f"Defined tools not in dispatch: {unmapped}"


def test_call_unknown_tool():
    result = _call_tool("nonexistent_tool", {})
    assert isinstance(result, dict)
    assert "error" in result


class TestAuth:
    def test_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            import auth

            auth._load_dotenv = lambda: None
            auth.COMMUTR_EMAIL = ""
            auth.COMMUTR_PASSWORD = ""
            with pytest.raises(auth.AuthError, match="COMMUTR_EMAIL"):
                auth._login()


class TestToolsReadOnly:
    def test_no_mutation_functions(self):
        import inspect
        import tools

        names = [n for n in dir(tools) if callable(getattr(tools, n))]
        for name in names:
            if name.startswith("_"):
                continue
            fn = getattr(tools, name)
            if not inspect.isfunction(fn):
                continue
            source = inspect.getsource(fn)
            http_methods = [
                "requests.post",
                "requests.put",
                "requests.delete",
                "requests.patch",
            ]
            for method in http_methods:
                assert (
                    method not in source
                ), f"{name} contains mutation method {method!r}"

    @patch("tools.requests.get")
    def test_api_get_only_calls_get(self, mock_get):
        import tools

        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"data": []}

        tools._get("/schedules")

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[1]["params"] is None
        assert call_args[1]["timeout"] == 15
        assert "Authorization" in call_args[1]["headers"]


class TestToolRouting:
    @patch("tools.requests.get")
    def test_get_schedule_404(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = _call_tool("get_schedule", {"schedule_id": 99999})
        assert "error" in result
        assert result["status_code"] == 404

    @patch("tools.requests.get")
    def test_get_schedule_403(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "forbidden"
        mock_get.return_value = mock_resp

        result = _call_tool("get_schedule", {"schedule_id": 1})
        assert "error" in result
        assert result["status_code"] == 403


class TestToolsParams:
    @patch("tools.requests.get")
    def test_get_schedules_passes_query_params(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}
        mock_get.return_value = mock_resp

        _call_tool("get_schedules", {"date": "2026-07-16", "status": "active"})

        call_args = mock_get.call_args
        assert call_args is not None
        assert call_args[1]["params"] == {
            "date": "2026-07-16",
            "status": "active",
        }

    @patch("tools.requests.get")
    def test_get_users_passes_role(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}
        mock_get.return_value = mock_resp

        _call_tool("get_users", {"role": "driver"})

        call_args = mock_get.call_args
        assert call_args[1]["params"] == {"role": "driver"}
