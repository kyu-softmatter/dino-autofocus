/**
 * Temporary until gen:api covers the console router (T-009): hand-written types for
 * `/api/console/*` (docs/screens/console.md, the AgentStore records' `to_dict()` shapes) and
 * `/api/permissions` (T-009b), the paths, and the two calls that are not a plain `get`: the
 * one permissions function and the question POST. Reads go through the shell's client
 * (`src/app/client.tsx`). When `src/api/schema.ts` has these paths, swap the types below for
 * imports from it; nothing else changes.
 */

import type { Client } from "../../app/client";

export type Agent = "microscope" | "simulation";
export const AGENTS: readonly Agent[] = ["microscope", "simulation"];

/** goal.schema.json "purpose" (mock_store.PURPOSES) */
export const PURPOSES = ["screen", "characterize", "compare", "verify", "troubleshoot", "feed"] as const;

export interface FileInfo {
  name: string;
  size: number;
}

export interface Card {
  name: string;
  kind: string;
  version: number;
  status: string | null;
  created_at: string | null;
  /** the file's content, untouched */
  data: unknown;
}

export interface DocumentText {
  name: string;
  version: number;
  text: string;
}

export interface QuestionSummary {
  qid: string;
  agent: Agent;
  title: string;
  status: string | null;
  created_at: string | null;
  updated_at: string | null;
  latest_version: number;
  versions: number[];
  source: string;
  /** from the latest goal (T-025); absent until the store sends them */
  purpose?: string | null;
  intent?: string | null;
  observable_name?: string | null;
}

export interface QuestionDetail {
  summary: QuestionSummary;
  version: number;
  goal: Card | null;
  axes: Card[];
  plan: Card | null;
  synthesis: Card | null;
  refusals: Card[];
  results: Card[];
  others: Card[];
  documents: DocumentText[];
  files: FileInfo[];
}

export interface RunSummary {
  run_id: string;
  agent: Agent;
  qid: string | null;
  plan_id: string | null;
  status: string | null;
  created_at: string | null;
  finished_at: string | null;
  backend: string | null;
  source: string;
  /** the log's approval.kind (T-025); absent until the store sends it */
  approval_kind?: string | null;
}

export interface RunDetail {
  summary: RunSummary;
  /** file name -> content, untouched */
  records: Record<string, unknown>;
  files: FileInfo[];
  not_opened: string[];
}

export interface InboxMessage {
  name: string;
  round: number | null;
  kind: string;
  card: unknown;
  text: string | null;
}

export interface InboxThread {
  thread: string;
  agent: Agent | null;
  state: string | null;
  turn: string | null;
  round: number | null;
  updated_at: string | null;
  status: unknown;
  messages: InboxMessage[];
  source: string;
}

/** `GET /api/console/store`: which store is behind the console. Area-specific, so the router serves it. */
export interface StoreInfo {
  /** "mock" or "soft-matter-agents" */
  store: string;
  writable: boolean;
}

/** `GET /api/permissions?ops=...` (T-009b, from T-011 `check()`): why a command would be refused. */
export interface Permission {
  allowed: boolean;
  reason: string | null;
}

export type Permissions = Record<string, Permission>;

export interface SubmitIn {
  text: string;
  target: Agent;
  purpose?: string;
  observable?: string;
}

/** The permission op for asking a question (D16: operator on the microscope PC). */
export const SUBMIT_OP = "submit_question";

/** Shared texts for every screen (screen rules from AF 업무분배보조). */
export const CHECKING_PERMISSIONS = "Checking permissions…";
export const PERMISSION_CHECK_UNAVAILABLE = "Permission check unavailable";
export const READ_ONLY_REMOTE = "Read-only: remote view";
/** ui-spec 7.1: the console's own rule, a store that is not the mock store. */
export const READ_ONLY_STORE_REASON = "Submitting to soft-matter-agents is not connected yet (read-only)";

const seg = encodeURIComponent;

function query(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) q.set(k, String(v));
  const s = q.toString();
  return s === "" ? "" : `?${s}`;
}

export const PATHS = {
  store: "/api/console/store",
  questions: (agent?: Agent) => `/api/console/questions${query({ agent })}`,
  question: (qid: string, version?: number) => `/api/console/questions/${seg(qid)}${query({ version })}`,
  runs: (agent?: Agent) => `/api/console/runs${query({ agent })}`,
  run: (agent: Agent, runId: string) => `/api/console/runs/${seg(agent)}/${seg(runId)}`,
  inbox: "/api/console/inbox",
  permissions: (ops: readonly string[]) => `/api/permissions?ops=${ops.map(seg).join(",")}`,
};

/** The one permissions call. A missing op counts as unavailable (screen rule). */
export async function fetchPermissions(client: Client, ops: readonly string[]): Promise<Permissions> {
  const got = await client.get<Permissions>(PATHS.permissions(ops));
  const out: Permissions = {};
  for (const op of ops) out[op] = got[op] ?? { allowed: false, reason: PERMISSION_CHECK_UNAVAILABLE };
  return out;
}

export class SubmitRefused extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

/**
 * Stand-in for the shell's `useClient().post<T>(path, body?)` (T-010 stage 3, in review), with the
 * same signature: JSON body, `null` for 204, `SubmitRefused` with the server's `detail` otherwise.
 * Replace with `client.post` when stage 3 merges; that one also handles 403 and 401/423.
 */
export async function post<T>(client: Client, path: string, body?: unknown): Promise<T | null> {
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
      // not JSON; keep the status
    }
    throw new SubmitRefused(r.status, detail);
  }
  return r.status === 204 ? null : ((await r.json()) as T);
}

/** `POST /api/console/questions`: the console's one write (mock store only, D16 on the server). */
export async function submitQuestion(client: Client, body: SubmitIn): Promise<QuestionSummary> {
  const q = await post<QuestionSummary>(client, "/api/console/questions", body);
  if (q === null) throw new SubmitRefused(204, "the server returned no question");
  return q;
}
