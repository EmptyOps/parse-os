# # os_automation/api/server.py
# """
# FastAPI entry point for parse-os.

# Flow:
#     Dhruv (Kilo Code MCP)
#         │  POST /run
#         │  { session_id, user_prompt, url, browser_auto_script_mode }
#         ▼
#     parse-os  (THIS FILE — the HTTP boundary Dhruv calls)
#         │
#         ├─ browser_auto_script_mode=False ──► Orchestrator (classic path)
#         │
#         └─ browser_auto_script_mode=True  ──► parse-os-pro via HTTP
#                POST http://parse-os-pro:8000/api/v1/jobs/run

# Why Dhruv calls parse-os and NOT parse-os-pro directly:
#     parse-os-pro is a PRIVATE/proprietary extension.
#     It has no public-facing endpoint of its own.
#     All traffic enters through parse-os, which decides whether to handle
#     it classically or hand off to the pro layer.

# Start with:
#     uvicorn os_automation.api.server:app --host 0.0.0.0 --port 7000
# """

# from __future__ import annotations

# import logging
# import os
# from contextlib import asynccontextmanager

# import httpx
# from fastapi import FastAPI, HTTPException
# from pydantic import BaseModel, Field, field_validator

# logger = logging.getLogger(__name__)

# logging.basicConfig(
#     level=logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO,
#     format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
# )

# # URL of parse-os-pro's internal API (configurable via env var)
# _PRO_URL = os.getenv(
#     "PARSE_OS_PRO_URL",
#     "http://localhost:8000/api/v1/jobs/run"
# )
# _PRO_TIMEOUT = float(os.getenv("PARSE_OS_PRO_TIMEOUT", "300"))

# # Shared async HTTP client (reuses connection pool across requests)
# _http_client: httpx.AsyncClient | None = None


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     global _http_client
#     _http_client = httpx.AsyncClient(timeout=_PRO_TIMEOUT, follow_redirects=True)
#     logger.info("[startup] parse-os API server ready — pro_url=%s", _PRO_URL)
#     yield
#     await _http_client.aclose()
#     logger.info("[shutdown] parse-os API server stopped")


# app = FastAPI(
#     title="parse-os",
#     description="OS automation API. Browser tasks with browser_auto_script_mode=True are forwarded to parse-os-pro.",
#     version="1.0.0",
#     lifespan=lifespan,
# )


# # ── Schemas ───────────────────────────────────────────────────────────────────

# class RunRequest(BaseModel):
#     session_id:               str  = Field(..., min_length=1)
#     user_prompt:              str  = Field(..., min_length=1)
#     url:                      str  = Field(..., description="Target website URL")
#     browser_auto_script_mode: bool = Field(default=False)

#     @field_validator("session_id")
#     @classmethod
#     def no_path_chars(cls, v: str) -> str:
#         if any(c in v for c in ("/", "\\", "..", "\x00")):
#             raise ValueError("session_id must not contain path characters")
#         return v.strip()

#     @field_validator("url")
#     @classmethod
#     def url_has_scheme(cls, v: str) -> str:
#         if not (v.startswith("http://") or v.startswith("https://")):
#             raise ValueError("url must start with http:// or https://")
#         return v


# class RunResponse(BaseModel):
#     session_id:   str
#     status:       str
#     detail:       str = ""
#     mode:         str = ""
#     # Only present in pro mode — Playwright script from parse-os-pro
#     playwright_script: str = ""


# # ── Routes ────────────────────────────────────────────────────────────────────

# @app.get("/health")
# async def health():
#     return {"status": "ok", "service": "parse-os"}

# @app.get("/parseos/run", response_model=RunResponse)
# async def parseos_run_compat(
#     prompt: str,
#     session_id: str,
#     project_link: str,
#     browser_auto_script_mode: str = "false",
# ):
#     """
#     Compat endpoint for Dhruv's MCP controller which fires a GET
#     to /parseos/run with query params instead of POST /run with JSON body.
#     """
#     req = RunRequest(
#         session_id=session_id,
#         user_prompt=prompt,
#         url=project_link,
#         browser_auto_script_mode=browser_auto_script_mode.lower() == "true",
#     )
#     return await run(req)


# @app.post("/run", response_model=RunResponse)
# async def run(req: RunRequest) -> RunResponse:
#     """
#     Single entry point for all automation tasks from Dhruv's layer.

#     Classic mode (browser_auto_script_mode=False):
#         Runs the standard parse-os Orchestrator pipeline directly.
#         No HTTP forwarding — all processing happens in this process.

#     Pro mode (browser_auto_script_mode=True):
#         Forwards the request to parse-os-pro which handles:
#           - step-by-step planning
#           - per-step MCP execution via Gemini
#           - selector capture
#           - per-step notification to Krish
#           - Playwright script generation
#     """

#     if not req.browser_auto_script_mode:
#         return await _run_classic(req)
#     else:
#         return await _run_pro(req)


# # ── Internal handlers ─────────────────────────────────────────────────────────

# async def _run_classic(req: RunRequest) -> RunResponse:
#     """Run standard parse-os pipeline in-process."""
#     import asyncio
#     from os_automation.core.orchestrator import Orchestrator

#     logger.info("[parse-os] classic mode — session=%s", req.session_id)
#     try:
#         # Orchestrator is synchronous — run in thread pool to avoid blocking
#         loop   = asyncio.get_running_loop()
#         orch   = Orchestrator()
#         result = await loop.run_in_executor(None, orch.run, req.user_prompt)
#     except Exception as exc:
#         logger.exception("[parse-os] classic run failed")
#         raise HTTPException(status_code=500, detail=f"Orchestration failed: {exc}")

#     return RunResponse(
#         session_id=req.session_id,
#         status=result.get("overall_status", "unknown"),
#         mode="classic",
#         detail="Classic parse-os run completed.",
#     )


# async def _run_pro(req: RunRequest) -> RunResponse:
#     """Forward to parse-os-pro and relay its response back to Dhruv."""
#     logger.info("[parse-os] pro mode — forwarding to parse-os-pro  session=%s url=%s",
#                 req.session_id, req.url)

#     payload = {
#         "session_id":               req.session_id,
#         "user_prompt":              req.user_prompt,
#         "url":                      req.url,
#         "browser_auto_script_mode": True,
#     }

#     try:
#         response = await _http_client.post(_PRO_URL, json=payload)
#         response.raise_for_status()
#         data = response.json()
#     except httpx.HTTPStatusError as exc:
#         logger.error("[parse-os] parse-os-pro returned %d: %s",
#                      exc.response.status_code, exc.response.text[:300])
#         raise HTTPException(
#             status_code=502,
#             detail=f"parse-os-pro error: HTTP {exc.response.status_code}",
#         )
#     except httpx.TransportError as exc:
#         logger.error("[parse-os] could not reach parse-os-pro: %s", exc)
#         raise HTTPException(
#             status_code=503,
#             detail="parse-os-pro is unreachable. Is it running on "
#                    f"{_PRO_URL}?",
#         )

#     return RunResponse(
#         session_id=req.session_id,
#         status=data.get("status", "unknown"),
#         mode="pro",
#         detail=data.get("detail", ""),
#         playwright_script=data.get("playwright_script", ""),
#     )
    
    
    
    
# os_automation/api/server.py
"""
FastAPI entry point for parse-os. KiloCode MCP calls this on port 7000.

YOUR SERVER IP: 192.168.0.122
  KiloCode MCP calls: http://192.168.0.122:7000/parseos/run
  parse-os internal:  http://localhost:8000/api/v1/jobs/run  (parse-os-pro)

Two call formats supported:

  Format A — GET /parseos/run  (what KiloCode MCP sends)
    GET /parseos/run?prompt=...&browser_auto_script_mode=true
                    &session_id=SESS-...&project_link=https://...

  Format B — POST /run  (for direct curl testing)
    POST /run  { session_id, user_prompt, url, browser_auto_script_mode }

Flow:
  browser_auto_script_mode=False → Orchestrator runs in-process (classic)
  browser_auto_script_mode=True  → forwarded to parse-os-pro (port 8000)

Start:
  uvicorn os_automation.api.server:app --host 0.0.0.0 --port 7000

Env vars:
  PARSE_OS_PRO_URL     = http://localhost:8000/api/v1/jobs/run
  PARSE_OS_PRO_TIMEOUT = 300
  OPENAI_API_KEY       = sk-...
  GEMINI_MCP_SCRIPT    = /absolute/path/to/run_gemini_mcp.sh
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

_PRO_URL     = os.getenv("PARSE_OS_PRO_URL",     "http://localhost:8000/api/v1/jobs/run")
_PRO_TIMEOUT = float(os.getenv("PARSE_OS_PRO_TIMEOUT", "300"))

_http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client
    _http_client = httpx.AsyncClient(timeout=_PRO_TIMEOUT, follow_redirects=True)
    logger.info("[startup] parse-os API server ready — pro_url=%s", _PRO_URL)
    yield
    await _http_client.aclose()
    logger.info("[shutdown] parse-os API server stopped")


app = FastAPI(
    title="parse-os",
    description=(
        "OS automation API. KiloCode MCP calls /parseos/run. "
        "Browser tasks (browser_auto_script_mode=True) are forwarded to parse-os-pro."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    session_id:               str  = Field(..., min_length=1)
    user_prompt:              str  = Field(..., min_length=1)
    url:                      str  = Field(default="")
    browser_auto_script_mode: bool = Field(default=False)

    @field_validator("session_id")
    @classmethod
    def no_path_chars(cls, v: str) -> str:
        if any(c in v for c in ("/", "\\", "..", "\x00")):
            raise ValueError("session_id must not contain path characters")
        return v.strip()


class RunResponse(BaseModel):
    session_id:        str
    status:            str
    detail:            str = ""
    mode:              str = ""
    playwright_script: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "parse-os"}


# ── Format A: GET /parseos/run — KiloCode MCP format ─────────────────────────
@app.get("/parseos/run", response_model=RunResponse)
async def parseos_run_get(
    prompt:                   str  = Query(...),
    session_id:               str  = Query(...),
    project_link:             str  = Query(""),
    browser_auto_script_mode: bool = Query(False),
) -> RunResponse:
    """
    KiloCode MCP calls this endpoint.

    Example:
      GET /parseos/run?prompt=Test+ring+builder&session_id=SESS-...
                      &project_link=http://localhost:3000
                      &browser_auto_script_mode=true
    """
    req = RunRequest(
        session_id=session_id,
        user_prompt=prompt,
        url=project_link,
        browser_auto_script_mode=browser_auto_script_mode,
    )
    return await (_run_classic(req) if not req.browser_auto_script_mode
                  else _run_pro(req))


# ── Format B: POST /run — for direct curl/Postman testing ────────────────────
@app.post("/run", response_model=RunResponse)
async def run_post(req: RunRequest) -> RunResponse:
    return await (_run_classic(req) if not req.browser_auto_script_mode
                  else _run_pro(req))


# ── Internal handlers ─────────────────────────────────────────────────────────

async def _run_classic(req: RunRequest) -> RunResponse:
    import asyncio
    from os_automation.core.orchestrator import Orchestrator

    logger.info("[parse-os] classic mode — session=%s", req.session_id)
    try:
        loop   = asyncio.get_running_loop()
        orch   = Orchestrator()
        result = await loop.run_in_executor(None, orch.run, req.user_prompt)
    except Exception as exc:
        logger.exception("[parse-os] classic run failed")
        raise HTTPException(status_code=500, detail=f"Orchestration failed: {exc}")

    return RunResponse(
        session_id=req.session_id,
        status=result.get("overall_status", "unknown"),
        mode="classic",
        detail="Classic parse-os run completed.",
    )


async def _run_pro(req: RunRequest) -> RunResponse:
    logger.info("[parse-os] pro mode → parse-os-pro  session=%s url=%s",
                req.session_id, req.url)

    payload = {
        "session_id":               req.session_id,
        "user_prompt":              req.user_prompt,
        "url":                      req.url,
        "browser_auto_script_mode": True,
    }

    try:
        response = await _http_client.post(_PRO_URL, json=payload)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500]
        logger.error("[parse-os] parse-os-pro returned %d: %s",
                     exc.response.status_code, body)
        raise HTTPException(
            status_code=502,
            detail=f"parse-os-pro error: HTTP {exc.response.status_code} — {body}",
        )
    except httpx.TransportError as exc:
        logger.error("[parse-os] cannot reach parse-os-pro: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"parse-os-pro unreachable at {_PRO_URL}. Is it running?",
        )

    return RunResponse(
        session_id=req.session_id,
        status=data.get("status", "unknown"),
        mode="pro",
        detail=data.get("detail", ""),
        playwright_script=data.get("playwright_script", ""),
    )