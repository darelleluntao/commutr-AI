"""Commutr AI Agent — HTTP server for dashboard integration.

Usage:
    python server.py                # default: localhost:8765
    python server.py --port 8765 --host 0.0.0.0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    import uvicorn
except ImportError:
    print("Missing dependencies. Install: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

import agent
import tools as api
from agent import _compact_result, TOOL_DEFINITIONS

app = FastAPI(title="Commutr AI Agent Server", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_STARTED_AT = datetime.now().astimezone()
_CONVERSATIONS: dict[str, list[dict[str, Any]]] = {}


@app.get("/health")
def health():
    model = agent._model()
    try:
        ollama_status = "ok"
    except Exception:
        ollama_status = "not checked"

    try:
        api.get_routes({"limit": 1})
        api_status = "ok"
    except Exception as e:
        api_status = str(e)

    return {
        "status": "ok",
        "model": model,
        "ollama": ollama_status,
        "api": api_status,
        "started_at": _STARTED_AT.isoformat(),
        "uptime_seconds": (datetime.now().astimezone() - _STARTED_AT).total_seconds(),
    }


@app.post("/ask")
def ask(req: dict[str, Any]):
    question = req.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    conversation_id = req.get("conversation_id", "default")

    try:
        start = time.time()
        answer = agent._run_conversation(question)
        elapsed = time.time() - start

        return {"answer": answer, "elapsed_ms": int(elapsed * 1000)}
    except api.ApiError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ask/stream")
async def ask_stream(req: dict[str, Any]):
    question = req.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    async def stream():
        system_prompt = agent.build_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        max_turns = 8
        for _turn in range(max_turns):
            response = agent.ollama.chat(
                model=agent._model(),
                messages=messages,
                tools=TOOL_DEFINITIONS,
                options=agent._ollama_options(),
            )

            msg = response["message"]

            if not msg.get("tool_calls"):
                yield f"data: {json.dumps({'type': 'answer', 'content': msg.get('content', '')})}\n\n"
                return

            messages.append(msg)

            tool_info: list[dict] = []
            for tc in msg["tool_calls"]:
                fn = tc["function"]
                name = fn["name"]
                arguments = fn.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                result = agent._call_tool(name, arguments)
                content = _compact_result(result)
                messages.append({"role": "tool", "content": content})
                tool_info.append({"tool": name, "args": arguments})

            yield f"data: {json.dumps({'type': 'tool_calls', 'tools': tool_info})}\n\n"

        messages.append({
            "role": "user",
            "content": "Stop calling tools. Answer the original question now using only the data already gathered; say what is still unknown.",
        })
        response = agent.ollama.chat(
            model=agent._model(), messages=messages, options=agent._ollama_options()
        )
        yield f"data: {json.dumps({'type': 'answer', 'content': response['message'].get('content', '')})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/health/model")
def model_health():
    try:
        import ollama
        ollama.ps()
        models = ollama.list()
        return {"ollama_running": True, "models": [m.model for m in models.models] if hasattr(models, 'models') else []}
    except Exception as e:
        return {"ollama_running": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Commutr AI Agent HTTP Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8765, help="Port")
    args = parser.parse_args()

    print(f"Commutr AI Agent Server [model: {agent._model()}]")
    print(f"Listening on http://{args.host}:{args.port}")
    print(f"Health check: http://{args.host}:{args.port}/health")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
