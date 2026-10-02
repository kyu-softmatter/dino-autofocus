import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScreenContextProvider, useCurrentScreenContext } from "../../app/screenContext";
import { emptyLoading, FakeSampleApi, type Geometry, SampleApiProvider } from "./api";
import SampleScreen from "./index";

const ID = "20261001_0930_1";

function ContextProbe() {
  return <output data-testid="ctx">{JSON.stringify(useCurrentScreenContext())}</output>;
}

function mount(api: FakeSampleApi) {
  window.location.hash = "#/sample"; // as the shell would have it
  render(
    <SampleApiProvider value={api}>
      <ScreenContextProvider area="sample">
        <SampleScreen />
        <ContextProbe />
      </ScreenContextProvider>
    </SampleApiProvider>,
  );
}

function withOpenSample(): FakeSampleApi {
  const api = new FakeSampleApi();
  const geometry: Geometry = {
    values: {
      sample_size_mm: { value: [24, 50], source: { kind: "default", by: null, t: null } },
      chamber_shape: { value: "hole", source: { kind: "default", by: null, t: null } },
      hole_diameter_mm: { value: 6, source: { kind: "entered", by: "kyu", t: "2026-10-01T09:40" } },
      coverslip_thickness_um: { value: 170, source: { kind: "default", by: null, t: null } },
      sample_thickness_um: { value: null, source: { kind: "not_set", by: null, t: null } },
      orientation: { value: "upright", source: { kind: "entered", by: "kyu", t: "2026-10-01T09:41" } },
    },
  };
  api.addSample(ID, {}, geometry, emptyLoading("s-1"));
  api.addSample("20260930_1849_1", { created: "2026-09-30T18:49:00", fitted_at: "2026-09-30T19:10:00" });
  api.currentSample = { sample_id: ID, reserved: false, session_id: "s-1" };
  return api;
}

const geometryPanel = () => screen.getByRole("region", { name: "Geometry" });
const loadingPanel = () => screen.getByRole("region", { name: "Loading check" });

describe("sample screen", () => {
  it("shows the geometry with the source of every value and marks the safety fields", async () => {
    mount(withOpenSample());
    await waitFor(() => expect(screen.getByTestId("source-orientation").textContent).toBe("entered by kyu 2026-10-01T09:41"));
    expect(screen.getByTestId("source-coverslip_thickness_um").textContent).toBe("default");
    expect(screen.getByTestId("source-sample_thickness_um").textContent).toBe("not set");
    const marked = [...geometryPanel().querySelectorAll("tr[data-field]")]
      .filter((tr) => within(tr as HTMLElement).queryByText("safety limit"))
      .map((tr) => tr.getAttribute("data-field"));
    expect(marked).toEqual(["coverslip_thickness_um", "sample_thickness_um", "orientation"]);
  });

  it("renders the field list the server serves, with no field names of its own", async () => {
    const api = withOpenSample();
    api.fieldList = [{ key: "new_field_um", label: "New field", kind: "number", unit: "µm", choices: null, default: null, safety: true }];
    mount(api);
    await waitFor(() => expect(screen.getByLabelText("New field")).toBeTruthy());
    expect(screen.queryByLabelText("Coverslip thickness")).toBeNull();
  });

  it("saves only the changed keys through sample_geometry_set", async () => {
    const api = withOpenSample();
    mount(api);
    const input = await screen.findByLabelText("Sample thickness");
    fireEvent.change(input, { target: { value: "120" } });
    fireEvent.click(screen.getByRole("button", { name: "Save geometry" }));
    await waitFor(() => expect(api.sent).toHaveLength(1));
    expect(api.sent[0]).toEqual({
      kind: "start",
      op: "sample_geometry_set",
      args: { sample_id: ID, values: { sample_thickness_um: 120 } },
    });
  });

  it("does not save a pair with one half empty", async () => {
    const api = withOpenSample();
    mount(api);
    fireEvent.change(await screen.findByLabelText("Sample size (second)"), { target: { value: "" } });
    expect(screen.getByText("Enter both values: Sample size")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Save geometry" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows 'Loading confirmed' only when the engine says so, never from the steps alone", async () => {
    const api = withOpenSample();
    const all = emptyLoading("s-1");
    all.geometry = { done: true, by: "kyu", t: "t1" };
    all.person = { done: true, by: "kyu", t: "t2" };
    all.image = { done: true, ok: true, by: "kyu", t: "t3", why: null, result_ref: "r" };
    api.samples.get(ID)!.loading = { ...all, confirmed: false };
    mount(api);
    await waitFor(() => expect(within(loadingPanel()).getByRole("status").textContent).toBe("Loading not confirmed"));
    expect(screen.queryByText("Loading confirmed (person + image)")).toBeNull();

    api.samples.get(ID)!.loading = { ...all, confirmed: true };
    act(() => api.emit("finished", { op: "loading_check_image", summary: {} }));
    await waitFor(() => expect(screen.getByText("Loading confirmed (person + image)")).toBeTruthy());
  });

  it("lists the missing steps and sends the person and image steps", async () => {
    const api = withOpenSample();
    mount(api);
    await waitFor(() =>
      expect(within(loadingPanel()).getByRole("status").textContent).toBe(
        "Loading not confirmed: missing geometry, person, image",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Sample is on the stage" }));
    fireEvent.click(screen.getByRole("button", { name: "Check with an image" }));
    await waitFor(() => expect(api.sent.map((c) => c.op)).toEqual(["loading_confirm_person", "loading_check_image"]));
    expect(api.sent[1].args).toEqual({ sample_id: ID });
  });

  it("shows the image check failure reason from the engine", async () => {
    const api = withOpenSample();
    api.samples.get(ID)!.loading.image = { done: true, ok: false, by: "kyu", t: "t", why: "no hole edge in the frame", result_ref: null };
    mount(api);
    expect(await screen.findByText("image check failed: no hole edge in the frame")).toBeTruthy();
  });

  it("read-only: every command is off with the server's reason, the folder is a path only", async () => {
    const api = withOpenSample();
    api.accessFor = () => ({ can_open_folder: false, open_reason: null });
    api.permissionFor = () => ({ allowed: false, reason: "Read-only: remote view" });
    mount(api);
    await screen.findByLabelText("Sample thickness");
    await waitFor(() => expect(screen.getAllByText("Read-only: remote view").length).toBeGreaterThan(0));
    for (const name of ["New sample", "Save geometry", "Sample is on the stage", "Check with an image"]) {
      expect((screen.getByRole("button", { name }) as HTMLButtonElement).disabled).toBe(true);
    }
    expect((screen.getByLabelText("Sample thickness") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Open 20260930_1849_1" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Open folder" })).toBeNull();
    expect(screen.getByText(`D:\\AutoFocus\\samples\\${ID}`)).toBeTruthy();
  });

  it("session open for this sample: other samples cannot be opened, with the reason shown", async () => {
    const api = withOpenSample();
    api.accessFor = () => ({ can_open_folder: true, open_reason: `Session s-1 is open for sample ${ID}` });
    mount(api);
    await screen.findByLabelText("Sample thickness");
    expect((screen.getByRole("button", { name: "New sample" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Open 20260930_1849_1" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByText(`Session s-1 is open for sample ${ID}`).length).toBeGreaterThan(0);
    expect((screen.getByRole("button", { name: "Sample is on the stage" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("no session for the sample: geometry and loading steps are off with the reason", async () => {
    const api = withOpenSample();
    api.currentSample = { sample_id: ID, reserved: false, session_id: null };
    api.permissionFor = (op) =>
      op === "sample_open" || op === "sample_new"
        ? { allowed: true, reason: null }
        : { allowed: false, reason: "Open an experiment session first" };
    mount(api);
    await screen.findByLabelText("Sample thickness");
    await waitFor(() => expect(screen.getAllByText("Open an experiment session first")).toHaveLength(3));
    expect((screen.getByRole("button", { name: "New sample" }) as HTMLButtonElement).disabled).toBe(false);
    for (const name of ["Save geometry", "Sample is on the stage", "Check with an image"]) {
      expect((screen.getByRole("button", { name }) as HTMLButtonElement).disabled).toBe(true);
    }
  });

  it("shows a server refusal and an engine preflight_failed next to the control", async () => {
    const api = withOpenSample();
    api.refuse.set("loading_confirm_person", "anna has control of the microscope");
    mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "Sample is on the stage" }));
    expect(await screen.findByText("anna has control of the microscope")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Check with an image" }));
    await waitFor(() => expect(api.sent.at(-1)?.op).toBe("loading_check_image"));
    act(() => api.emit("preflight_failed", { op: "loading_check_image", why: "4x is not in place" }, "op-1"));
    expect(await screen.findByText("4x is not in place")).toBeTruthy();
  });

  it("New sample selects the reserved sample the engine reports", async () => {
    const api = withOpenSample();
    api.currentSample = null;
    mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "New sample" }));
    await waitFor(() => expect(api.sent.at(-1)?.op).toBe("sample_new"));
    api.addSample("20261001_1200_1", { created: "2026-10-01T12:00:00", reserved: true });
    act(() => api.emit("finished", { op: "sample_new", summary: { sample_id: "20261001_1200_1" } }, "op-1"));
    await waitFor(() => expect(window.location.hash).toBe("#/sample?sample_id=20261001_1200_1"));
    expect(await screen.findByText("reserved, no session yet")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Opened sample" }).textContent).toContain("20261001_1200_1");
  });

  it("Open folder calls the server route and never opens anything itself", async () => {
    const api = withOpenSample();
    mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "Open folder" }));
    await waitFor(() => expect(api.opened).toEqual([ID]));
    expect(api.sent).toHaveLength(0);
  });

  it("opening another sample sends sample_open", async () => {
    const api = withOpenSample();
    mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "Open 20260930_1849_1" }));
    await waitFor(() => expect(api.sent.at(-1)).toEqual({ kind: "start", op: "sample_open", args: { sample_id: "20260930_1849_1" } }));
  });

  it("puts the sample id, geometry sources and loading state in the prompt context, no images", async () => {
    mount(withOpenSample());
    await waitFor(() => expect(JSON.parse(screen.getByTestId("ctx").textContent ?? "{}").sample_id).toBe(ID));
    const ctx = JSON.parse(screen.getByTestId("ctx").textContent ?? "{}");
    expect(ctx.area).toBe("sample");
    expect(ctx.geometry.orientation).toEqual({ value: "upright", source: "entered" });
    expect(ctx.loading).toEqual({ geometry: false, person: false, image: false, confirmed: false });
  });
});
