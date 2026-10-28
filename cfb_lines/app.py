"""HTTP API and dashboard.

Run with:  uvicorn cfb_lines.app:app --reload
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from .config import Settings
from .providers import make_provider
from .service import LineService

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("cfb_lines")


def create_app(service: LineService | None = None, autostart: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = service
        if svc is None:
            settings = Settings.from_env()
            svc = LineService(settings, make_provider(settings))
            if settings.provider == "odds_api":
                per_month = settings.fetch_cost * (30 * 24 * 3600 / settings.poll_seconds)
                log.warning(
                    "Polling The Odds API every %ss at %s credits/call (~%s credits/month if run 24/7)",
                    settings.poll_seconds, settings.fetch_cost, f"{per_month:,.0f}",
                )
        app.state.service = svc
        if autostart:
            svc.start()
        yield
        await svc.stop()

    app = FastAPI(title="CFB Lines", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/snapshot")
    async def snapshot(request: Request):
        return request.app.state.service.payload()

    @app.get("/api/opportunities")
    async def opportunities(request: Request, type: str | None = None, min_edge: float = 0.0):
        opps = request.app.state.service.payload()["opportunities"]
        if type:
            wanted = {t.strip().upper() for t in type.split(",")}
            opps = [o for o in opps if o["type"] in wanted]
        return [o for o in opps if o["edge"] >= min_edge]

    @app.get("/api/games/{game_id}/history")
    async def game_history(request: Request, game_id: str):
        svc = request.app.state.service
        series = svc.history.for_game(game_id)
        if not series:
            raise HTTPException(404, "unknown game")
        return series

    @app.post("/api/refresh")
    async def refresh(request: Request):
        await request.app.state.service.refresh_now()
        return request.app.state.service.status

    @app.get("/api/stream")
    async def stream(request: Request):
        svc: LineService = request.app.state.service
        queue = svc.subscribe()

        async def events():
            try:
                yield f"data: {json.dumps(svc.payload())}\n\n"
                while True:
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=15)
                        yield f"data: {json.dumps(payload)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                    if await request.is_disconnected():
                        break
            finally:
                svc.unsubscribe(queue)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
