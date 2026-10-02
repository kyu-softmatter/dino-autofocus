import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { ScreenContextProvider } from "../../app/screenContext";
import { createFakeApi, type FakeOptions, scriptAfterLoading, scriptToLoading } from "./api";
import { COMPUTED_GRADE, ObjectiveView } from "./ObjectiveView";

function wrap(children: ReactNode) {
  return <ScreenContextProvider area="objective">{children}</ScreenContextProvider>;
}

async function setup(opts: FakeOptions = {}) {
  const api = createFakeApi(opts);
  render(wrap(<ObjectiveView api={api} />));
  await screen.findByTestId("current-label");
  return api;
}

function emitAll(api: ReturnType<typeof createFakeApi>, evs: Parameters<typeof api.emit>[0][]) {
  act(() => {
    for (const ev of evs) api.emit(ev);
  });
}

describe("objective change", () => {
  it("rotates with the +Y step-out and drives the seven steps from events", async () => {
    const api = await setup();
    await screen.findByLabelText("Plan");
    fireEvent.click(screen.getByRole("button", { name: "Rotate" }));
    await waitFor(() => expect(api.sent).toHaveLength(1));
    expect(api.sent[0]).toEqual({ kind: "start", op: "objective_change", args: { target_state: 5, escape: true } });

    emitAll(api, scriptToLoading("op-1"));
    expect(screen.getByTestId("step-1").dataset.status).toBe("done");
    expect(screen.getByTestId("step-2").textContent).toContain("read 0.0");
    expect(screen.getByTestId("step-2").textContent).toContain("PFS Out of Range");
    expect(screen.getByTestId("step-3").textContent).toContain("read 15571.6");
    expect(screen.getByTestId("step-4").textContent).toContain("6-Plan Apo LmbdD0.13 100x Oil");
    expect(screen.getByTestId("step-5").dataset.status).toBe("running");

    const card = screen.getByRole("dialog", { name: "Load immersion" });
    fireEvent.click(within(card).getByRole("button", { name: "Loading done" }));
    await waitFor(() => expect(api.sent).toHaveLength(2));
    expect(api.sent[1]).toEqual({ kind: "confirm", op_id: "op-1", args: { key: "load_immersion", ok: true } });

    emitAll(api, scriptAfterLoading("op-1", 3));
    expect(screen.queryByRole("dialog", { name: "Load immersion" })).toBeNull();
    expect(screen.getByTestId("step-5").textContent).toContain("operator@example.test");
    expect(screen.getByTestId("change-ended").textContent).toBe("Done");
    expect(screen.getByTestId("step-6").dataset.status).toBe("done");
  });

  it("moves the Z approach bar one event at a time, never jumping to the target", async () => {
    const api = await setup();
    emitAll(api, scriptToLoading("op-9", false));
    const after = scriptAfterLoading("op-9", 4, false);
    const bar = () => screen.getByLabelText("Z approach").querySelector("progress") as HTMLProgressElement;
    emitAll(api, after.slice(0, 3)); // confirmed, first progress, first position
    expect(bar().value).toBe(1);
    expect(screen.getByLabelText("Z approach").textContent).toContain("Z 700.00 µm");
    emitAll(api, after.slice(3, 5));
    expect(bar().value).toBe(2);
    expect(screen.getByLabelText("Z approach").textContent).toContain("Z 1400.00 µm");
  });

  it("shows the return action after an interrupted change and sends resume", async () => {
    const api = await setup();
    emitAll(api, scriptToLoading("op-2"));
    emitAll(api, [{ kind: "aborted", op_id: "op-2", data: { state: "awaiting_return", why: "stopped by the operator" } }]);
    expect(screen.getByTestId("step-5").dataset.status).toBe("failed");
    const banner = screen.getByRole("alert", { name: "Awaiting return" });
    expect(screen.getByRole("button", { name: "Rotate" })).toHaveProperty("disabled", true);
    fireEvent.click(within(banner).getByRole("button", { name: "Return to sample position" }));
    await waitFor(() => expect(api.sent.at(-1)).toEqual({ kind: "start", op: "objective_change", args: { resume: true } }));
  });

  it("shows the step-out read-only with its provisional mark, and each lens reason", async () => {
    await setup();
    await screen.findByLabelText("Plan");
    const esc = screen.getByTestId("escape");
    expect(esc.textContent).toContain("Step out +Y 15 mm");
    expect(esc.textContent).toContain("unmeasured provisional");
    expect(within(esc).queryByRole("textbox")).toBeNull(); // never typed
    expect(screen.getByRole("checkbox")).toHaveProperty("checked", true);
    expect(screen.queryByTestId("escape-reason")).toBeNull();
    const wi = screen.getByLabelText(/40x WI/);
    expect(wi).toHaveProperty("disabled", true);
    expect(screen.getByText("no working distance value")).toBeTruthy();
    expect(screen.getByText("already on that objective")).toBeTruthy();
    expect(screen.getAllByText(/unmeasured provisional/)).toHaveLength(2); // step-out and approach step
  });

  it("shows the engine's refusal of the step-out and rotates without it", async () => {
    const api = await setup({ escapeRefusal: "Y step-out exceeds the stage Y limit" });
    await screen.findByLabelText("Plan");
    expect(screen.getByTestId("escape-reason").textContent).toContain("Y step-out exceeds the stage Y limit");
    expect(screen.getByRole("checkbox")).toHaveProperty("disabled", true);
    expect(screen.getByRole("checkbox")).toHaveProperty("checked", false);
    fireEvent.click(screen.getByRole("button", { name: "Rotate" }));
    await waitFor(() => expect(api.sent).toHaveLength(1));
    expect(api.sent[0].args).toEqual({ target_state: 5, escape: false });
  });

  it("is read-only in remote view: no commands, and Loading done is never offered", async () => {
    const api = await setup({ denyAll: "Read-only: remote view", remote: true });
    await screen.findByLabelText("Plan");
    expect(screen.getAllByText("Read-only: remote view").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Rotate" })).toHaveProperty("disabled", true);
    emitAll(api, scriptToLoading("op-3"));
    expect(screen.queryByRole("button", { name: "Loading done" })).toBeNull();
    expect(screen.getByText(/Waiting for the operator at the microscope PC/)).toBeTruthy();
  });

  it("never offers Loading done to a remote client, even one allowed to command", async () => {
    const api = await setup({ remote: true });
    emitAll(api, scriptToLoading("op-4"));
    expect(screen.queryByRole("button", { name: "Loading done" })).toBeNull();
  });
});

describe("100x focus", () => {
  it("shows the centre as not set without a 4x focus plane", async () => {
    await setup({ z4xFocusUm: null });
    const centre = (await screen.findByLabelText("Centre")) as HTMLInputElement;
    expect(centre.value).toBe("");
    expect(centre.placeholder).toBe("not set");
    expect(screen.getByRole("button", { name: "Find 100x focus" })).toHaveProperty("disabled", true);
    expect(screen.getByText("Enter the sweep centre")).toBeTruthy();
  });

  it("fills the centre from the 4x plane, shows the ceiling, and draws the sweep and result", async () => {
    const api = await setup({ z4xFocusUm: 3048.7 });
    const centre = (await screen.findByLabelText("Centre")) as HTMLInputElement;
    expect(Number(centre.value)).toBeCloseTo(2988.7, 6);
    await waitFor(() => expect(screen.getByTestId("ceiling").textContent).toContain("3040.7"));
    fireEvent.click(screen.getByRole("button", { name: "Find 100x focus" }));
    await waitFor(() => expect(api.sent).toHaveLength(1));
    expect(api.sent[0].op).toBe("focus_100x");
    expect(api.sent[0].args?.centre_um).toBeCloseTo(2988.7, 6);

    emitAll(api, [
      { kind: "started", op_id: "op-5", data: { op: "focus_100x" } },
      { kind: "planned", op_id: "op-5", data: { ceiling_um: 3040.7 } },
      { kind: "progress", op_id: "op-5", data: { phase: "coarse", z_readback_um: 2949.0, score: 10, sat: 0 } },
      { kind: "progress", op_id: "op-5", data: { phase: "coarse", z_readback_um: 2989.0, score: 90, sat: 0.01 } },
      { kind: "progress", op_id: "op-5", data: { phase: "coarse", z_readback_um: 3027.0, score: 12, sat: 0 } },
      { kind: "reading", op_id: "op-5", data: { source: "classical", verdict: "in_focus", z_encoder_um: 2989.42,
        warnings: ["reduce exposure"] } },
    ]);
    expect(screen.getByTestId("ceiling-line")).toBeTruthy();
    expect(document.querySelectorAll('circle[data-saturated="true"]')).toHaveLength(1);
    const result = screen.getByTestId("focus-result");
    expect(result.textContent).toContain(COMPUTED_GRADE);
    expect(result.textContent).toContain("Z 2989.42 µm");
    expect(result.textContent).toContain("reduce exposure");
  });

  it("shows the top-end extension only as the engine's confirm", async () => {
    const api = await setup({ z4xFocusUm: 3048.7 });
    await screen.findByLabelText("Centre");
    emitAll(api, [
      { kind: "started", op_id: "op-6", data: { op: "focus_100x" } },
      { kind: "confirm_required", op_id: "op-6", data: { key: "extend_upward", kind: "confirm",
        prompt: "peak at the top end of 2949-3029; extend upward to 3040?", options: ["Extend upward", "Stop"] } },
    ]);
    const box = screen.getByRole("dialog", { name: "Confirm" });
    fireEvent.click(within(box).getByRole("button", { name: "Extend upward" }));
    await waitFor(() => expect(api.sent.at(-1)).toEqual({ kind: "confirm", op_id: "op-6", args: { key: "extend_upward", ok: true } }));
  });
});
