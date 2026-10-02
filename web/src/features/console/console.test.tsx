import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ScreenContextProvider, useCurrentScreenContext } from "../../app/screenContext";
import { ConsoleApiContext, type FakeData, fakeConsoleApi, READ_ONLY_REASON } from "./api";
import ConsoleScreen, { parseRest } from "./index";
import { changedKeys } from "./questions";
import { PERMISSION_CHECKING, PERMISSION_UNAVAILABLE, submitReason } from "./submit";
import { FAKE_DATA, MOCK_STORE, READ_ONLY_STORE } from "./testData";

function ContextProbe() {
  return <output data-testid="ctx">{JSON.stringify(useCurrentScreenContext())}</output>;
}

function renderConsole(data: FakeData = FAKE_DATA, hash = "#/console") {
  window.location.hash = hash;
  const api = fakeConsoleApi(data);
  render(
    <ConsoleApiContext.Provider value={api}>
      <ScreenContextProvider area="console">
        <ConsoleScreen />
        <ContextProbe />
      </ScreenContextProvider>
    </ConsoleApiContext.Provider>,
  );
  return api;
}

const ctx = () => JSON.parse(screen.getByTestId("ctx").textContent ?? "{}");

beforeEach(() => {
  // the console never reaches the network in tests: everything goes through the fake
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network used in a test"))));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("parseRest", () => {
  it("reads the documented forms and falls back to the question list", () => {
    expect(parseRest("")).toEqual({ tab: "questions" });
    expect(parseRest("questions/sim-20260923-001")).toEqual({ tab: "questions", qid: "sim-20260923-001" });
    expect(parseRest("runs/simulation/run-1")).toEqual({ tab: "runs", agent: "simulation", runId: "run-1" });
    expect(parseRest("runs/nobody/run-1")).toEqual({ tab: "runs" });
    expect(parseRest("inbox")).toEqual({ tab: "inbox" });
    expect(parseRest("whatever")).toEqual({ tab: "questions" });
  });
});

describe("question list", () => {
  it("filters by agent, status and date", async () => {
    renderConsole();
    const list = await screen.findByRole("region", { name: "Questions" });
    expect(within(list).getByText("sim-20260923-001")).toBeTruthy();
    expect(within(list).getByText("mic-20260925-001")).toBeTruthy();

    fireEvent.change(within(list).getByLabelText("Agent"), { target: { value: "simulation" } });
    expect(within(list).queryByText("mic-20260925-001")).toBeNull();
    expect(within(list).getByText("sim-20260923-001")).toBeTruthy();

    fireEvent.change(within(list).getByLabelText("Agent"), { target: { value: "" } });
    fireEvent.change(within(list).getByLabelText("Status"), { target: { value: "VALIDATED" } });
    expect(within(list).queryByText("sim-20260923-001")).toBeNull();
    expect(within(list).getByText("mic-20260925-001")).toBeTruthy();

    fireEvent.change(within(list).getByLabelText("Status"), { target: { value: "" } });
    fireEvent.change(within(list).getByLabelText("Created from"), { target: { value: "2026-09-24" } });
    expect(within(list).queryByText("sim-20260923-001")).toBeNull();
    expect(within(list).getByText("mic-20260925-001")).toBeTruthy();
  });

  it("reads once on open and again only on Refresh", async () => {
    const api = renderConsole();
    await screen.findByRole("region", { name: "Questions" });
    expect(api.calls.filter((c) => c === "listQuestions")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(api.calls.filter((c) => c === "listQuestions")).toHaveLength(2));
  });
});

describe("question detail", () => {
  it("shows card tabs of the latest version and switches between them", async () => {
    renderConsole(FAKE_DATA, "#/console/questions/sim-20260923-001");
    const tabs = await screen.findByRole("tablist", { name: "Cards" });
    const names = within(tabs).getAllByRole("tab").map((t) => t.textContent);
    expect(names).toEqual(["goal", "axis a1", "axis a7"]);
    expect(screen.getByRole("article", { name: "Card v5_goal.json" })).toBeTruthy();

    fireEvent.click(within(tabs).getByRole("tab", { name: "axis a7" }));
    const card = screen.getByRole("article", { name: "Card v5_axis_bd_pairwise_a7.json" });
    expect(within(card).getByText("infeasible")).toBeTruthy();
    await waitFor(() => expect(ctx()).toMatchObject({ area: "console", qid: "sim-20260923-001", version: 5, card_kind: "axis" }));
  });

  it("lists every version the store returns, past v3", async () => {
    const api = renderConsole(FAKE_DATA, "#/console/questions/sim-20260923-001");
    const picker = (await screen.findByLabelText("Version")) as HTMLSelectElement;
    expect([...picker.options].map((o) => o.textContent)).toEqual(["v1", "v2", "v5 (latest)"]);

    fireEvent.change(picker, { target: { value: "1" } });
    expect(await screen.findByRole("article", { name: "Card goal.json" })).toBeTruthy();
    expect(api.calls).toContain("getQuestion sim-20260923-001 1");
    expect(screen.getByRole("tab", { name: "refusal" })).toBeTruthy();
  });

  it("shows grades exactly as the card has them, and the degraded banner", async () => {
    renderConsole(FAKE_DATA, "#/console/questions/sim-20260923-001");
    const table = await screen.findByRole("table", { name: "Numbers" });
    const grades = within(table).getAllByTitle("grade as written on the card").map((g) => g.textContent);
    expect(grades).toEqual(["E2", "E4", "E9"]);
    expect(within(table).getByText("0.09")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("librarian unreachable");
  });

  it("compares two versions by card and field", async () => {
    renderConsole(FAKE_DATA, "#/console/questions/sim-20260923-001");
    fireEvent.change(await screen.findByLabelText("Compare with"), { target: { value: "2" } });
    const diff = await screen.findByRole("table", { name: "Changes v5 to v2" });
    expect(within(diff).getByText("axis_bd_pairwise_a7.json").nextSibling?.textContent).toBe("changed: verdict");
    expect(within(diff).getByText("goal.json").nextSibling?.textContent).toBe("only in v5");
    expect(changedKeys({ a: 1, b: 2 }, { a: 1, b: 3, c: 0 })).toEqual(["b", "c"]);
  });
});

describe("runs and inbox", () => {
  it("links a simulation run to the simulation area", async () => {
    renderConsole(FAKE_DATA, "#/console/runs/simulation/run-20260924-001-smoke-g2k2");
    const link = await screen.findByRole("link", { name: "Open in Simulation" });
    expect(link.getAttribute("href")).toBe("#/simulation/runs/run-20260924-001-smoke-g2k2");
    expect(screen.getByText(/Not opened: trajectory.gsd/)).toBeTruthy();
    expect(within(screen.getByRole("table", { name: "Events" })).getByText("complete")).toBeTruthy();
    await waitFor(() => expect(ctx()).toMatchObject({ run_id: "run-20260924-001-smoke-g2k2", agent: "simulation" }));
  });

  it("shows a microscope run's explanation fields and no simulation link", async () => {
    renderConsole(FAKE_DATA, "#/console/runs/microscope/run-20260924-003");
    expect(await screen.findByText("No plan fits this run.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Open in Simulation" })).toBeNull();
  });

  it("opens a run from the list", async () => {
    renderConsole(FAKE_DATA, "#/console/runs");
    fireEvent.click(await screen.findByRole("button", { name: "run-20260924-003" }));
    expect(await screen.findByRole("region", { name: "Run run-20260924-003" })).toBeTruthy();
    expect(window.location.hash).toBe("#/console/runs/microscope/run-20260924-003");
  });

  it("lists inbox threads with their rounds", async () => {
    renderConsole(FAKE_DATA, "#/console/inbox");
    const inbox = await screen.findByRole("region", { name: "Inbox" });
    expect(within(inbox).getByText("thr-tracer-diffusivity-001")).toBeTruthy();
    expect(within(inbox).getByText("Round two.")).toBeTruthy();
  });
});

describe("ask a question", () => {
  it("is disabled with the read-only reason when the store is not the mock store", async () => {
    const api = renderConsole({ ...FAKE_DATA, store: READ_ONLY_STORE }, "#/console/ask");
    expect(await screen.findByText(READ_ONLY_REASON)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "How fast?" } });
    const button = screen.getByRole("button", { name: "Submit question" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.submit(screen.getByRole("form", { name: "Ask a question" }));
    expect(api.submitted).toHaveLength(0);
    expect(screen.getByText("Store: soft-matter-agents (read-only)")).toBeTruthy();
  });

  it("shows the shared permission reason first (viewer, remote view)", async () => {
    const api = renderConsole(
      {
        ...FAKE_DATA,
        store: READ_ONLY_STORE,
        permissions: { submit_question: { allowed: false, reason: "Needs the operator role" } },
      },
      "#/console/ask",
    );
    expect(await screen.findByText("Needs the operator role")).toBeTruthy();
    expect(screen.queryByText(READ_ONLY_REASON)).toBeNull();
    expect((screen.getByRole("button", { name: "Submit question" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.calls).toContain("permissions submit_question");
  });

  it("orders the reasons: permission, then read-only store", () => {
    const ok = { data: { submit_question: { allowed: true, reason: null } } };
    const remote = { data: { submit_question: { allowed: false, reason: "Read-only: remote view" } } };
    expect(submitReason(ok, { data: MOCK_STORE })).toBeUndefined();
    expect(submitReason(ok, { data: READ_ONLY_STORE })).toBe(READ_ONLY_REASON);
    expect(submitReason(remote, { data: READ_ONLY_STORE })).toBe("Read-only: remote view");
    expect(submitReason({}, { data: MOCK_STORE })).toBe(PERMISSION_CHECKING);
    expect(submitReason({ data: {} }, { data: MOCK_STORE })).toBe(PERMISSION_UNAVAILABLE);
  });

  it("disables submit when the permission check cannot be read, and keeps the reads", async () => {
    window.location.hash = "#/console/ask";
    const api = fakeConsoleApi(FAKE_DATA);
    const broken = { ...api, permissions: () => Promise.reject(new Error("502 Bad Gateway")) };
    render(
      <ConsoleApiContext.Provider value={broken}>
        <ScreenContextProvider area="console">
          <ConsoleScreen />
        </ScreenContextProvider>
      </ConsoleApiContext.Provider>,
    );
    expect(await screen.findByText(PERMISSION_UNAVAILABLE)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "How fast?" } });
    expect((screen.getByRole("button", { name: "Submit question" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole("tab", { name: "Questions" }));
    expect(await screen.findByText("sim-20260923-001")).toBeTruthy();
  });

  it("submits to the mock store and re-reads the list", async () => {
    const api = renderConsole(FAKE_DATA, "#/console/ask");
    await screen.findByText("Store: mock");
    const button = screen.getByRole("button", { name: "Submit question" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true); // no text yet
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "How fast do tracers move?" } });
    fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "simulation" } });
    await act(async () => {
      fireEvent.click(button);
    });
    expect(await screen.findByText("Submitted as sim-20261001-901")).toBeTruthy();
    expect(api.submitted).toEqual([{ text: "How fast do tracers move?", target: "simulation" }]);
    await waitFor(() => expect(api.calls.filter((c) => c === "listQuestions")).toHaveLength(2));

    fireEvent.click(screen.getByRole("tab", { name: "Questions" }));
    expect(await screen.findByText("sim-20261001-901")).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });
});
