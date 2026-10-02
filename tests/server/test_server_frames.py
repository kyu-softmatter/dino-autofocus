from __future__ import annotations

import asyncio
import io
import json
import threading
import time

import numpy as np
import pytest
from PIL import Image

from dino_autofocus.server.ws import FrameBridge, encode_frame


@pytest.mark.parametrize(
    ("shape", "binning", "out"),
    [((3200, 3200), 4, (800, 800)), ((1200, 1600), 2, (600, 800)), ((300, 400), 1, (300, 400)),
     ((2048, 2048), 3, (682, 682))],
)
def test_encode_frame_size(shape, binning, out):
    rng = np.random.default_rng(1)
    frame, jpeg = encode_frame(rng.integers(0, 4096, shape, dtype=np.uint16), {"t": 1.0}, 3)
    assert (frame.binning, frame.height, frame.width) == (binning, *out)
    assert (frame.source_height, frame.source_width) == shape
    assert max(frame.width, frame.height) <= 800
    img = Image.open(io.BytesIO(jpeg))
    assert (img.format, img.mode, img.size) == ("JPEG", "L", (out[1], out[0]))
    assert frame.seq == 3 and frame.jpeg_bytes == len(jpeg)


def test_encode_frame_display_range():
    a = np.zeros((100, 100), np.uint16)
    a[:, 50:] = 4000
    frame, jpeg = encode_frame(a, {}, 1)
    assert (frame.display_min, frame.display_max) == (0.0, 4000.0)
    flat, _ = encode_frame(np.full((10, 10), 7, np.uint16), {}, 1)
    assert flat.display_max > flat.display_min  # no division by zero on a blank frame
    with pytest.raises(ValueError):
        encode_frame(np.zeros((4, 4, 3), np.uint8), {}, 1)


def test_bridge_rate_limit_and_latest_only(frame_engine):
    """200 frame_ready/s for 1 s from an engine thread: at most ~10 encodes, and a client that
    does not read keeps only the newest frame."""
    frame_engine.frame = (np.zeros((64, 64), np.uint16), {"t": 0.0})

    async def scenario():
        bridge = FrameBridge(frame_engine, max_fps=10.0)
        reader: asyncio.Queue = asyncio.Queue(maxsize=1)
        idle: asyncio.Queue = asyncio.Queue(maxsize=1)
        bridge.add(reader)
        bridge.add(idle)
        got = []

        async def read():
            while True:
                meta, _ = await reader.get()
                got.append(json.loads(meta)["seq"])

        stop = threading.Event()

        def produce():
            while not stop.is_set():
                frame_engine.frame = (frame_engine.frame[0], {"t": time.time()})
                frame_engine.emit("frame_ready")
                time.sleep(0.005)

        t = threading.Thread(target=produce)
        task = asyncio.ensure_future(read())
        t.start()
        await asyncio.sleep(1.0)
        stop.set()
        t.join()
        await asyncio.sleep(0.25)  # let the last encode land
        task.cancel()
        assert idle.qsize() == 1
        last_idle = json.loads(idle.get_nowait()[0])["seq"]
        bridge.remove(reader)
        bridge.remove(idle)
        assert frame_engine.sinks == []
        return got, last_idle, bridge.seq

    got, last_idle, seq = asyncio.run(scenario())
    assert 5 <= len(got) <= 12
    assert frame_engine.frame_reads <= 12
    assert got == sorted(got)
    assert last_idle == seq  # the idle client holds the newest frame, not the first
