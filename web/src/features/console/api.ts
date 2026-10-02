/**
 * Console API: wire types, the HTTP client and a fake for tests.
 *
 * TEMPORARY until gen:api (T-009): the types below are hand copies of the AgentStore records
 * (`agents/store.py`, `to_dict()` shapes) and of the routes in `docs/screens/console.md`.
 * When the console router is on main and `src/api/` is generated, replace the types in this
 * file with re-exports from `src/api/` and keep the client; nothing else in the area changes.
 * The shared permission check (`GET /api/permissions`, T-009b) is faked behind `permissions()`.
 */

import { createContext, useContext } from "react";

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

/** One answer of the shared `GET /api/permissions?ops=` (T-009b): reasons in ui-spec 7.0 wording. */
export interface Permission {
  allowed: boolean;
  reason: string | null;
}

/** The permission op for asking a question (D16: operator on the microscope PC). */
export const SUBMIT_OP = "submit_question";

export const READ_ONLY_REASON = "Submitting to soft-matter-agents is not connected yet (read-only)";

export interface SubmitIn {
  text: string;
  target: Agent;
  purpose?: string;
  observable?: string;
}

export interface ConsoleApi {
  storeInfo(): Promise<StoreInfo>;
  /** the shared permission check; the screen shows its reasons and decides nothing */
  permissions(ops: string[]): Promise<Record<string, Permission>>;
  /** both agents, newest first, when `agent` is omitted */
  listQuestions(agent?: Agent): Promise<QuestionSummary[]>;
  /** the latest version unless `version` is given */
  getQuestion(qid: string, version?: number): Promise<QuestionDetail>;
  listRuns(agent?: Agent): Promise<RunSummary[]>;
  getRun(agent: Agent, runId: string): Promise<RunDetail>;
  listInbox(): Promise<InboxThread[]>;
  submitQuestion(body: SubmitIn): Promise<QuestionSummary>;
}

export class ConsoleApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ConsoleApiError";
    this.status = status;
  }
}

// --- HTTP client ------------------------------------------------------------------------------

const BASE = "/api/console";

function query(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) q.set(k, String(v));
  const s = q.toString();
  return s === "" ? "" : `?${s}`;
}

async function call<T>(path: string, init?: RequestInit, base = BASE): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init?.body !== undefined) headers["Content-Type"] = "application/json";
  const r = await fetch(base + path, { credentials: "same-origin", ...init, headers });
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const body: unknown = await r.json();
      if (typeof body === "object" && body !== null && typeof (body as { detail?: unknown }).detail === "string") {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      // not JSON; keep the status line
    }
    throw new ConsoleApiError(r.status, detail);
  }
  return (await r.json()) as T;
}

const seg = encodeURIComponent;

export const httpConsoleApi: ConsoleApi = {
  storeInfo: () => call("/store"),
  permissions: (ops) => call(`/permissions${query({ ops: ops.join(",") })}`, undefined, "/api"),
  listQuestions: (agent) => call(`/questions${query({ agent })}`),
  getQuestion: (qid, version) => call(`/questions/${seg(qid)}${query({ version })}`),
  listRuns: (agent) => call(`/runs${query({ agent })}`),
  getRun: (agent, runId) => call(`/runs/${seg(agent)}/${seg(runId)}`),
  listInbox: () => call("/inbox"),
  submitQuestion: (body) => call("/questions", { method: "POST", body: JSON.stringify(body) }),
};

export const ConsoleApiContext = createContext<ConsoleApi>(httpConsoleApi);

export function useConsoleApi(): ConsoleApi {
  return useContext(ConsoleApiContext);
}

// --- fake, for tests (no network) ---------------------------------------------------------------

export interface FakeData {
  store: StoreInfo;
  /** answers of the shared permission check; an op left out is allowed */
  permissions: Record<string, Permission>;
  /** every version of every question, one QuestionDetail each */
  questions: QuestionDetail[];
  runs: RunDetail[];
  inbox: InboxThread[];
}

export interface FakeConsoleApi extends ConsoleApi {
  calls: string[];
  submitted: SubmitIn[];
}

export function fakeConsoleApi(data: FakeData): FakeConsoleApi {
  const questions = [...data.questions];
  const calls: string[] = [];
  const submitted: SubmitIn[] = [];
  const newestFirst = <T>(xs: T[], key: (x: T) => string) =>
    [...xs].sort((a, b) => (key(a) < key(b) ? 1 : key(a) > key(b) ? -1 : 0));
  const latest = (qid: string) => {
    const vs = questions.filter((d) => d.summary.qid === qid);
    return vs.find((d) => d.version === vs[0].summary.latest_version) ?? vs[0];
  };
  const notFound = (what: string) => Promise.reject(new ConsoleApiError(404, `no ${what}`));

  return {
    calls,
    submitted,
    storeInfo: async () => {
      calls.push("storeInfo");
      return data.store;
    },
    permissions: async (ops) => {
      calls.push(`permissions ${ops.join(",")}`);
      return Object.fromEntries(ops.map((op) => [op, data.permissions[op] ?? { allowed: true, reason: null }]));
    },
    listQuestions: async (agent) => {
      calls.push(`listQuestions ${agent ?? ""}`.trim());
      const qids = [...new Set(questions.map((d) => d.summary.qid))];
      const out = qids.map((q) => latest(q).summary).filter((s) => agent === undefined || s.agent === agent);
      return newestFirst(out, (s) => s.qid);
    },
    getQuestion: async (qid, version) => {
      calls.push(`getQuestion ${qid} ${version ?? ""}`.trim());
      if (!questions.some((d) => d.summary.qid === qid)) return notFound(`question ${qid}`);
      const d = version === undefined ? latest(qid) : questions.find((x) => x.summary.qid === qid && x.version === version);
      return d ?? notFound(`version ${version} of ${qid}`);
    },
    listRuns: async (agent) => {
      calls.push(`listRuns ${agent ?? ""}`.trim());
      const out = data.runs.map((r) => r.summary).filter((s) => agent === undefined || s.agent === agent);
      return newestFirst(out, (s) => s.created_at ?? "");
    },
    getRun: async (agent, runId) => {
      calls.push(`getRun ${agent} ${runId}`);
      const r = data.runs.find((x) => x.summary.agent === agent && x.summary.run_id === runId);
      return r ?? notFound(`run ${runId}`);
    },
    listInbox: async () => {
      calls.push("listInbox");
      return data.inbox;
    },
    submitQuestion: async (body) => {
      calls.push(`submitQuestion ${body.target}`);
      // the server's order: permission (403), then a read-only store (409)
      const perm = data.permissions[SUBMIT_OP];
      if (perm !== undefined && !perm.allowed) throw new ConsoleApiError(403, perm.reason ?? "refused");
      if (!data.store.writable) throw new ConsoleApiError(409, READ_ONLY_REASON);
      submitted.push(body);
      const prefix = body.target === "microscope" ? "mic" : "sim";
      const qid = `${prefix}-20261001-${String(900 + submitted.length).padStart(3, "0")}`;
      const card: Card = {
        name: "goal.json", kind: "goal", version: 1, status: "DRAFT", created_at: "2026-10-01T00:00:00Z",
        data: { card: "goal", qid, status: "DRAFT", question: body.text, origin: "dino-autofocus mock" },
      };
      const summary: QuestionSummary = {
        qid, agent: body.target, title: body.text, status: "DRAFT", created_at: card.created_at,
        updated_at: card.created_at, latest_version: 1, versions: [1], source: "mock-submitted",
      };
      questions.push({
        summary, version: 1, goal: card, axes: [], plan: null, synthesis: null, refusals: [], results: [],
        others: [], documents: [], files: [],
      });
      return summary;
    },
  };
}
