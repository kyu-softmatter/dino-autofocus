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

/** What this viewer may do. From the auth dependency (T-105) and the request origin (T-009). */
export interface Access {
  canWrite: boolean;
  /** ui-spec 7.0 string when canWrite is false */
  reason: string | null;
  user_id: string | null;
  role: "admin" | "operator" | "viewer" | null;
}

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
  access(): Promise<Access>;
}

// -- fake ----------------------------------------------------------------------------------

export interface FakeOptions {
  sessions?: SessionDetail[];
  currentSample?: string | null;
  access?: Access;
  now?: () => string;
}

export const LOCAL_OPERATOR: Access = {
  canWrite: true,
  reason: null,
  user_id: "operator@example.test",
  role: "operator",
};

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
  const access = opts.access ?? LOCAL_OPERATOR;
  const now = opts.now ?? (() => new Date().toISOString());
  let n = 0;

  const find = (id: string) => {
    const s = sessions.find((x) => x.session_id === id);
    if (!s) throw new ApiError(404, `No experiment session ${id}`);
    return s;
  };
  const guardWrite = () => {
    if (!access.canWrite) throw new ApiError(403, access.reason ?? "Read-only: remote view");
  };
  const openFor = (sampleId: string, continues: string | null) => {
    const open = sessions.find((x) => x.status === "open");
    if (open) throw new ApiError(409, `${open.session_id} is open; close it first`);
    n += 1;
    const d = fakeDetail({
      session_id: `fake-${n}`,
      sample_id: sampleId,
      user_id: access.user_id ?? "",
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
      guardWrite();
      if (!sample) throw new ApiError(409, "Open or create a sample first");
      return openFor(sample, null);
    },
    async close(id, note) {
      guardWrite();
      const s = find(id);
      if (s.status === "closed") throw new ApiError(409, `Session ${id} is closed (read-only)`);
      if (access.role !== "admin" && s.user_id !== access.user_id) {
        throw new ApiError(403, `Only ${s.user_id} or an admin can close this session`);
      }
      s.status = "closed";
      s.closed_at = now();
      s.close_note = note;
      return { ...s };
    },
    async continueFrom(id) {
      guardWrite();
      const prev = find(id);
      sample = prev.sample_id; // the server runs sample_open for it first
      return openFor(prev.sample_id, id);
    },
    async currentSample() {
      return sample;
    },
    async access() {
      return access;
    },
  };
}

/** The client the screen uses until the router is on main: a fake with no sessions. */
export const defaultClient: SessionsClient = createFakeClient();

/** Tests and, later, the app provide the real client here. */
export const SessionsClientContext = createContext<SessionsClient>(defaultClient);
