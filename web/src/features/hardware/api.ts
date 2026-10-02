/**
 * Temporary until gen:api (T-009): hand-written types for the hardware router
 * (docs/screens/hardware.md 1) and the common endpoints, the real client, and a
 * fake client for tests. The screen imports types and clients only from here,
 * so moving to `src/api/` is a change to this one file.
 */

import { createContext, useContext } from "react";

// --- hardware router (`/api/hardware/*`) ---

export interface DeviceRow {
  label: string;
  role?: string;
  type?: string;
  library?: string;
  present: boolean;
  /** a read of its state succeeded and was checked; null = not reported */
  read_back: boolean | null;
  /** a write was read back correctly; null = not tested yet (ops-spec 5) */
  write_verified: boolean | null;
  note?: string;
}

export interface ObjectiveRow {
  label: string;
  state?: number;
  magnification?: number;
  na?: number;
  immersion?: string;
  working_distance_um?: number | null;
  pixel_um?: number;
}

export interface ConfirmedItem {
  value: string;
  by?: string;
  at?: string;
}

export interface HardwareProfile {
  detected_at: string;
  backend: string;
  host?: string;
  config?: { path?: string; sha256?: string; changed_during_load?: boolean; startup_preset_applied?: boolean };
  /** sha256 of the previous profile; null = no previous profile */
  previous_sha256?: string | null;
  /** top-level keys that differ from the previous profile */
  changed?: string[];
  devices: DeviceRow[];
  objectives: ObjectiveRow[];
  camera?: { name?: string; sensor?: [number, number]; bit_depth?: number; ceiling_adu?: number; pixel_type?: string };
  piezo?: { port?: string; connected?: boolean; z_um?: number | null; error?: string | null };
  human_confirmed: Record<string, ConfirmedItem>;
}

export interface HardwareProfileOut {
  profile: HardwareProfile | null;
  path: string | null;
  sha256: string | null;
}

export interface GateRow {
  op: string;
  enabled: boolean;
  reasons: string[];
  requires: { devices: string[]; objectives: string[]; confirmed: string[] };
}

/** `summary` of the last `finished(status)` (ops-spec 2). */
export interface StatusSummary {
  nosepiece_label?: string;
  nosepiece_state?: number;
  z_um?: number | null;
  pfs_enabled?: boolean | string;
  pfs_locked?: boolean | string;
  pfs_in_range?: string;
}

export interface StatusResultOut {
  op_id: string;
  t: number;
  user_id: string | null;
  summary: StatusSummary;
}

// --- common endpoints (T-009) ---

export interface Readback {
  device: string;
  property: string;
  wanted: unknown;
  read: unknown;
  verified: boolean;
}

/** `light_changed` data (ui-spec 4.0). */
export interface LightState {
  dialamp: "on" | "off" | "unknown";
  aura: { state: "on" | "off" | "unknown"; line?: string | null; intensity_permille?: number | null };
  verified: boolean;
  records?: Readback[];
}

/** `GET /api/permissions?ops=...` (T-009b, from T-011 `check()`): why a command would be refused. */
export interface Permission {
  allowed: boolean;
  reason: string | null;
}

export type Permissions = Record<string, Permission>;

/** The commands this screen sends; `lights_off` is a command kind, the rest are `start` ops. */
export const SCREEN_OPS = ["hardware_scan", "hardware_confirm", "status", "light_set", "lights_off"] as const;

export interface EngineState {
  lights?: LightState | null;
  lights_t?: number | null;
  running?: { op: string; op_id: string } | null;
  position?: { z_um?: number | null } | null;
}

export interface EngineEvent {
  kind: string;
  op_id: string;
  data: Record<string, unknown>;
  t: number;
}

export type CommandIn =
  | { kind: "start"; op: string; args?: Record<string, unknown> }
  | { kind: "lights_off" };

export type CommandResult = { ok: true; op_id: string } | { ok: false; status: number; detail: string };

export interface HardwareApi {
  profile(): Promise<HardwareProfileOut>;
  gates(): Promise<GateRow[]>;
  status(): Promise<StatusResultOut | null>;
  state(): Promise<EngineState>;
  permissions(ops: readonly string[]): Promise<Permissions>;
  submit(cmd: CommandIn): Promise<CommandResult>;
  /** returns the unsubscribe function */
  subscribe(onEvent: (ev: EngineEvent) => void): () => void;
}

// --- real client ---

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return (await r.json()) as T;
}

/** Every op refused with one reason: used when the permission endpoint cannot be read. */
export function refuseAll(ops: readonly string[], reason: string): Permissions {
  return Object.fromEntries(ops.map((op) => [op, { allowed: false, reason }]));
}

export const httpHardwareApi: HardwareApi = {
  profile: () => getJson("/api/hardware/profile"),
  gates: () => getJson("/api/hardware/gates"),
  status: () => getJson("/api/hardware/status"),
  state: () => getJson("/api/state"),
  async permissions(ops) {
    try {
      return await getJson<Permissions>(`/api/permissions?ops=${ops.map(encodeURIComponent).join(",")}`);
    } catch (e) {
      return refuseAll(ops, `permissions unavailable (${String(e)})`);
    }
  },
  async submit(cmd) {
    const r = await fetch("/api/commands", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cmd),
    });
    const body = (await r.json().catch(() => ({}))) as { op_id?: string; detail?: unknown };
    if (r.ok && typeof body.op_id === "string") return { ok: true, op_id: body.op_id };
    return { ok: false, status: r.status, detail: String(body.detail ?? `HTTP ${r.status}`) };
  },
  subscribe(onEvent) {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/events`);
    ws.onmessage = (m) => {
      try {
        const msg = JSON.parse(String(m.data)) as { type?: string; event?: EngineEvent };
        if (msg.type === "event" && msg.event) onEvent(msg.event);
      } catch {
        // not an event message
      }
    };
    return () => ws.close();
  },
};

export const HardwareApiContext = createContext<HardwareApi>(httpHardwareApi);

export function useHardwareApi(): HardwareApi {
  return useContext(HardwareApiContext);
}

// --- fake client (tests) ---

export interface FakeHardwareApi extends HardwareApi {
  sent: CommandIn[];
  /** deliver an event to every subscriber */
  emit(ev: Partial<EngineEvent> & { kind: string }): void;
  data: {
    profile: HardwareProfileOut;
    gates: GateRow[];
    status: StatusResultOut | null;
    state: EngineState;
    /** ops missing here are allowed */
    permissions: Permissions;
    submitResult: CommandResult;
  };
}

export function createFakeHardwareApi(init: Partial<FakeHardwareApi["data"]> = {}): FakeHardwareApi {
  const subscribers = new Set<(ev: EngineEvent) => void>();
  const data: FakeHardwareApi["data"] = {
    profile: { profile: null, path: null, sha256: null },
    gates: [],
    status: null,
    state: {},
    permissions: {},
    submitResult: { ok: true, op_id: "op-1" },
    ...init,
  };
  const api: FakeHardwareApi = {
    sent: [],
    data,
    profile: async () => data.profile,
    gates: async () => data.gates,
    status: async () => data.status,
    state: async () => data.state,
    permissions: async (ops) =>
      Object.fromEntries(ops.map((op) => [op, data.permissions[op] ?? { allowed: true, reason: null }])),
    async submit(cmd) {
      api.sent.push(cmd);
      return data.submitResult;
    },
    subscribe(onEvent) {
      subscribers.add(onEvent);
      return () => subscribers.delete(onEvent);
    },
    emit(ev) {
      const full: EngineEvent = { op_id: "", data: {}, t: Date.now() / 1000, ...ev };
      for (const s of subscribers) s(full);
    },
  };
  return api;
}
