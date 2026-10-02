/**
 * Temporary until map.py lands in the generated types (T-009 / gen:api): the map router's response
 * types (docs/screens/map.md section 2), the shared permissions shape, and the calls to those
 * routes. Engine commands and events go through the shell's client (src/app/client.tsx); this file
 * only adds the map routes, so switching to generated types is a one-file change.
 */

import { type Client, CommandRefused } from "../../app/client";

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

/** The parts of GET /api/state (engine snapshot, T-011) this screen reads. */
export interface Snapshot {
  sample: string | null;
  position: { x_um: number | null; y_um: number | null; z_um: number | null } | null;
  objective: string | null;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);

export function readSnapshot(snap: Record<string, unknown>): Snapshot {
  const p = (snap.positions ?? snap.position ?? null) as Record<string, unknown> | null;
  return {
    sample: str(snap.sample) ?? str((snap.sample as { sample_id?: unknown } | null)?.sample_id),
    position: p && typeof p === "object" ? { x_um: num(p.x_um), y_um: num(p.y_um), z_um: num(p.z_um) } : null,
    objective: str(snap.objective) ?? str(p?.objective),
  };
}

const enc = encodeURIComponent;
const base = (sampleId: string) => `/api/map/${enc(sampleId)}`;

export const PATHS = {
  map: base,
  results: (id: string) => `${base(id)}/results`,
  result: (id: string, rid: string) => `${base(id)}/results/${enc(rid)}`,
  mosaic: (id: string, rid: string) => `${base(id)}/results/${enc(rid)}/mosaic.png`,
  flags: (id: string, all: boolean) => `${base(id)}/flags?include_retired=${all}`,
  candidates: (id: string, all: boolean) => `${base(id)}/candidates?include_rejected=${all}`,
  addFlag: (id: string) => `${base(id)}/flags`,
  retireFlag: (id: string, fid: string) => `${base(id)}/flags/${enc(fid)}/retire`,
  decide: (id: string, cid: string, d: "confirm" | "reject") => `${base(id)}/candidates/${enc(cid)}/${d}`,
  permissions: (ops: readonly string[]) => `/api/permissions?ops=${ops.map(enc).join(",")}`,
};

/**
 * POST to a map route (D16 writes). Stopgap with the signature of the shell's coming
 * useClient().post<T>(path, body?) (T-010 stage 3): null for 204. Only a 403 whose detail.code is
 * "remote_view" (T-009b) switches the app to read-only; any other 403 (e.g. a viewer refused by
 * D16) is that action's reason and changes no global state. Swap to client.post once it is on main.
 */
async function post<T>(client: Client, path: string, body?: unknown): Promise<T | null> {
  const r = await client.transport.fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 204) return null;
  let detail = `HTTP ${r.status}`;
  let code: string | null = null;
  let parsed: unknown = null;
  try {
    parsed = await r.json();
    const d = (parsed as { detail?: unknown } | null)?.detail;
    if (typeof d === "string") detail = d;
    else if (d && typeof d === "object") {
      const o = d as { code?: unknown; message?: unknown; reason?: unknown };
      code = typeof o.code === "string" ? o.code : null;
      const msg = o.message ?? o.reason;
      if (typeof msg === "string") detail = msg;
    }
  } catch {
    // no body
  }
  if (r.status === 403 && code === "remote_view") client.readOnly.refuse(detail);
  if (!r.ok) throw new CommandRefused(r.status, detail);
  return parsed as T;
}

const opIdOf = (r: { op_id?: string } | null): string => r?.op_id ?? "";

export interface MapRoutes {
  mapState(sampleId: string): Promise<MapState>;
  results(sampleId: string): Promise<ResultSummary[]>;
  result(sampleId: string, resultId: string): Promise<ResultDetail>;
  mosaicUrl(sampleId: string, resultId: string): string;
  flags(sampleId: string, includeRetired: boolean): Promise<Flag[]>;
  candidates(sampleId: string, includeRejected: boolean): Promise<Candidate[]>;
  /** the one permissions call; a failure disables the controls ("Permission check unavailable") */
  permissions(ops: readonly string[]): Promise<Permissions>;
  addFlag(sampleId: string, body: { x_um: number; y_um: number; name: string; note: string; replaces?: string }): Promise<string>;
  retireFlag(sampleId: string, flagId: string): Promise<string>;
  decideCandidate(sampleId: string, candidateId: string, decision: "confirm" | "reject"): Promise<string>;
}

export function mapRoutes(client: Client): MapRoutes {
  return {
    mapState: (id) => client.get<MapState>(PATHS.map(id)),
    results: (id) => client.get<ResultSummary[]>(PATHS.results(id)),
    result: (id, rid) => client.get<ResultDetail>(PATHS.result(id, rid)),
    mosaicUrl: PATHS.mosaic,
    flags: (id, all) => client.get<Flag[]>(PATHS.flags(id, all)),
    candidates: (id, all) => client.get<Candidate[]>(PATHS.candidates(id, all)),
    permissions: (ops) => client.get<Permissions>(PATHS.permissions(ops)),
    addFlag: (id, body) => post<{ op_id?: string }>(client, PATHS.addFlag(id), body).then(opIdOf),
    retireFlag: (id, fid) => post<{ op_id?: string }>(client, PATHS.retireFlag(id, fid), {}).then(opIdOf),
    decideCandidate: (id, cid, d) => post<{ op_id?: string }>(client, PATHS.decide(id, cid, d), {}).then(opIdOf),
  };
}
