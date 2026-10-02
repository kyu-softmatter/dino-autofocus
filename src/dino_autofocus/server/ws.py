"""WebSocket bridges: `/ws/events` (engine events out, commands in) and `/ws/frames` (live view).

Engine sinks are called from engine threads. Every sink here only serialises and hands the
message to the event loop with `call_soon_threadsafe`, and never raises back into the engine.

Frames: the engine says `frame_ready`; the bridge then takes the newest frame from the engine
(`FrameSource.latest_frame`), bins it to at most `target_px` on the long side, maps it to
8 bit and encodes a JPEG, at most `max_fps` times a second however fast frames arrive. Each
client holds one pending frame; a slow client skips to the newest instead of queueing.
Nothing is encoded while nobody watches. Raw frames go to disk records only, never here.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import math
from collections.abc import Awaitable, Callable
from typing import Any

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.requests import HTTPConnection

from .api import is_local
from .schemas import (
    EngineAPI,
    Event,
    EventOut,
    FrameSource,
    WsAccepted,
    WsCommand,
    WsError,
    WsEvent,
    WsFrame,
)

log = logging.getLogger(__name__)

EVENT_QUEUE_MAX = 1000  # a client this far behind is closed (1013) and should reload /api/state
CLOSE_TRY_AGAIN = 1013
CLOSE_UNSUPPORTED = 1003

Refuse = Callable[[HTTPConnection, str | None, str], str | None]  # (conn, kind, op) -> why not


def install(
    app: FastAPI, engine: EngineAPI, *, refuse: Refuse, stopped: Callable[[], bool] = lambda: False
) -> None:
    frames = FrameBridge(engine)
    app.state.frames = frames

    @app.websocket("/ws/events")
    async def events(websocket: WebSocket) -> None:
        await websocket.accept()
        loop = asyncio.get_running_loop()
        out: asyncio.Queue[str | None] = asyncio.Queue(maxsize=EVENT_QUEUE_MAX)

        def push(text: str) -> None:
            try:
                out.put_nowait(text)
            except asyncio.QueueFull:
                while not out.empty():
                    out.get_nowait()
                out.put_nowait(None)  # sender closes the socket

        def sink(ev: Event) -> None:
            try:
                text = WsEvent(event=EventOut.from_engine(ev)).model_dump_json()
                loop.call_soon_threadsafe(push, text)
            except RuntimeError:
                pass  # loop already closed: the client has gone
            except Exception:
                log.exception("event %r could not be forwarded", getattr(ev, "kind", ev))

        async def send() -> None:
            while (text := await out.get()) is not None:
                await websocket.send_text(text)
            await websocket.close(CLOSE_TRY_AGAIN, "event queue overflow; reload state")

        async def receive() -> None:
            while True:
                reply = await _command_reply(await websocket.receive_text(), websocket)
                push(reply.model_dump_json())

        async def _command_reply(text: str, conn: HTTPConnection) -> WsAccepted | WsError:
            try:
                msg = WsCommand.model_validate_json(text)
            except ValidationError as e:
                return WsError(status=422, detail=str(e))
            why = refuse(conn, msg.command.kind, msg.command.op)
            if why is not None:
                return WsError(status=403, detail=why)
            if stopped():
                return WsError(status=503, detail="the server is shutting down")
            try:
                cmd = msg.command.to_engine(remote=not is_local(conn))
                op_id = await asyncio.to_thread(engine.submit, cmd)
            except ValueError as e:
                return WsError(status=400, detail=str(e))
            return WsAccepted(op_id=op_id)

        unsubscribe = engine.subscribe(sink)
        try:
            await _until_first_done(send(), receive())
        finally:
            unsubscribe()

    @app.websocket("/ws/frames")
    async def live_frames(websocket: WebSocket) -> None:
        await websocket.accept()
        if not isinstance(engine, FrameSource):
            await websocket.send_text(
                WsError(status=501, detail="this engine provides no frames").model_dump_json()
            )
            await websocket.close(CLOSE_UNSUPPORTED)
            return
        slot: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue(maxsize=1)

        async def send() -> None:
            while True:
                meta, jpeg = await slot.get()
                await websocket.send_text(meta)
                await websocket.send_bytes(jpeg)

        async def wait_disconnect() -> None:
            while (await websocket.receive())["type"] != "websocket.disconnect":
                pass

        frames.add(slot)
        try:
            await _until_first_done(send(), wait_disconnect())
        finally:
            frames.remove(slot)


async def _until_first_done(*coros: Awaitable[None]) -> None:
    """Run until one finishes (or the client disconnects), then cancel the rest."""
    tasks = [asyncio.ensure_future(c) for c in coros]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            exc = t.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                raise exc
    finally:
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, Exception):
                await t


class FrameBridge:
    def __init__(
        self, engine: EngineAPI, *, max_fps: float = 10.0, target_px: int = 800,
        quality: int = 80,
    ) -> None:
        self.engine = engine
        self.max_fps = max_fps
        self.target_px = target_px
        self.quality = quality
        self.seq = 0
        self._clients: set[asyncio.Queue[tuple[str, bytes]]] = set()
        self._unsubscribe: Callable[[], None] | None = None
        self._pump: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()

    @property
    def watching(self) -> int:
        return len(self._clients)

    def add(self, slot: asyncio.Queue[tuple[str, bytes]]) -> None:
        self._clients.add(slot)
        if self._unsubscribe is None:
            loop = asyncio.get_running_loop()
            self._wake = asyncio.Event()

            def sink(ev: Event) -> None:
                if ev.kind == "frame_ready":
                    with contextlib.suppress(RuntimeError):  # loop closed
                        loop.call_soon_threadsafe(self._wake.set)

            self._unsubscribe = self.engine.subscribe(sink)
            self._pump = asyncio.ensure_future(self._run())

    def remove(self, slot: asyncio.Queue[tuple[str, bytes]]) -> None:
        self._clients.discard(slot)
        if not self._clients and self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
            if self._pump is not None:
                self._pump.cancel()
                self._pump = None

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        last = -math.inf
        while True:
            await self._wake.wait()
            wait = last + 1.0 / self.max_fps - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            self._wake.clear()  # frames that came during the wait are covered by this one
            got = self.engine.latest_frame()  # type: ignore[attr-defined]
            if got is None:
                continue
            last = loop.time()
            try:
                frame, jpeg = await asyncio.to_thread(
                    encode_frame, got[0], got[1], self.seq + 1, self.target_px, self.quality
                )
            except Exception:
                log.exception("live frame could not be encoded")
                continue
            self.seq = frame.seq
            item = (frame.model_dump_json(), jpeg)
            for slot in self._clients:
                if slot.full():
                    slot.get_nowait()  # drop the stale frame
                slot.put_nowait(item)


def encode_frame(
    pixels: Any, meta: dict[str, Any], seq: int, target_px: int = 800, quality: int = 80
) -> tuple[WsFrame, bytes]:
    """Bin a mono frame to at most `target_px` on the long side and JPEG it. Display range is
    the 0.5-99.5 percentile of the binned frame (reported, so the UI can say so)."""
    from PIL import Image

    a = np.asarray(pixels)
    if a.ndim != 2:
        raise ValueError(f"expected a mono 2-D frame, got shape {a.shape}")
    h, w = a.shape
    b = max(1, math.ceil(max(h, w) / target_px))
    hb, wb = h // b, w // b
    binned = a[: hb * b, : wb * b].astype(np.float32).reshape(hb, b, wb, b).mean(axis=(1, 3))
    lo, hi = (float(v) for v in np.percentile(binned, (0.5, 99.5)))
    if hi <= lo:
        hi = lo + 1.0
    u8 = np.clip((binned - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(u8).save(buf, format="JPEG", quality=quality)
    jpeg = buf.getvalue()
    frame = WsFrame(
        seq=seq, t=float(meta.get("t", 0.0)), width=wb, height=hb, binning=b,
        source_width=w, source_height=h, display_min=lo, display_max=hi,
        jpeg_bytes=len(jpeg), meta=meta,
    )
    return frame, jpeg
