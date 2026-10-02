import { afterEach, describe, expect, it, vi } from "vitest";

import { fakeTransport } from "../test/fakes";
import { Client, CommandRefused, EventStream, isLoopbackHost, ReadOnlyStore } from "./client";

afterEach(() => {
  vi.useRealTimers();
});

describe("read-only", () => {
  it("starts writable on the microscope PC and read-only from another host", () => {
    for (const h of ["127.0.0.1", "localhost", "[::1]", "app.localhost"]) expect(isLoopbackHost(h)).toBe(true);
    expect(isLoopbackHost("192.168.1.20")).toBe(false);
    expect(new ReadOnlyStore("127.0.0.1").get()).toEqual({ readOnly: false, why: null });
    expect(new ReadOnlyStore("lab-pc").get()).toEqual({ readOnly: true, why: "remote view" });
  });

  it("turns read-only when the server refuses a command with 403", async () => {
    const { transport, calls } = fakeTransport({
      "/api/commands": () => ({ status: 403, body: { detail: "remote viewers may send abort only" } }),
    });
    const client = new Client(transport, "127.0.0.1");
    const seen = vi.fn();
    client.readOnly.subscribe(seen);
    await expect(client.command({ kind: "start", op: "status" } as never)).rejects.toBeInstanceOf(CommandRefused);
    expect(client.readOnly.get()).toEqual({ readOnly: true, why: "remote viewers may send abort only" });
    expect(seen).toHaveBeenCalledTimes(1);
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ kind: "start", op: "status" });
  });

  it("returns the op_id of an accepted command", async () => {
    const { transport } = fakeTransport({ "/api/commands": () => ({ status: 200, body: { op_id: "op-1" } }) });
    await expect(new Client(transport, "127.0.0.1").command({ kind: "lights_off" } as never)).resolves.toBe("op-1");
  });
});

describe("EventStream", () => {
  it("delivers engine events and ignores other messages", () => {
    const { transport, sockets } = fakeTransport({});
    const es = new EventStream(transport);
    const got = vi.fn();
    es.on(got);
    es.start();
    expect(sockets[0].path).toBe("/ws/events");
    sockets[0].open();
    sockets[0].event("position", { z_um: 3048.7 });
    sockets[0].send({ type: "accepted", op_id: "x" });
    sockets[0].send("not json");
    expect(got).toHaveBeenCalledTimes(1);
    expect(got.mock.calls[0][0]).toMatchObject({ kind: "position", data: { z_um: 3048.7 } });
  });

  it("reports open/closed and reconnects with backoff", () => {
    vi.useFakeTimers();
    const { transport, sockets } = fakeTransport({});
    const es = new EventStream(transport, "/ws/events", () => 1000);
    const status = vi.fn();
    es.onStatus(status);
    es.start();
    sockets[0].open();
    sockets[0].close();
    expect(status.mock.calls.map((c) => c[0])).toEqual([true, false]);
    expect(sockets).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    expect(sockets).toHaveLength(2);
    es.stop();
    expect(sockets[1].closed).toBe(true);
    vi.advanceTimersByTime(5000);
    expect(sockets).toHaveLength(2);
  });
});
