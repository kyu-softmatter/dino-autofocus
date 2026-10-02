// Temporary until gen:api, T-009: the /api/sessions and /api/permissions shapes are hand-written
// here (docs/screens/sessions.md section 2) because the router is not on main yet. Everything goes
// through the shell's shared client (src/app/client.tsx); this file opens no connection of its own.

import { type Client, CommandRefused } from "../../app/client";

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

export const PATHS = {
  list: (f: SessionFilter = {}) => {
    const q = (["user", "sample", "status"] as const)
      .filter((k) => f[k])
      .map((k) => `${k}=${encodeURIComponent(String(f[k]))}`)
      .join("&");
    return q ? `/api/sessions?${q}` : "/api/sessions";
  },
  current: "/api/sessions/current",
  detail: (id: string) => `/api/sessions/${encodeURIComponent(id)}`,
  open: "/api/sessions",
  close: (id: string) => `/api/sessions/${encodeURIComponent(id)}/close`,
  continueFrom: (id: string) => `/api/sessions/${encodeURIComponent(id)}/continue`,
  /** the engine snapshot; its `sample` block is {sample_id, reserved, session_id} (T-011, G9) */
  state: "/api/state",
  permissions: (ops: readonly string[]) => `/api/permissions?ops=${ops.map(encodeURIComponent).join(",")}`,
};

// -- permissions (one shared check, T-009b over T-011 check()) -----------------------------

/** Op names this area asks the shared permission check about (fixed, sessions.md section 2). */
export const SESSION_OPS = ["session_open", "session_close", "session_continue"] as const;

export interface Permission {
  allowed: boolean;
  reason: string | null;
}
export type Permissions = Record<string, Permission>;

/** Shown on every control when /api/permissions cannot be read (rule for all screens). */
export const PERMISSION_UNAVAILABLE = "Permission check unavailable";
/** Shown while the first permission check is loading (same on every screen). */
export const PERMISSION_CHECKING = "Checking permissions…";
/** Shown when the shell says this browser is a remote viewer (useReadOnly). */
export const READ_ONLY_REMOTE = "Read-only: remote view";

/** The shared answer, or every op refused with PERMISSION_UNAVAILABLE when it cannot be read. */
export async function readPermissions(client: Client, ops: readonly string[]): Promise<Permissions> {
  try {
    return await client.get<Permissions>(PATHS.permissions(ops));
  } catch {
    return Object.fromEntries(ops.map((op) => [op, { allowed: false, reason: PERMISSION_UNAVAILABLE }]));
  }
}

/**
 * Why `op` is off, or null. Order: remote view (shell), still checking, the shared check's reason.
 * An op missing from the answer counts as unavailable. Area rules come after this, in the screen.
 */
export function blockedBy(readOnly: boolean, permissions: Permissions | null, op: string): string | null {
  if (readOnly) return READ_ONLY_REMOTE;
  if (permissions === null) return PERMISSION_CHECKING;
  const p = permissions[op];
  if (!p) return PERMISSION_UNAVAILABLE;
  return p.allowed ? null : p.reason ?? PERMISSION_UNAVAILABLE;
}

// -- router writes ---------------------------------------------------------------------------

/**
 * POST JSON to this area's router through the shared transport, with the signature of the shell's
 * coming `useClient().post<T>(path, body?) -> Promise<T | null>` (T-010 stage 3, null for 204).
 * Swap to `client.post` when that merges. Until then a 403 here stays an area refusal (for example
 * the session owner rule) and does not switch the app to read-only.
 */
export async function postJson<T>(client: Client, path: string, body?: unknown): Promise<T | null> {
  const r = await client.transport.fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try {
      const b = (await r.json()) as { detail?: unknown };
      if (typeof b.detail === "string") detail = b.detail;
    } catch {
      // keep the status text
    }
    throw new CommandRefused(r.status, detail);
  }
  if (r.status === 204) return null;
  return (await r.json()) as T;
}

/** The engine's current sample from the snapshot, or null (T-011 adds the `sample` block). */
export async function readCurrentSample(client: Client): Promise<string | null> {
  const s = await client.get<{ sample?: { sample_id?: string | null } | null }>(PATHS.state);
  return s.sample?.sample_id ?? null;
}
