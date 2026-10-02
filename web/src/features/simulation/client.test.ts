import { describe, expect, it, vi } from "vitest";

import { ClientError, httpClient } from "./client";
import { fakeClient } from "./fakeClient";
import { frameFromJson } from "./frame";
import { parseSimRest, runRest } from "./simRoute";

describe("httpClient", () => {
  it("GETs the simulation routes", async () => {
    const fetchFn = vi.fn(async () => new Response(JSON.stringify([]), { status: 200 }));
    const c = httpClient("/api/simulation", fetchFn as unknown as typeof fetch);
    await c.listRuns();
    await c.getRun("run a");
    await c.getSeries("r1");
    await c.getFrame("r1", 3, ["diameter", "orientation"]);
    await c.zipEntries("r1");
    expect(fetchFn.mock.calls.map((call) => (call as unknown[])[0])).toEqual([
      "/api/simulation/runs",
      "/api/simulation/runs/run%20a",
      "/api/simulation/runs/r1/series",
      "/api/simulation/runs/r1/frames/3?fields=diameter,orientation",
      "/api/simulation/runs/r1/zip/entries",
    ]);
    expect(c.zipUrl("r1", false)).toBe("/api/simulation/runs/r1/zip");
    expect(c.zipUrl("r1", true)).toBe("/api/simulation/runs/r1/zip?trajectory=1");
  });

  it("turns an error status into a ClientError with the server's detail", async () => {
    const fetchFn = async () => new Response(JSON.stringify({ detail: "no simulation run x" }), { status: 404 });
    const c = httpClient("/api/simulation", fetchFn as unknown as typeof fetch);
    await expect(c.getRun("x")).rejects.toMatchObject({ status: 404, message: expect.stringContaining("no simulation run x") });
    await expect(c.getRun("x")).rejects.toBeInstanceOf(ClientError);
  });
});

describe("fakeClient", () => {
  it("has a finished, a faulted and a running run", async () => {
    const c = fakeClient(() => 1_000_000_000_000);
    const runs = await c.listRuns();
    expect(Object.fromEntries(runs.map((r) => [r.run_id, r.progress.state]))).toEqual({
      "mock-sim-2d-running": "running",
      "mock-sim-3d-fault": "fault",
      "mock-sim-2d-done": "complete",
    });
    expect(runs[0].run_id).toBe("mock-sim-2d-running"); // newest first
    expect(c.source).toBe("mock");
    expect(c.zipUrl("mock-sim-2d-done", true)).toBeNull();
  });

  it("moves the running run forward with the clock", async () => {
    let t = 1_000_000_000_000;
    const c = fakeClient(() => t);
    const before = (await c.getRun("mock-sim-2d-running")).progress;
    t += 10_000;
    const after = (await c.getRun("mock-sim-2d-running")).progress;
    expect(after.steps_taken! - before.steps_taken!).toBe(1000); // 100 steps/s
    expect(after.frames_saved).toBeGreaterThan(before.frames_saved!);
    expect(after.eta).toBe(before.eta);
    const s = await c.getSeries("mock-sim-2d-running");
    expect(s.log.steps_taken.at(-1)).toBe(after.steps_taken);
    expect(s.observables).toBeNull();
  });

  it("serves frames that frameFromJson accepts, and only saved ones", async () => {
    const c = fakeClient(() => 1_000_000_000_000);
    const f = frameFromJson(await c.getFrame("mock-sim-3d-fault", 5));
    expect(f.dimensions).toBe(3);
    expect(f.n).toBe(128);
    expect(f.step).toBe(250);
    const info = await c.getRun("mock-sim-3d-fault");
    await expect(c.getFrame("mock-sim-3d-fault", info.progress.frames_saved!)).rejects.toMatchObject({ status: 404 });
    await expect(c.getRun("nope")).rejects.toMatchObject({ status: 404 });
  });

  it("gives a finished run its observables and log columns", async () => {
    const s = await fakeClient(() => 1_000_000_000_000).getSeries("mock-sim-2d-done");
    expect(Object.keys(s.log)).toEqual(expect.arrayContaining(["steps_taken", "temperature", "pressure"]));
    expect(s.curves[0]).toMatchObject({ path: "msd_curve", kind: "line" });
    expect(s.curves[0].y.every((v) => v !== null && v > 0)).toBe(true);
  });
});

describe("simulation routes", () => {
  it("reads runs/<run_id> and nothing else as a run", () => {
    expect(parseSimRest("")).toEqual({ runId: null });
    expect(parseSimRest("runs")).toEqual({ runId: null });
    expect(parseSimRest("runs/run-20260924-001")).toEqual({ runId: "run-20260924-001" });
    expect(parseSimRest("runs/run-20260924-001/")).toEqual({ runId: "run-20260924-001" });
    expect(parseSimRest("runs/a%20b?x=1")).toEqual({ runId: "a b" });
    expect(parseSimRest("runs/a/b")).toEqual({ runId: null });
    expect(parseSimRest("runs/%E0%A4%A")).toEqual({ runId: null });
    expect(parseSimRest(runRest("a b"))).toEqual({ runId: "a b" });
  });
});
