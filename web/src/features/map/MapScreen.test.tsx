import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScreenContextProvider, useCurrentScreenContext } from "../../app/screenContext";
import { fakeMapApi, type EngineEvent, type FakeData, type Permissions } from "./api";
import { fixture, SAMPLE } from "./fixture";
import { MapScreen } from "./index";

let shown: Record<string, unknown> = {};
function ContextProbe() {
  shown = useCurrentScreenContext();
  return null;
}

async function mount(over: Partial<FakeData> = {}) {
  const api = fakeMapApi(fixture(over));
  render(
    <ScreenContextProvider area="map">
      <MapScreen api={api} width={400} height={400} />
      <ContextProbe />
    </ScreenContextProvider>,
  );
  await screen.findByText(`Sample map · ${SAMPLE}`);
  await screen.findByTestId("hole-fit");
  return api;
}

const emit = (api: ReturnType<typeof fakeMapApi>, ev: EngineEvent) => act(() => api.emit(ev));
const deny = (reason: string, ops: string[]): Permissions =>
  Object.fromEntries(ops.map((op) => [op, { allowed: false, reason }]));
const ALL_OPS = [
  "edge_trace", "boundary_mark", "boundary_undo", "boundary_reset", "scan_4x", "sample_map",
  "goto_xy", "map_flag", "map_flag_retire", "candidate_confirm", "candidate_reject",
];
const RECORD_OPS = ["map_flag", "map_flag_retire", "candidate_confirm", "candidate_reject"];

const lastCommand = (api: ReturnType<typeof fakeMapApi>) => api.sent[api.sent.length - 1];

describe("map screen", () => {
  it("shows this session's hole fit and enables the scan step", async () => {
    await mount();
    expect(screen.getByTestId("hole-fit").textContent).toMatch(/^Hole fit \d\d:\d\d \(this session\)$/);
    expect(screen.getByRole("button", { name: "Start scan" })).toHaveProperty("disabled", false);
    expect(screen.getByTestId("map-scale").textContent).toContain("+stage x ←  +y ↓");
  });

  it("warns about a fit from an earlier session and keeps the scan off", async () => {
    const base = fixture().maps[SAMPLE];
    await mount({ maps: { [SAMPLE]: { ...base, session_started_at: (base.hole!.fitted_at ?? 0) + 3600 } } });
    expect(screen.getByTestId("hole-fit").textContent).toMatch(/previous session: re-trace before scanning$/);
    expect(screen.getByRole("button", { name: "Start scan" })).toHaveProperty("disabled", true);
    within(screen.getByRole("region", { name: "Scan" })).getByText("Trace the hole edge in brightfield first");
  });

  it("is read-only from a remote view: map shown, every control off with the shared reason", async () => {
    const api = await mount({ permissions: deny("Read-only: remote view", ALL_OPS) });
    await screen.findByTestId("move-reason");
    expect(screen.getAllByText(/Read-only: remote view/).length).toBeGreaterThan(1);
    for (const name of ["Start tracing", "Start scan", "Confirm", "Retire", "Flag current position"]) {
      for (const b of screen.getAllByRole("button", { name })) expect(b).toHaveProperty("disabled", true);
    }
    fireEvent.click(screen.getByTestId("map-canvas"), { clientX: 200, clientY: 200 });
    expect(api.sent).toEqual([]);
  });

  it("keeps flag and candidate writes off for a viewer (D16) but leaves the map", async () => {
    await mount({ permissions: deny("Needs the operator role on the microscope PC", RECORD_OPS) });
    await within(screen.getByRole("region", { name: "Flags" })).findByText("Needs the operator role on the microscope PC");
    expect(screen.queryByTestId("move-reason")).toBeNull();
    for (const b of screen.getAllByRole("button", { name: "Confirm" })) expect(b).toHaveProperty("disabled", true);
    expect(screen.getByRole("checkbox", { name: "Mosaic" })).toHaveProperty("disabled", false);
  });

  it("lists candidates by source and sends a decision to the map route", async () => {
    const api = await mount();
    const panel = screen.getByRole("region", { name: "Candidates" });
    expect(within(panel).getAllByRole("listitem").map((li) => li.getAttribute("data-source"))).toEqual([
      "classical_candidate",
      "person_confirmed",
    ]);
    fireEvent.click(within(panel).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(lastCommand(api)?.route).toBe(`/api/map/${SAMPLE}/candidates/c1/confirm`));
  });

  it("adds a flag at the current position and edits a note as a new flag", async () => {
    const api = await mount();
    const panel = screen.getByRole("region", { name: "Flags" });
    fireEvent.change(within(panel).getByLabelText("Flag name"), { target: { value: "edge" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Flag current position" }));
    await waitFor(() =>
      expect(lastCommand(api)).toEqual({
        route: `/api/map/${SAMPLE}/flags`,
        body: { x_um: 8026, y_um: 571.6, name: "edge", note: "" },
      }),
    );
    fireEvent.click(within(panel).getByRole("button", { name: "Edit note" }));
    fireEvent.change(within(panel).getByLabelText("New note"), { target: { value: "denser" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Save" }));
    await waitFor(() => expect((lastCommand(api)?.body as { replaces?: string }).replaces).toBe("f1"));
  });

  it("toggles layers and the hidden-by-default records", async () => {
    await mount();
    const mosaic = screen.getByRole("checkbox", { name: "Mosaic" });
    expect(mosaic).toHaveProperty("checked", true);
    fireEvent.click(mosaic);
    expect(mosaic).toHaveProperty("checked", false);
    fireEvent.click(screen.getByRole("checkbox", { name: "Show rejected candidates" }));
    await within(screen.getByRole("region", { name: "Candidates" })).findByText(/rejected/);
  });

  it("starts edge tracing with hole_diameter_mm and sends speed changes as update", async () => {
    const api = await mount();
    const panel = screen.getByRole("region", { name: "Edge trace" });
    fireEvent.click(within(panel).getByRole("button", { name: "Start tracing" }));
    await waitFor(() =>
      expect(lastCommand(api)?.body).toEqual({
        kind: "start",
        op: "edge_trace",
        args: { sample_id: SAMPLE, speed_um_s: 100, hole_diameter_mm: 6.0, light: "bf" },
      }),
    );
    await within(panel).findByRole("button", { name: "Stop" });
    fireEvent.click(within(panel).getByRole("button", { name: "+" }));
    await waitFor(() =>
      expect(lastCommand(api)?.body).toEqual({ kind: "update", op_id: "op-1", args: { speed_um_s: 200 } }),
    );
  });

  it("walks the click-to-move steps from scripted events and never raises Z", async () => {
    const api = await mount();
    fireEvent.click(screen.getByTestId("map-canvas"), { clientX: 180, clientY: 220 });
    await waitFor(() => expect(api.sent.length).toBe(1));
    const sent = api.sent[0].body as { op: string; args: { x_um: number; y_um: number } };
    expect(sent.op).toBe("goto_xy");
    // joystick direction: right of centre is -x, below centre is +y
    const op = "op-1";
    await emit(api, { kind: "planned", op_id: op, data: { distance_um: 900, large_move: true, retract_needed: true, z_safe_um: 0 } });
    await emit(api, { kind: "confirm_required", op_id: op, data: { key: "retract_then_move", z_um: 3048.7, z_safe_um: 0 } });
    const dialog = screen.getByRole("dialog", { name: "Retract Z" });
    expect(dialog.textContent).toContain("Z 3048.70 µm");
    expect(dialog.textContent).toContain("plan Z 0.0 µm");
    fireEvent.click(within(dialog).getByRole("button", { name: "Retract and move" }));
    await waitFor(() =>
      expect(lastCommand(api)?.body).toEqual({ kind: "confirm", op_id: op, args: { key: "retract_then_move", ok: true } }),
    );

    await emit(api, { kind: "progress", op_id: op, data: { step: "retract" } });
    await emit(api, { kind: "position", op_id: "", data: { x_um: 8026, y_um: 571.6, z_um: 0 } });
    expect(screen.getByTestId("click-move").getAttribute("data-phase")).toBe("retracting");
    await emit(api, { kind: "progress", op_id: op, data: { step: "move_xy" } });
    expect(screen.getByTestId("click-move").textContent).toMatch(/^Moving to \(/);
    await emit(api, { kind: "finished", op_id: op, data: { x_um: sent.args.x_um, y_um: sent.args.y_um, z_um: 0, retracted: true } });

    const banner = screen.getByTestId("click-move");
    expect(banner.getAttribute("data-phase")).toBe("arrived");
    expect(banner.textContent).toContain("read back");
    expect(banner.textContent).toContain("Z left retracted at Z 0.00 µm: refocus with a scan tile or focus_100x");
    // only goto_xy and its confirm were sent: the screen does not move Z itself
    expect(api.sent.map((s) => (s.body as { kind: string; op?: string }).op ?? (s.body as { kind: string }).kind)).toEqual([
      "goto_xy",
      "confirm",
    ]);
  });

  it("shows the engine's reason when the click is outside the scan box", async () => {
    const api = await mount();
    fireEvent.click(screen.getByTestId("map-canvas"), { clientX: 0, clientY: 0 });
    await waitFor(() => expect(api.sent.length).toBe(1));
    await emit(api, { kind: "preflight_failed", op_id: "op-1", data: { why: "outside the scan box + 1 mm" } });
    const banner = screen.getByTestId("click-move");
    expect(banner.getAttribute("data-phase")).toBe("refused");
    expect(banner.textContent).toContain("outside the scan box + 1 mm");
  });

  it("puts only short ids into the prompt context, never the mosaic", async () => {
    await mount();
    fireEvent.click(screen.getAllByRole("radio")[0]);
    fireEvent.click(screen.getByRole("button", { name: "good field" }));
    await waitFor(() => expect(shown.flag_id).toBe("f1"));
    expect(shown.sample_id).toBe(SAMPLE);
    expect(JSON.stringify(shown)).not.toMatch(/mosaic|png/i);
  });

  it("re-reads the records on map_changed", async () => {
    const api = await mount();
    api.data.flags[SAMPLE] = [
      ...api.data.flags[SAMPLE],
      { flag_id: "f9", name: "new one", note: "", t: 0, objective: "4x", x_um: 1, y_um: 2, z_um: null, replaces: null, retired_at: null },
    ];
    await emit(api, { kind: "map_changed", op_id: "", data: { sample_id: SAMPLE } });
    await screen.findByRole("button", { name: "new one" });
  });
});
