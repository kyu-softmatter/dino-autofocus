import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScreenContextProvider, useCurrentScreenContext } from "../../app/screenContext";
import {
  createFakeHardwareApi,
  type FakeHardwareApi,
  type GateRow,
  HardwareApiContext,
  type HardwareProfileOut,
  type Permissions,
  refuseAll,
  SCREEN_OPS,
} from "./api";
import HardwareScreen from "./index";
const PROFILE: HardwareProfileOut = {
  path: "D:/AutoFocus/hardware/hardware_profile.json",
  sha256: "abcdef0123456789",
  profile: {
    detected_at: "2026-10-01T18:00:00",
    backend: "mock",
    previous_sha256: null,
    devices: [
      { label: "Kinetix_red", type: "Camera", present: true, read_back: true, write_verified: null },
      { label: "ZDrive", type: "Stage", present: true, read_back: true, write_verified: null },
      { label: "XYStage", type: "XYStage", present: true, read_back: false, write_verified: null, note: "no read-back" },
    ],
    objectives: [{ label: "1-Plan Apo LmbdD20 4x", state: 0, magnification: 4, working_distance_um: null }],
    camera: { bit_depth: 12 },
    human_confirmed: {},
  },
};

const GATES: GateRow[] = [
  { op: "status", enabled: true, reasons: [], requires: { devices: ["camera"], objectives: [], confirmed: [] } },
  {
    op: "sample_map",
    enabled: false,
    reasons: ["xy_stage detected but its state did not read back"],
    requires: { devices: ["camera", "xy_stage"], objectives: ["4x"], confirmed: [] },
  },
];

function ContextProbe() {
  const ctx = useCurrentScreenContext();
  return <pre data-testid="ctx">{JSON.stringify(ctx)}</pre>;
}

function setup(permissions: Permissions = {}, extra: Partial<FakeHardwareApi["data"]> = {}) {
  const api = createFakeHardwareApi({ profile: PROFILE, gates: GATES, permissions, ...extra });
  render(
    <HardwareApiContext.Provider value={api}>
      <ScreenContextProvider area="hardware">
        <HardwareScreen />
        <ContextProbe />
      </ScreenContextProvider>
    </HardwareApiContext.Provider>,
  );
  return api;
}

/** Disabled directly or by a disabled fieldset. */
const isDisabled = (el: HTMLElement) => el.matches(":disabled");

// Reasons as T-009b / T-011 would give them (D2: remote may abort only; D15: lights need a session)
const remote: Permissions = refuseAll(SCREEN_OPS, "Read-only: remote view");
const viewer: Permissions = {
  ...refuseAll(["hardware_scan", "hardware_confirm", "status", "light_set"], "Needs the operator role"),
  lights_off: { allowed: true, reason: null },
};

describe("hardware screen", () => {
  it("shows off gates first, with their reasons", async () => {
    setup();
    const table = within(await screen.findByRole("region", { name: "Gates" }));
    const rows = table.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("sample_map");
    expect(rows[0].textContent).toContain("Off");
    expect(rows[0].textContent).toContain("xy_stage detected but its state did not read back");
    expect(rows[1].textContent).toContain("status");
  });

  it("sorts problem devices first", async () => {
    setup();
    const table = within(await screen.findByRole("region", { name: "Devices" }));
    await waitFor(() => expect(table.getAllByRole("row")).toHaveLength(4));
    const rows = table.getAllByRole("row").slice(1);
    expect(rows.map((r) => (r as HTMLTableRowElement).cells[0].textContent)).toEqual(["XYStage", "Kinetix_red", "ZDrive"]);
  });

  it("says when nothing has been scanned", async () => {
    setup({}, { profile: { profile: null, path: null, sha256: null } });
    expect(await screen.findByText(/Not scanned yet/)).toBeTruthy();
  });

  it("disables the confirm form for a remote client and a viewer", async () => {
    setup(remote);
    const form = within(await screen.findByRole("region", { name: "Human-confirmed items" }));
    await waitFor(() => expect(isDisabled(form.getByRole("button", { name: "Save" }))).toBe(true));
    expect(form.getByText("Read-only: remote view")).toBeTruthy();
  });

  it("disables operator commands for a viewer but keeps Lights off", async () => {
    const api = setup(viewer);
    await waitFor(() => expect(isDisabled(screen.getByRole("button", { name: "Scan hardware" }))).toBe(true));
    expect(screen.getAllByText("Needs the operator role").length).toBeGreaterThan(0);
    const off = screen.getByRole("button", { name: "Lights off" });
    expect(isDisabled(off)).toBe(false);
    fireEvent.click(off);
    await waitFor(() => expect(api.sent).toEqual([{ kind: "lights_off" }]));
  });

  it("refuses Lights off from a remote client (D2: abort only)", async () => {
    setup(remote);
    await waitFor(() => expect(isDisabled(screen.getByRole("button", { name: "Lights off" }))).toBe(true));
  });

  it("needs an open experiment session for light_set (D15)", async () => {
    setup({ light_set: { allowed: false, reason: "Open an experiment session first" } });
    await waitFor(() => expect(isDisabled(screen.getByRole("button", { name: "Brightfield on" }))).toBe(true));
    expect(isDisabled(screen.getByRole("button", { name: "Scan hardware" }))).toBe(false);
    expect(screen.getByText("Open an experiment session first")).toBeTruthy();
  });

  it("scans with the piezo skipped by default", async () => {
    const api = setup();
    const scan = await screen.findByRole("button", { name: "Scan hardware" });
    await waitFor(() => expect(isDisabled(scan)).toBe(false));
    fireEvent.click(scan);
    await waitFor(() =>
      expect(api.sent).toEqual([
        { kind: "start", op: "hardware_scan", args: { include_properties: true, piezo_port: "" } },
      ]),
    );
  });

  it("shows the light read-back, not the requested value", async () => {
    const api = setup();
    const state = await screen.findByTestId("light-state");
    fireEvent.click(screen.getByRole("button", { name: "Brightfield on" }));
    await waitFor(() => expect(api.sent).toHaveLength(1));
    expect(state.textContent).toContain("no read-back yet");

    act(() =>
      api.emit({
        kind: "light_changed",
        data: {
          dialamp: "unknown",
          aura: { state: "off" },
          verified: false,
          records: [{ device: "DiaLamp", property: "State", wanted: 1, read: 0, verified: false }],
        },
      }),
    );
    expect(state.textContent).toContain("Lights not confirmed: DiaLamp read 0, wanted 1");

    act(() =>
      api.emit({
        kind: "light_changed",
        data: { dialamp: "off", aura: { state: "on", line: "GREEN", intensity_permille: 10 }, verified: true },
      }),
    );
    expect(state.textContent).toContain("DiaLamp OFF · Aura GREEN 1 %");
  });

  it("re-reads permissions when an operation starts and ends, and names it on Lights off", async () => {
    const api = setup();
    const scan = await screen.findByRole("button", { name: "Scan hardware" });
    await waitFor(() => expect(isDisabled(scan)).toBe(false));

    api.data.permissions = { hardware_scan: { allowed: false, reason: "status is running" } };
    act(() => api.emit({ kind: "started", op_id: "op-9", data: { op: "status" } }));
    await waitFor(() => expect(isDisabled(scan)).toBe(true));
    expect(screen.getByText("status is running")).toBeTruthy();
    expect(screen.getByText("stops status")).toBeTruthy();

    api.data.permissions = {};
    act(() =>
      api.emit({ kind: "finished", op_id: "op-9", data: { op: "status", summary: { nosepiece_label: "4x", z_um: 3012.5 } } }),
    );
    await waitFor(() => expect(isDisabled(scan)).toBe(false));
    expect(within(screen.getByRole("region", { name: "Current state" })).getByText("Z 3012.50 µm")).toBeTruthy();
  });

  it("shows this area's gate reason when the permission allows the op", async () => {
    setup({}, {
      gates: [...GATES, {
        op: "hardware_scan", enabled: false, reasons: ["camera not detected"],
        requires: { devices: ["camera"], objectives: [], confirmed: [] },
      }],
    });
    const scan = await screen.findByRole("button", { name: "Scan hardware" });
    await waitFor(() => expect(isDisabled(scan)).toBe(true));
    expect(screen.getByText("hardware_scan is off: camera not detected")).toBeTruthy();
  });

  it("shows a server refusal next to the button", async () => {
    setup({}, { submitResult: { ok: false, status: 403, detail: "Ann has control of the microscope" } });
    const scan = await screen.findByRole("button", { name: "Scan hardware" });
    await waitFor(() => expect(isDisabled(scan)).toBe(false));
    fireEvent.click(scan);
    expect(await screen.findByText("refused: Ann has control of the microscope")).toBeTruthy();
  });

  it("puts the selected gate and its reasons in the screen context", async () => {
    setup();
    const table = within(await screen.findByRole("region", { name: "Gates" }));
    fireEvent.click(table.getByText("sample_map"));
    const ctx = JSON.parse(screen.getByTestId("ctx").textContent ?? "{}");
    expect(ctx).toEqual({
      area: "hardware",
      gate: "sample_map",
      gate_reasons: ["xy_stage detected but its state did not read back"],
    });
  });
});
