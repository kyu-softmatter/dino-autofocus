/** Fixtures for the console tests, shaped like the T-008 mock store's records. */

import type { Card, FakeData, QuestionDetail, QuestionSummary, RunDetail, StoreInfo } from "./api";

export const MOCK_STORE: StoreInfo = { store: "mock", writable: true };
export const READ_ONLY_STORE: StoreInfo = { store: "soft-matter-agents", writable: false };

function summary(over: Partial<QuestionSummary> & Pick<QuestionSummary, "qid" | "agent">): QuestionSummary {
  return {
    title: over.qid, status: "DRAFT", created_at: "2026-09-23T10:00:00Z", updated_at: "2026-09-24T14:40:00Z",
    latest_version: 1, versions: [1], source: "mock", ...over,
  };
}

function card(name: string, kind: string, version: number, data: Record<string, unknown>): Card {
  return { name, kind, version, status: (data.status as string) ?? null, created_at: null, data };
}

function detail(s: QuestionSummary, version: number, cards: Partial<QuestionDetail>): QuestionDetail {
  return {
    summary: s, version, goal: null, axes: [], plan: null, synthesis: null, refusals: [], results: [], others: [],
    documents: [], files: [], ...cards,
  };
}

// versions 1, 2 and 5: the picker must list whatever the store returns
const SIM = summary({
  qid: "sim-20260923-001", agent: "simulation", title: "structural relaxation time", status: "DRAFT",
  latest_version: 5, versions: [1, 2, 5],
});
const MIC = summary({
  qid: "mic-20260925-001", agent: "microscope", title: "tracer diffusivity", status: "VALIDATED",
  created_at: "2026-09-25T09:00:00Z",
});

const NUMBERS = [
  { name: "bead_diameter", value: 5, unit: "um", source: "kb:tracer_diameter_measured", grade: "E2", precision: "significant_figures" },
  { name: "diffusivity", value: 0.09, unit: "um^2/s", source: "computed:stokes_einstein", grade: "E4", precision: "order_of_magnitude" },
  { name: "odd", value: 1, unit: "1", source: "assumed:x", grade: "E9", precision: "exact" },
];

const SIM_V5_GOAL = card("v5_goal.json", "goal", 5, {
  card: "goal", status: "DRAFT", purpose: "characterize", observable: { name: "structural_relaxation_time" },
  numbers: NUMBERS,
  assumptions: [{ statement: "The sweep corners.", authorised_by: "kyuhwan_20260923" }],
  degraded: ["librarian unreachable"],
});

export const FAKE_DATA: FakeData = {
  store: MOCK_STORE,
  permissions: { submit_question: { allowed: true, reason: null } },
  questions: [
    detail(SIM, 1, {
      goal: card("goal.json", "goal", 1, { card: "goal", status: "DRAFT", numbers: NUMBERS.slice(0, 1), degraded: [] }),
      refusals: [card("refusal_s4_sim-20260923-001.json", "refusal", 1, { card: "refusal", stage: "S4", reason_code: "budget" })],
    }),
    detail(SIM, 2, {
      axes: [card("v2_axis_bd_pairwise_a7.json", "axis", 2, { card: "axis", verdict: "feasible" })],
    }),
    detail(SIM, 5, {
      goal: SIM_V5_GOAL,
      axes: [
        card("v5_axis_bd_pairwise_a1.json", "axis", 5, { card: "axis", verdict: "feasible" }),
        card("v5_axis_bd_pairwise_a7.json", "axis", 5, { card: "axis", verdict: "infeasible" }),
      ],
    }),
    detail(MIC, 1, {
      goal: card("goal.json", "goal", 1, { card: "goal", status: "VALIDATED", numbers: [], degraded: [] }),
    }),
  ],
  runs: [
    {
      summary: {
        run_id: "run-20260924-001-smoke-g2k2", agent: "simulation", qid: "sim-20260923-001", plan_id: "plan-x",
        status: "complete", created_at: "2026-09-24T20:00:00Z", finished_at: "2026-09-24T20:10:00Z",
        backend: "hoomd", source: "mock",
      },
      records: {
        "config.json": { seed: 7, parameters_si: { dt: 0.001 } },
        "log.json": { events: [{ t_mono: 0.1, event: "gate", tier: 1 }, { t_mono: 9, event: "complete" }] },
      },
      files: [{ name: "config.json", size: 10 }, { name: "trajectory.gsd", size: 9_000_000 }],
      not_opened: ["trajectory.gsd"],
    } satisfies RunDetail,
    {
      summary: {
        run_id: "run-20260924-003", agent: "microscope", qid: null, plan_id: null, status: null,
        created_at: "2026-09-24T19:06:52Z", finished_at: null, backend: "micromanager", source: "mock",
      },
      records: { "log.json": { no_plan_because: "No plan fits this run.", events: [{ t_wall: "19:07", event: "not_dispatched" }] } },
      files: [{ name: "log.json", size: 10 }],
      not_opened: [],
    },
  ],
  inbox: [
    {
      thread: "thr-tracer-diffusivity-001", agent: "microscope", state: "open", turn: "microscope_agent", round: 2,
      updated_at: "2026-09-22T03:47:24Z", status: { state: "open" }, source: "mock",
      messages: [{ name: "r2_ask_experiment.md", round: 2, kind: "ask_experiment", card: null, text: "Round two." }],
    },
  ],
};
