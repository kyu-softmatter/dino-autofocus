// Temporary until gen:api, T-009: hand-written types and a fake client for /api/sessions.
// The shapes follow docs/screens/sessions.md section 2. When the server router lands, replace
// the types with the generated ones from src/api/ and the fake with a fetch client; the screen
// only depends on the `SessionsClient` interface below.

import { createContext } from "react";

export type SessionStatus = "open" | "closed";

export interface SessionSummary {
  session_id: string;
  user_id: string;
  user_name: string;
  sample_id: string;
  status: SessionStatus;
  started_at: string;
  closed_at: string | null;
  continues: string | null;
  /** null: no librarian ledger to tell */
  reflected: boolean | null;
}

export interface ManifestEntry {
  name: string;
  where: "session" | "data";
  path: string;
  size: number;
  sha256: string;
  added_at: string;
  kind: string;
}

export interface SessionDetail extends SessionSummary {
  /** as recorded in session.json at open; never recomputed */
  code: { repo: string; commit: string | null; dirty: boolean | null; error: string | null };
  hardware_profile: { path: string; sha256: string } | null;
  sma_run_id: string | null;
  close_note: string;
  log_tail: Array<{ t: string; level: string; msg: string; [k: string]: unknown }>;
  records: Array<{ name: string; lines: number }>;
  manifest: { files: number; bytes: number; by_where: Record<string, number>; entries: ManifestEntry[] };
}

export interface SessionFilter {
  user?: string;
  sample?: string;
  status?: SessionStatus;
}

/** Op names this area asks the shared permission check about (fixed, sessions.md section 2). */
export const SESSION_OPS = ["session_open", "session_close", "session_continue"] as const;
export type SessionOp = (typeof SESSION_OPS)[number];

/**
 * One entry of `GET /api/permissions?ops=a,b` (T-009b over T-011 check(): the single permission
 * table plus engine state). Role, control, experiment-session and remote rules live there only;
 * this screen shows `reason` and never works those rules out itself.
 */
export interface Permission {
  allowed: boolean;
  reason: string | null;
}
export type Permissions = Record<string, Permission>;

/** Shown on every control when /api/permissions cannot be read (rule for all screens). */
export const PERMISSION_UNAVAILABLE = "Permission check unavailable";
/** Shown while the first permission check is loading (same on every screen). */
export const PERMISSION_CHECKING = "Checking permissions…";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly reason: string,
  ) {
    super(reason);
  }
}

export interface SessionsClient {
  list(filter?: SessionFilter): Promise<SessionSummary[]>;
  current(): Promise<SessionSummary | null>;
  detail(id: string): Promise<SessionDetail>;
  /** opens the session for the engine's current sample */
  open(): Promise<SessionDetail>;
  close(id: string, note: string): Promise<SessionDetail>;
  continueFrom(id: string): Promise<SessionDetail>;
  /** the engine's current sample: snapshot()["sample"].sample_id (T-011) */
  currentSample(): Promise<string | null>;
  /** stands in for GET /api/permissions until T-009b lands */
  permissions(ops: readonly string[]): Promise<Permissions>;
}

// -- fake ----------------------------------------------------------------------------------

export interface FakeOptions {
  sessions?: SessionDetail[];
  currentSample?: string | null;
  /** the logged-in user (fake auth, T-105) */
  user?: { user_id: string; role: "admin" | "operator" | "viewer" };
  /** the shared check's answer for every op; default: all allowed */
  permission?: (op: string) => Permission;
  /** make the permission check fail, as when /api/permissions cannot be read */
  permissionsDown?: boolean;
  /** answer only these ops (a missing op counts as unavailable) */
  answerOps?: string[];
  now?: () => string;
}

export const ALLOW_ALL = (): Permission => ({ allowed: true, reason: null });

export function denyAll(reason: string) {
  return (): Permission => ({ allowed: false, reason });
}

export function fakeDetail(p: Partial<SessionDetail> & Pick<SessionDetail, "session_id" | "sample_id">): SessionDetail {
  return {
    user_id: "operator@example.test",
    user_name: "Operator",
    status: "closed",
    started_at: "2026-10-01T09:05:00-07:00",
    closed_at: "2026-10-01T11:40:00-07:00",
    continues: null,
    reflected: null,
    code: { repo: "D:/AutoFocus/dino-autofocus", commit: "0".repeat(40), dirty: false, error: null },
    hardware_profile: null,
    sma_run_id: null,
    close_note: "",
    log_tail: [],
    records: [],
    manifest: { files: 0, bytes: 0, by_where: {}, entries: [] },
    ...p,
  };
}

function summary(d: SessionDetail): SessionSummary {
  const { session_id, user_id, user_name, sample_id, status, started_at, closed_at, continues, reflected } = d;
  return { session_id, user_id, user_name, sample_id, status, started_at, closed_at, continues, reflected };
}

/** In-memory stand-in for the server, following the refusals in sessions.md section 2. */
export function createFakeClient(opts: FakeOptions = {}): SessionsClient {
  const sessions: SessionDetail[] = (opts.sessions ?? []).map((s) => ({ ...s }));
  let sample = opts.currentSample ?? null;
  const user = opts.user ?? { user_id: "operator@example.test", role: "operator" as const };
  const permission = opts.permission ?? ALLOW_ALL;
  const now = opts.now ?? (() => new Date().toISOString());
  let n = 0;

  const find = (id: string) => {
    const s = sessions.find((x) => x.session_id === id);
    if (!s) throw new ApiError(404, `No experiment session ${id}`);
    return s;
  };
  const guard = (op: SessionOp) => {
    const p = permission(op);
    if (!p.allowed) throw new ApiError(403, p.reason ?? "Not allowed");
  };
  const openFor = (sampleId: string, continues: string | null) => {
    const open = sessions.find((x) => x.status === "open");
    if (open) throw new ApiError(409, `${open.session_id} is open; close it first`);
    n += 1;
    const d = fakeDetail({
      session_id: `fake-${n}`,
      sample_id: sampleId,
      user_id: user.user_id,
      status: "open",
      started_at: now(),
      closed_at: null,
      continues,
      log_tail: [{ t: now(), level: "info", msg: "session opened" }],
    });
    sessions.push(d);
    return { ...d };
  };

  return {
    async list(f = {}) {
      return sessions
        .filter((s) => (!f.user || s.user_id === f.user) && (!f.sample || s.sample_id === f.sample))
        .filter((s) => !f.status || s.status === f.status)
        .map(summary);
    },
    async current() {
      const open = sessions.filter((s) => s.status === "open");
      return open.length ? summary(open[open.length - 1]) : null;
    },
    async detail(id) {
      return { ...find(id) };
    },
    async open() {
      guard("session_open");
      if (!sample) throw new ApiError(409, "Open or create a sample first");
      return openFor(sample, null);
    },
    async close(id, note) {
      guard("session_close");
      const s = find(id);
      if (s.status === "closed") throw new ApiError(409, `Session ${id} is closed (read-only)`);
      // area rule, kept in the router: a session belongs to the user who opened it
      if (user.role !== "admin" && s.user_id !== user.user_id) {
        throw new ApiError(403, `Only ${s.user_id} or an admin can close this session`);
      }
      s.status = "closed";
      s.closed_at = now();
      s.close_note = note;
      return { ...s };
    },
    async continueFrom(id) {
      guard("session_continue");
      const prev = find(id);
      sample = prev.sample_id; // the server runs sample_open for it first
      return openFor(prev.sample_id, id);
    },
    async currentSample() {
      return sample;
    },
    async permissions(ops) {
      if (opts.permissionsDown) throw new ApiError(503, "permissions unavailable");
      const asked = opts.answerOps ? ops.filter((op) => opts.answerOps!.includes(op)) : ops;
      return Object.fromEntries(asked.map((op) => [op, permission(op)]));
    },
  };
}

/** The client the screen uses until the router is on main: a fake with no sessions. */
export const defaultClient: SessionsClient = createFakeClient();

/** Tests and, later, the app provide the real client here. */
export const SessionsClientContext = createContext<SessionsClient>(defaultClient);
