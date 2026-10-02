/**
 * Temporary until gen:api, T-009: the map screen's API types, its HTTP client and a scripted fake.
 *
 * The shapes follow docs/screens/map.md sections 2-4. When `src/api/schema.ts` is generated from
 * the server's OpenAPI, replace the interfaces below with the generated ones; nothing else in
 * `features/map/` builds requests or parses responses, so that is a one-file change.
 */

export interface Box {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

export interface BoundaryPoint {
  x_um: number;
  y_um: number;
  t?: number;
}

export interface HoleFit {
  centre_um: [number, number];
  diameter_mm: number;
  fit_rms_um: number;
  n_points: number;
  arc_deg: number;
  /** epoch seconds */
  fitted_at: number | null;
}

export interface Visit {
  x_um: number;
  y_um: number;
  w_um: number;
  h_um: number;
  verdict: string | null;
  source?: string;
}

export interface MapState {
  sample_id: string;
  boundary: BoundaryPoint[];
  hole: HoleFit | null;
  expected_diameter_mm: number | null;
  visits: Visit[];
  scan_box_um: Box | null;
  allowed_box_um: Box | null;
  /** experiment session start, else engine start (epoch seconds) */
  session_started_at: number | null;
}

export type ResultKind = "scan_4x" | "sample_map";

export interface ResultSummary {
  result_id: string;
  kind: ResultKind;
  started: number | null;
  finished: number | null;
  light: string | null;
  n_tiles: number;
  grid_n: number;
  has_mosaic: boolean;
  scan_box_um: Box | null;
  allowed_box_um: Box | null;
}

export interface Tile {
  name: string;
  row: number;
  col: number;
  x_um: number;
  y_um: number;
  z_focus_um: number | null;
  focus_note: string;
  block_z_um: (number | null)[];
  blocks_per_side: number;
  dropout_z_um: number[];
}

export interface MosaicExtent extends Box {
  um_per_px: number;
  bin: number;
}

export interface ResultDetail extends ResultSummary {
  tiles: Tile[];
  fov_um: number;
  um_per_px: number;
  mosaic: MosaicExtent | null;
}

export interface Flag {
  flag_id: string;
  name: string;
  note: string;
  t: number;
  objective: string | null;
  x_um: number;
  y_um: number;
  /** ZDrive read-back when the flag was set */
  z_um: number | null;
  replaces: string | null;
  retired_at: number | null;
}

export type CandidateSource = "classical_candidate" | "person_confirmed" | "person_rejected";

export interface Candidate {
  candidate_id: string;
  x_um: number;
  y_um: number;
  source: CandidateSource;
  score: number | null;
  result_id: string | null;
  decides: string | null;
  t: number;
  by: string | null;
}

/** One message on /ws/events (engine/events.py `Event`). */
export interface EngineEvent {
  kind: string;
  op_id: string;
  data: Record<string, unknown>;
  t?: number;
}

/** POST /api/commands body (T-009 `CommandIn`). */
export interface CommandIn {
  kind: "start" | "abort" | "confirm" | "update";
  op?: string;
  op_id?: string;
  args?: Record<string, unknown>;
}

export interface Position {
  x_um: number | null;
  y_um: number | null;
  z_um: number | null;
}

/** The parts of GET /api/state (engine `snapshot()`, T-011) this screen reads. */
export interface Snapshot {
  sample: string | null;
  position: Position | null;
  objective: string | null;
  running: string | null;
}

/**
 * One entry of the shared `GET /api/permissions?ops=a,b` (T-009b, backed by T-011's check()):
 * whether the op may be sent now and, if not, why. The screen only shows these reasons; the
 * server and engine enforce them again on every request.
 */
export interface Permission {
  allowed: boolean;
  reason: string | null;
}

export type Permissions = Record<string, Permission>;

export type Unsubscribe = () => void;

export interface MapApi {
  snapshot(): Promise<Snapshot>;
  permissions(ops: readonly string[]): Promise<Permissions>;
  mapState(sampleId: string): Promise<MapState>;
  results(sampleId: string): Promise<ResultSummary[]>;
  result(sampleId: string, resultId: string): Promise<ResultDetail>;
  mosaicUrl(sampleId: string, resultId: string): string;
  flags(sampleId: string, includeRetired: boolean): Promise<Flag[]>;
  candidates(sampleId: string, includeRejected: boolean): Promise<Candidate[]>;
  /** common command endpoint; resolves to the op_id */
  command(cmd: CommandIn): Promise<string>;
  addFlag(sampleId: string, body: { x_um: number; y_um: number; name: string; note: string; replaces?: string }): Promise<string>;
  retireFlag(sampleId: string, flagId: string): Promise<string>;
  decideCandidate(sampleId: string, candidateId: string, decision: "confirm" | "reject"): Promise<string>;
  subscribe(onEvent: (ev: EngineEvent) => void): Unsubscribe;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
  }
}

// ---------------------------------------------------------------- HTTP client

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const enc = encodeURIComponent;

function isLoopbackHost(host: string): boolean {
  return host === "localhost" || host === "127.0.0.1" || host === "[::1]" || host === "::1";
}

export function httpMapApi(base = ""): MapApi {
  const get = <T,>(path: string) => fetch(`${base}${path}`).then((r) => json<T>(r));
  const post = <T,>(path: string, body: unknown) =>
    fetch(`${base}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<T>(r));
  const opId = (r: { op_id: string }) => r.op_id;
  const m = (sampleId: string) => `/api/map/${enc(sampleId)}`;

  return {
    snapshot: async () => {
      const s = await get<Record<string, unknown>>("/api/state");
      const pos = (s.position ?? null) as Position | null;
      return {
        sample: typeof s.sample === "string" ? s.sample : null,
        position: pos,
        objective: typeof s.objective === "string" ? s.objective : null,
        running: typeof s.running === "string" ? s.running : null,
      };
    },
    permissions: async (ops) => {
      try {
        return await get<Permissions>(`/api/permissions?ops=${ops.map(enc).join(",")}`);
      } catch (e) {
        // until T-009b serves /api/permissions: allow on this PC, read-only elsewhere.
        // The server refuses anything not allowed either way.
        if (!(e instanceof ApiError && e.status === 404)) throw e;
        const local = isLoopbackHost(window.location.hostname);
        const reason = local ? null : "Read-only: remote view";
        return Object.fromEntries(ops.map((op) => [op, { allowed: local, reason }]));
      }
    },
    mapState: (id) => get<MapState>(m(id)),
    results: (id) => get<ResultSummary[]>(`${m(id)}/results`),
    result: (id, rid) => get<ResultDetail>(`${m(id)}/results/${enc(rid)}`),
    mosaicUrl: (id, rid) => `${base}${m(id)}/results/${enc(rid)}/mosaic.png`,
    flags: (id, all) => get<Flag[]>(`${m(id)}/flags?include_retired=${all}`),
    candidates: (id, all) => get<Candidate[]>(`${m(id)}/candidates?include_rejected=${all}`),
    command: (cmd) => post<{ op_id: string }>("/api/commands", cmd).then(opId),
    addFlag: (id, body) => post<{ op_id: string }>(`${m(id)}/flags`, body).then(opId),
    retireFlag: (id, fid) => post<{ op_id: string }>(`${m(id)}/flags/${enc(fid)}/retire`, {}).then(opId),
    decideCandidate: (id, cid, d) =>
      post<{ op_id: string }>(`${m(id)}/candidates/${enc(cid)}/${d}`, {}).then(opId),
    subscribe: (onEvent) => {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${proto}//${window.location.host}${base}/ws/events`);
      ws.onmessage = (msg) => {
        try {
          onEvent(JSON.parse(String(msg.data)) as EngineEvent);
        } catch {
          // not an event; ignore
        }
      };
      return () => ws.close();
    },
  };
}

// ---------------------------------------------------------------- scripted fake (tests)

export interface FakeData {
  snapshot: Snapshot;
  /** ops not listed here are allowed */
  permissions: Permissions;
  maps: Record<string, MapState>;
  results: Record<string, ResultSummary[]>;
  details: Record<string, ResultDetail>;
  flags: Record<string, Flag[]>;
  candidates: Record<string, Candidate[]>;
}

export interface FakeMapApi extends MapApi {
  /** every command and record write, in order */
  sent: { route: string; body: unknown }[];
  /** push an event to every subscriber, as /ws/events would */
  emit(ev: EngineEvent): void;
  data: FakeData;
}

export function fakeMapApi(data: FakeData): FakeMapApi {
  const subs = new Set<(ev: EngineEvent) => void>();
  const sent: { route: string; body: unknown }[] = [];
  let n = 0;
  const record = (route: string, body: unknown) => {
    sent.push({ route, body });
    n += 1;
    return Promise.resolve(`op-${n}`);
  };
  const need = <T,>(v: T | undefined, what: string): Promise<T> =>
    v === undefined ? Promise.reject(new ApiError(404, `no ${what}`)) : Promise.resolve(v);

  return {
    data,
    sent,
    emit: (ev) => subs.forEach((s) => s(ev)),
    snapshot: () => Promise.resolve(data.snapshot),
    permissions: (ops) =>
      Promise.resolve(Object.fromEntries(ops.map((op) => [op, data.permissions[op] ?? { allowed: true, reason: null }]))),
    mapState: (id) => need(data.maps[id], `sample ${id}`),
    results: (id) => Promise.resolve(data.results[id] ?? []),
    result: (_id, rid) => need(data.details[rid], `result ${rid}`),
    mosaicUrl: (id, rid) => `fake://${id}/${rid}/mosaic.png`,
    flags: (id, all) => Promise.resolve((data.flags[id] ?? []).filter((f) => all || f.retired_at === null)),
    candidates: (id, all) =>
      Promise.resolve((data.candidates[id] ?? []).filter((c) => all || c.source !== "person_rejected")),
    command: (cmd) => record("/api/commands", cmd),
    addFlag: (id, body) => record(`/api/map/${id}/flags`, body),
    retireFlag: (id, fid) => record(`/api/map/${id}/flags/${fid}/retire`, {}),
    decideCandidate: (id, cid, d) => record(`/api/map/${id}/candidates/${cid}/${d}`, {}),
    subscribe: (onEvent) => {
      subs.add(onEvent);
      return () => subs.delete(onEvent);
    },
  };
}
