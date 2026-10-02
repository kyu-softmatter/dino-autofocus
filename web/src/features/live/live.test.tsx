import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Client, ClientProvider } from "../../app/client";
import { fakeTransport } from "../../test/fakes";
import { FpsMeter, FramePairer } from "./frames";
import { LiveView } from "./LiveView";

const META = {
  type: "frame",
  seq: 7,
  t: 1759300000.5,
  width: 800,
  height: 800,
  binning: 3,
  source_width: 2400,
  source_height: 2400,
  display_min: 102,
  display_max: 3435,
  jpeg_bytes: 4,
  meta: { z_um: 2989.42 },
};

const jpeg = () => new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xd9])], { type: "image/jpeg" });

describe("FramePairer", () => {
  it("pairs the metadata text with the next binary message", () => {
    const p = new FramePairer();
    expect(p.feed(JSON.stringify(META))).toBeNull();
    const got = p.feed(jpeg());
    expect(got).toMatchObject({ kind: "frame", meta: { seq: 7, binning: 3 } });
  });

  it("drops a JPEG with no metadata before it, or of the wrong length", () => {
    const p = new FramePairer();
    expect(p.feed(jpeg())).toBeNull();
    p.feed(JSON.stringify({ ...META, jpeg_bytes: 99 }));
    expect(p.feed(jpeg())).toBeNull();
  });

  it("reports a server error message", () => {
    expect(new FramePairer().feed(JSON.stringify({ type: "error", status: 501, detail: "this engine provides no frames" })))
      .toEqual({ kind: "error", status: 501, detail: "this engine provides no frames" });
  });
});

describe("FpsMeter", () => {
  it("measures the receive rate over recent frames", () => {
    const m = new FpsMeter(5);
    expect(m.tick(0)).toBeNull();
    for (let i = 1; i <= 4; i++) m.tick(i * 100);
    expect(m.tick(500)).toBeCloseTo(10);
  });
});

describe("LiveView", () => {
  beforeEach(() => {
    let n = 0;
    URL.createObjectURL = vi.fn(() => `blob:frame-${++n}`);
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.useRealTimers());

  function mount() {
    const t = fakeTransport({});
    const client = new Client(t.transport, "127.0.0.1");
    let clock = 0;
    const now = () => (clock += 100);
    render(
      <ClientProvider client={client}>
        <LiveView now={now} />
      </ClientProvider>,
    );
    return t.sockets.find((s) => s.path === "/ws/frames")!;
  }

  function sendBinary(ws: { onmessage: ((e: MessageEvent) => void) | null }, b: Blob) {
    ws.onmessage?.(new MessageEvent("message", { data: b }));
  }

  it("draws frames with their time, size and the receive rate", () => {
    const ws = mount();
    act(() => {
      ws.open();
      for (let i = 0; i < 3; i++) {
        ws.send(META);
        sendBinary(ws, jpeg());
      }
    });
    expect(screen.getByTestId("live-conn").textContent).toBe("frames: connected");
    expect(screen.getByRole("img", { name: "Live camera frame" }).getAttribute("src")).toBe("blob:frame-3");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:frame-2");
    expect(screen.getByTestId("live-fps").textContent).toBe("10.0 fps");
    expect(screen.getByTestId("live-size").textContent).toContain("bin 3 of 2400×2400");
    expect(screen.getByText("Z 2989.42 µm")).toBeTruthy();
    expect(screen.getByTestId("live-z").getAttribute("title")).toContain("camera buffer");
  });

  it("shows two cameras side by side, one at a time, or merged", () => {
    const ws = mount();
    act(() => {
      ws.open();
      for (const camera of ["Kinetix_red", "Kinetix_blue"]) {
        ws.send({ ...META, camera });
        sendBinary(ws, jpeg());
      }
    });
    expect(screen.queryByRole("img", { name: "Live camera frame" })).toBeNull();
    expect(screen.getByRole("img", { name: "Live frame Kinetix_blue" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Live frame Kinetix_red" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Side by side" }).getAttribute("aria-pressed")).toBe("true");

    act(() => screen.getByRole("button", { name: "Kinetix_red" }).click());
    expect(screen.getByRole("img", { name: "Live frame Kinetix_red" })).toBeTruthy();
    expect(screen.queryByRole("img", { name: "Live frame Kinetix_blue" })).toBeNull();

    act(() => screen.getByRole("button", { name: "Merged" }).click());
    expect(screen.getByRole("img", { name: "Merged camera frame" })).toBeTruthy();
    expect(screen.getByRole("figure", { name: "Merged cameras" }).textContent).toContain("Kinetix_blue");
  });

  it("keeps each camera's newest frame and frees only that camera's old one", () => {
    const ws = mount();
    act(() => {
      ws.open();
      ws.send({ ...META, camera: "Kinetix_blue" });
      sendBinary(ws, jpeg()); // frame-1
      ws.send({ ...META, camera: "Kinetix_red" });
      sendBinary(ws, jpeg()); // frame-2
      ws.send({ ...META, camera: "Kinetix_red", seq: 9 });
      sendBinary(ws, jpeg()); // frame-3
    });
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:frame-2");
    expect(URL.revokeObjectURL).not.toHaveBeenCalledWith("blob:frame-1");
    expect(screen.getByRole("img", { name: "Live frame Kinetix_blue" }).getAttribute("src")).toBe("blob:frame-1");
    expect(screen.getByRole("img", { name: "Live frame Kinetix_red" }).getAttribute("src")).toBe("blob:frame-3");
  });

  it("says so, and does not retry, when the engine provides no frames", () => {
    vi.useFakeTimers();
    const ws = mount();
    act(() => {
      ws.send({ type: "error", status: 501, detail: "this engine provides no frames" });
      ws.close();
    });
    expect(screen.getByTestId("live-conn").textContent).toBe("frames: not available");
    expect(screen.getByText("this engine provides no frames")).toBeTruthy();
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByTestId("live-conn").textContent).toBe("frames: not available");
  });

  it("reconnects after the socket drops", () => {
    vi.useFakeTimers();
    const t = fakeTransport({});
    const client = new Client(t.transport, "127.0.0.1");
    render(
      <ClientProvider client={client}>
        <LiveView />
      </ClientProvider>,
    );
    const frames = () => t.sockets.filter((s) => s.path === "/ws/frames");
    act(() => frames()[0].close());
    expect(screen.getByTestId("live-conn").textContent).toBe("frames: closed");
    act(() => vi.advanceTimersByTime(2000));
    expect(frames()).toHaveLength(2);
  });
});
