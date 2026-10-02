import { describe, expect, it, vi } from "vitest";

import { AREAS, areaIdOfPath, buildRegistry, registry } from "./areas";
import { areaFromHash, hashOfArea } from "./route";

const screen = () => Promise.resolve({ default: () => null });

describe("area registry", () => {
  it("lists every area in navigation order, with no screen yet as a placeholder", () => {
    const r = buildRegistry({});
    expect(r.map((e) => e.id)).toEqual(AREAS.map((a) => a.id));
    expect(r.every((e) => e.load === undefined)).toBe(true);
  });

  it("picks up features/<id>/index.tsx for a registered area", () => {
    const r = buildRegistry({ "../features/map/index.tsx": screen });
    expect(r.find((e) => e.id === "map")?.load).toBe(screen);
    expect(r.find((e) => e.id === "sample")?.load).toBeUndefined();
  });

  it("ignores a feature folder that is not an area, and says so", () => {
    const warn = vi.fn();
    const r = buildRegistry({ "../features/extra/index.tsx": screen }, warn);
    expect(r).toHaveLength(AREAS.length);
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("features/extra"));
  });

  it("reads only <id>/index.tsx paths", () => {
    expect(areaIdOfPath("../features/live/index.tsx")).toBe("live");
    expect(areaIdOfPath("../features/live/View.tsx")).toBeNull();
  });

  it("has the six areas of T-010 and simulation (PLAN v0.4)", () => {
    expect(registry.map((e) => e.id)).toEqual([
      "console", "hardware", "sample", "map", "objective", "live", "simulation",
    ]);
  });
});

describe("hash routing", () => {
  it("maps hashes to areas and falls back to the console", () => {
    expect(areaFromHash("#/map")).toBe("map");
    expect(areaFromHash("#/map/flags?x=1")).toBe("map");
    expect(areaFromHash("")).toBe("console");
    expect(areaFromHash("#/nowhere")).toBe("console");
    expect(hashOfArea("live")).toBe("#/live");
  });
});
