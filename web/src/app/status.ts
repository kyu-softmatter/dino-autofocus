import { useCallback, useEffect, useRef, useState } from "react";

import { type EventOut, useClient, useEngineEvents, useEventsConnected } from "./client";

/**
 * Reading the engine's state for the status bar. `GET /api/state` is untyped in
 * the OpenAPI (the engine snapshot is a dict), so these readers accept what the
 * engine sends today (T-011 runner) and the ui-spec 4.4 event shapes, and treat
 * anything else as unknown rather than guessing.
 */

export interface Positions {
  x_um?: number | null;
  y_um?: number | null;
  z_um?: number | null;
  errors?: Record<string, string>;
  [k: string]: unknown;
}

export interface Light {
  name: string;
  on: boolean | null; // null = unknown or unreadable
  raw: unknown;
}

export interface LightsView {
  lights: Light[];
  verified: boolean | null;
  error: string | null;
}

export interface RunningOp {
  op_id: string;
  op: string;
  state?: string;
}

export interface LastShutdown {
  t?: number;
  all_off?: boolean;
  [k: string]: unknown;
}

export interface EngineStatus {
  loaded: boolean;
  error: string | null;
  connected: boolean;
  positions: Positions | null;
  lights: LightsView | null;
  running: RunningOp[];
  lastShutdown: LastShutdown | null;
}

const OFF = new Set(["0", "off", "false", "closed"]);
const ON = new Set(["1", "on", "true", "open"]);

export function lightIsOn(v: unknown): boolean | null {
  if (typeof v === "boolean") return v;
  if (typeof v === "number") return v === 0 ? false : v === 1 ? true : null;
  if (typeof v === "string") {
    const s = v.trim().toLowerCase();
    if (OFF.has(s)) return false;
    if (ON.has(s)) return true;
  }
  if (v && typeof v === "object" && "state" in v) return lightIsOn((v as { state: unknown }).state);
  return null;
}

/** Lights from a snapshot `lights` value or a `light_changed` event's data. */
export function readLights(data: unknown): LightsView | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Record<string, unknown>;
  const verified = typeof d.verified === "boolean" ? d.verified : null;
  const error = typeof d.error === "string" ? d.error : null;
  let lights: Light[] = [];
  if (d.state && typeof d.state === "object") {
    // runner: {state: {device: read}, verified, records}
    lights = Object.entries(d.state as Record<string, unknown>).map(([name, raw]) => ({
      name,
      on: lightIsOn(raw),
      raw,
    }));
  } else if ("dialamp" in d || "aura" in d) {
    // ui-spec 4.4: {dialamp: "on"|"off"|"unknown", aura: {state, line, intensity_permille}}
    if ("dialamp" in d) lights.push({ name: "DiaLamp", on: lightIsOn(d.dialamp), raw: d.dialamp });
    if ("aura" in d) lights.push({ name: "Aura", on: lightIsOn(d.aura), raw: d.aura });
  }
  return { lights, verified, error };
}

function readPositions(data: unknown): Positions | null {
  return data && typeof data === "object" ? (data as Positions) : null;
}

function readRunning(data: unknown): RunningOp[] {
  if (!Array.isArray(data)) return [];
  return data
    .filter((o): o is Record<string, unknown> => !!o && typeof o === "object")
    .map((o) => ({ op_id: String(o.op_id ?? ""), op: String(o.op ?? ""), state: o.state as string }));
}

function readLastShutdown(data: unknown): LastShutdown | null {
  return data && typeof data === "object" ? (data as LastShutdown) : null;
}

/** Kinds after which the running list may have changed: re-read the snapshot. */
const LIFECYCLE = new Set([
  "started", "finished", "aborted", "error", "refused", "confirmed", "planned", "session_changed",
]);

export function useEngineStatus(): EngineStatus {
  const client = useClient();
  const connected = useEventsConnected();
  const [s, setS] = useState<Omit<EngineStatus, "connected">>({
    loaded: false,
    error: null,
    positions: null,
    lights: null,
    running: [],
    lastShutdown: null,
  });
  const alive = useRef(true);

  const reload = useCallback(async () => {
    try {
      const snap = await client.get<Record<string, unknown>>("/api/state");
      if (!alive.current) return;
      setS({
        loaded: true,
        error: null,
        positions: readPositions(snap.positions),
        lights: readLights(snap.lights),
        running: readRunning(snap.running),
        lastShutdown: readLastShutdown(snap.last_shutdown_lights),
      });
    } catch (e) {
      if (alive.current) setS((p) => ({ ...p, error: e instanceof Error ? e.message : String(e) }));
    }
  }, [client]);

  useEffect(() => {
    alive.current = true;
    void reload();
    return () => {
      alive.current = false;
    };
  }, [reload]);

  // events in a gap are lost: re-read after every (re)connect
  useEffect(() => {
    if (connected) void reload();
  }, [connected, reload]);

  const onEvent = useCallback(
    (ev: EventOut) => {
      if (ev.kind === "position") setS((p) => ({ ...p, positions: readPositions(ev.data) }));
      else if (ev.kind === "light_changed") setS((p) => ({ ...p, lights: readLights(ev.data) }));
      else if (LIFECYCLE.has(ev.kind)) void reload();
    },
    [reload],
  );
  useEngineEvents(onEvent);

  return { ...s, connected };
}

// -- assistant (PLAN D7) ----------------------------------------------------------------

export type DataStage = "prompt_only" | "text" | "images";

export interface AssistantStatus {
  available: boolean;
  provider: string | null; // "fake" | "anthropic"
  connected: boolean | null;
  data_stage: DataStage | string | null;
}

const UNAVAILABLE: AssistantStatus = {
  available: false,
  provider: null,
  connected: null,
  data_stage: null,
};

export function readAssistantStatus(body: unknown): AssistantStatus {
  if (!body || typeof body !== "object") return UNAVAILABLE;
  const b = body as Record<string, unknown>;
  const stage = b.data_stage ?? b.data_policy ?? null;
  return {
    available: true,
    provider: typeof b.provider === "string" ? b.provider : null,
    connected: typeof b.connected === "boolean" ? b.connected : null,
    data_stage: typeof stage === "string" ? stage : null,
  };
}

/** `GET /api/assistant/status` (T-013). Anything but a JSON answer reads as unavailable. */
export function useAssistantStatus(): AssistantStatus {
  const client = useClient();
  const connected = useEventsConnected();
  const [st, setSt] = useState<AssistantStatus>(UNAVAILABLE);
  useEffect(() => {
    let live = true;
    client
      .get("/api/assistant/status")
      .then((b) => live && setSt(readAssistantStatus(b)))
      .catch(() => live && setSt(UNAVAILABLE));
    return () => {
      live = false;
    };
  }, [client, connected]);
  return st;
}
