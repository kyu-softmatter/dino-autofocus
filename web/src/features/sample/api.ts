/**
 * Sample screen API: wire types, the client interface, an HTTP client and a fake.
 *
 * TEMPORARY until gen:api, T-009: the types below are written by hand from
 * docs/screens/sample.md. When `src/api/` has the generated types, replace the
 * "Wire types" section with re-exports from there; nothing else in
 * features/sample/ names a wire type from anywhere but this file.
 */

import { createContext, useContext } from "react";

// ---------------------------------------------------------------- Wire types

export type GeometryKind = "number" | "pair" | "choice";
export type GeometryRaw = number | [number, number] | string;

export interface GeometryField {
  key: string;
  label: string;
  kind: GeometryKind;
  unit: string | null;
  choices: string[] | null;
  default: GeometryRaw | null;
  /** feeds a safety limit in the engine (coverslip, sample thickness, orientation) */
  safety: boolean;
}

export interface ValueSource {
  kind: "entered" | "default" | "not_set";
  by: string | null;
  t: string | null;
}

export interface GeometryValue {
  value: GeometryRaw | null;
  source: ValueSource;
}

export interface Geometry {
  values: Record<string, GeometryValue>;
}

export interface SampleSummary {
  sample_id: string;
  created: string;
  fitted_at: string | null;
  objectives_used: string[];
  last_session: { session_id: string; opened_at: string } | null;
  awaiting_return: boolean;
  /** made by sample_new, no session yet */
  reserved: boolean;
}

export interface Hole {
  centre_um: [number, number];
  diameter_mm: number;
  fit_rms_um: number;
  n_points: number;
  arc_deg: number;
  fitted_at: string | null;
  /** the engine's own words about the fit, e.g. "partial trace" (T-031); shown as is */
  status: string | null;
}

export interface SampleDetail extends SampleSummary {
  dir: string;
  hole: Hole | null;
  calibration: { um_per_px: number; objective: string } | null;
  counts: { scans: number; maps: number; flags: number };
}

export interface StepState {
  done: boolean;
  by: string | null;
  t: string | null;
}

export interface LoadingState {
  session_id: string | null;
  geometry: StepState;
  person: StepState;
  image: StepState & { ok: boolean | null; why: string | null; result_ref: string | null };
  /** decided by the engine's sample view; the screen never combines the steps */
  confirmed: boolean;
}

/** Sample-specific pre-click facts from this area's router, GET /api/sample/access */
export interface SampleAccess {
  /** local request only (G9) */
  can_open_folder: boolean;
  /** why sample_open / sample_new would be refused now (a session is open for another sample) */
  open_reason: string | null;
}

/**
 * Generic pre-click verdicts (ui-spec 7.0: remote, role, control, session, running op), the same
 * for every screen: `GET /api/permissions?ops=a,b` -> `{op: {allowed, reason}}` (T-009b, backed by
 * T-011 `check()`). The screen reads them only through `SampleApi.permissions()`.
 */
export interface Permission {
  allowed: boolean;
  reason: string | null;
}
export type Permissions = Partial<Record<SampleOp, Permission>>;

/** the one fallback for every screen: no verdict means the control is off */
export const PERMISSION_UNAVAILABLE = "Permission check unavailable";

/**
 * The screen's only way to the shared verdicts. If `/api/permissions` cannot be read, or its answer
 * leaves an op out, that op is off with `PERMISSION_UNAVAILABLE`. A failure never counts as allowed.
 * (The shell's Abort and Lights off do not go through this.)
 */
export async function readPermissions(
  api: SampleApi,
  ops: readonly SampleOp[],
): Promise<Record<SampleOp, Permission>> {
  let got: Permissions = {};
  try {
    got = await api.permissions(ops);
  } catch {
    got = {};
  }
  const off: Permission = { allowed: false, reason: PERMISSION_UNAVAILABLE };
  return Object.fromEntries(ops.map((op) => [op, got[op] ?? off])) as Record<SampleOp, Permission>;
}

/** engine snapshot()["sample"] via GET /api/state (T-011) */
export interface CurrentSample {
  sample_id: string;
  reserved: boolean;
  session_id: string | null;
}

export interface CommandIn {
  kind: "start";
  op: SampleOp;
  args: Record<string, unknown>;
}

export interface EventOut {
  kind: string;
  op_id: string;
  data: Record<string, unknown>;
  t: number;
}

// ------------------------------------------------------------ Client interface

export const SAMPLE_OPS = [
  "sample_open",
  "sample_new",
  "sample_geometry_set",
  "loading_confirm_person",
  "loading_check_image",
] as const;
export type SampleOp = (typeof SAMPLE_OPS)[number];

/** accepted: the result comes as events. refused: the server's 403 detail */
export type SendResult = { ok: true; op_id: string } | { ok: false; reason: string };

export interface SampleApi {
  list(): Promise<SampleSummary[]>;
  fields(): Promise<GeometryField[]>;
  detail(sampleId: string): Promise<SampleDetail>;
  geometry(sampleId: string): Promise<Geometry>;
  loading(sampleId: string): Promise<LoadingState>;
  access(sampleId: string | null): Promise<SampleAccess>;
  permissions(ops: readonly SampleOp[]): Promise<Permissions>;
  current(): Promise<CurrentSample | null>;
  send(cmd: CommandIn): Promise<SendResult>;
  openFolder(sampleId: string): Promise<SendResult>;
  /** /ws/events; returns the unsubscribe function */
  subscribe(onEvent: (ev: EventOut) => void): () => void;
}

// ----------------------------------------------------------------- HTTP client

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return (await r.json()) as T;
}

async function post(path: string, body: unknown): Promise<SendResult> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = (await r.json().catch(() => ({}))) as { op_id?: string; detail?: unknown };
  if (r.ok) return { ok: true, op_id: payload.op_id ?? "" };
  return { ok: false, reason: typeof payload.detail === "string" ? payload.detail : `refused (${r.status})` };
}

const enc = encodeURIComponent;

export const httpSampleApi: SampleApi = {
  list: () => getJson("/api/sample/list"),
  fields: () => getJson("/api/sample/geometry-fields"),
  detail: (id) => getJson(`/api/sample/${enc(id)}`),
  geometry: (id) => getJson(`/api/sample/${enc(id)}/geometry`),
  loading: (id) => getJson(`/api/sample/${enc(id)}/loading`),
  access: (id) => getJson(`/api/sample/access${id ? `?sample_id=${enc(id)}` : ""}`),
  // a failure throws; readPermissions() turns it into the shared fallback
  permissions: (ops) => getJson<Permissions>(`/api/permissions?ops=${ops.join(",")}`),
  current: async () => ((await getJson<{ sample?: CurrentSample | null }>("/api/state")).sample ?? null),
  send: (cmd) => post("/api/commands", cmd),
  openFolder: (id) => post(`/api/sample/${enc(id)}/open-folder`, {}),
  subscribe(onEvent) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/events`);
    ws.onmessage = (m) => onEvent(JSON.parse(String(m.data)) as EventOut);
    return () => ws.close();
  },
};

// ------------------------------------------------------------------ Fake client

/**
 * The provisional F3.1 field list (PLAN 10절; docs/screens/sample.md 2). On the
 * web side it lives only here, as the fake server's answer; the screen renders
 * whatever `fields()` returns.
 */
export const PROVISIONAL_FIELDS: GeometryField[] = [
  { key: "sample_size_mm", label: "Sample size", kind: "pair", unit: "mm", choices: null, default: [24, 50], safety: false },
  { key: "chamber_shape", label: "Chamber", kind: "choice", unit: null, choices: ["hole"], default: "hole", safety: false },
  { key: "hole_diameter_mm", label: "Hole diameter", kind: "number", unit: "mm", choices: null, default: null, safety: false },
  { key: "coverslip_thickness_um", label: "Coverslip thickness", kind: "number", unit: "µm", choices: null, default: 170, safety: true },
  { key: "sample_thickness_um", label: "Sample thickness", kind: "number", unit: "µm", choices: null, default: null, safety: true },
  { key: "orientation", label: "Orientation", kind: "choice", unit: null, choices: ["upright", "flipped"], default: null, safety: true },
];

const step = (): StepState => ({ done: false, by: null, t: null });

export function emptyLoading(sessionId: string | null = null): LoadingState {
  return {
    session_id: sessionId,
    geometry: step(),
    person: step(),
    image: { ...step(), ok: null, why: null, result_ref: null },
    confirmed: false,
  };
}

interface FakeSample {
  detail: SampleDetail;
  geometry: Geometry;
  loading: LoadingState;
}

/**
 * In-memory stand-in for the server and engine, for tests and for work before
 * T-009. It records every command and answers with whatever the test sets; it
 * never decides a refusal on its own except through `refuse`.
 */
export class FakeSampleApi implements SampleApi {
  samples = new Map<string, FakeSample>();
  fieldList: GeometryField[] = PROVISIONAL_FIELDS;
  currentSample: CurrentSample | null = null;
  accessFor: (id: string | null) => SampleAccess = () => ({ can_open_folder: true, open_reason: null });
  /** the fake /api/permissions answer per op; default: allowed */
  permissionFor: (op: SampleOp) => Permission = () => ({ allowed: true, reason: null });
  /** make the fake /api/permissions fail, as a 404 or a dropped connection would */
  permissionsFail = false;
  sent: CommandIn[] = [];
  opened: string[] = [];
  /** op -> refusal detail, as the server's 403 would give */
  refuse = new Map<SampleOp, string>();
  private listeners = new Set<(ev: EventOut) => void>();
  private nextOp = 1;

  addSample(id: string, over: Partial<SampleDetail> = {}, geometry?: Geometry, loading?: LoadingState): void {
    const values: Record<string, GeometryValue> = {};
    for (const f of this.fieldList) {
      values[f.key] =
        f.default === null
          ? { value: null, source: { kind: "not_set", by: null, t: null } }
          : { value: f.default, source: { kind: "default", by: null, t: null } };
    }
    this.samples.set(id, {
      detail: {
        sample_id: id,
        created: "2026-10-01T10:00:00",
        fitted_at: null,
        objectives_used: [],
        last_session: null,
        awaiting_return: false,
        reserved: false,
        dir: `D:\\AutoFocus\\samples\\${id}`,
        hole: null,
        calibration: null,
        counts: { scans: 0, maps: 0, flags: 0 },
        ...over,
      },
      geometry: geometry ?? { values },
      loading: loading ?? emptyLoading(),
    });
  }

  private get(id: string): FakeSample {
    const s = this.samples.get(id);
    if (!s) throw new Error(`/api/sample/${id}: 404 unknown sample`);
    return s;
  }

  async list() {
    return [...this.samples.values()]
      .map((s) => s.detail)
      .sort((a, b) => b.created.localeCompare(a.created));
  }
  async fields() {
    return this.fieldList;
  }
  async detail(id: string) {
    return this.get(id).detail;
  }
  async geometry(id: string) {
    return this.get(id).geometry;
  }
  async loading(id: string) {
    return this.get(id).loading;
  }
  async access(id: string | null) {
    return this.accessFor(id);
  }
  async permissions(ops: readonly SampleOp[]) {
    if (this.permissionsFail) throw new Error("/api/permissions: 404");
    return Object.fromEntries(ops.map((op) => [op, this.permissionFor(op)])) as Permissions;
  }
  async current() {
    return this.currentSample;
  }
  async send(cmd: CommandIn): Promise<SendResult> {
    this.sent.push(cmd);
    const why = this.refuse.get(cmd.op);
    if (why !== undefined) return { ok: false, reason: why };
    return { ok: true, op_id: `op-${this.nextOp++}` };
  }
  async openFolder(id: string): Promise<SendResult> {
    if (!this.accessFor(id).can_open_folder) return { ok: false, reason: "Open folder works on the microscope PC only" };
    this.opened.push(id);
    return { ok: true, op_id: "" };
  }
  subscribe(onEvent: (ev: EventOut) => void) {
    this.listeners.add(onEvent);
    return () => {
      this.listeners.delete(onEvent);
    };
  }
  /** test helper: deliver an event as /ws/events would */
  emit(kind: string, data: Record<string, unknown> = {}, op_id = ""): void {
    for (const l of this.listeners) l({ kind, op_id, data, t: Date.now() / 1000 });
  }
}

// --------------------------------------------------------------------- Context

const ApiContext = createContext<SampleApi>(httpSampleApi);

export const SampleApiProvider = ApiContext.Provider;

export function useSampleApi(): SampleApi {
  return useContext(ApiContext);
}
