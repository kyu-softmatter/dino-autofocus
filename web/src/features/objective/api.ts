/**
 * TEMPORARY until gen:api (T-009): hand-written types for the objective area,
 * a fake API client and a scripted event source. The contract is
 * docs/screens/objective.md; when T-009 publishes its OpenAPI, these types come
 * from src/api/ instead and only the real client changes. No network here.
 */

// ---------- engine shapes (engine/events.py) ----------

export type CommandKind = "start" | "abort" | "confirm" | "lights_off";

export interface Command {
  kind: CommandKind;
  op?: string;
  op_id?: string;
  args?: Record<string, unknown>;
}

export interface EngineEvent {
  kind: string;
  op_id: string;
  data: Record<string, unknown>;
  t: number;
}

export interface SendResult {
  ok: boolean;
  op_id?: string;
  /** refusal text, shown as is (403 remote, permission table, busy) */
  refused?: string;
}

// ---------- read endpoints (docs/screens/objective.md section 1) ----------

/** One op's permission from GET /api/permissions?ops=a,b (T-009b, T-011 check()). */
export interface Permission {
  allowed: boolean;
  /** first disabled reason (ui-spec 7.0), shown as is, e.g. "Read-only: remote view" */
  reason: string | null;
}

export type Permissions = Record<string, Permission>;

export interface ObjectiveState {
  nosepiece_state: number;
  label: string;
  pixel_um: number;
  z_um: number | null;
  pfs: { enabled: boolean; locked: boolean; in_range: string };
  immersion_loaded_this_session: { loaded: boolean; immersion: string; at: string; by: string } | null;
  awaiting_return: { since: string; return_xy_um: [number, number]; objective_before: string } | null;
  running: { op_id: string; op: string; step: number; n_steps: number } | null;
  /** this browser is a remote viewer (Loading done is never offered then) */
  remote: boolean;
}

export interface LensRow {
  nosepiece_state: number;
  label: string;
  registry_key: string;
  magnification: number;
  na: number;
  immersion: "dry" | "oil" | "water";
  working_distance_um: number | null;
  selectable: boolean;
  /** engine preflight text, as is */
  disabled_reason: string | null;
}

export interface PlanStep {
  step: number;
  name: string;
  target: string;
}

export interface ObjectivePlan {
  steps: PlanStep[];
  /** Y step-out for loading (PLAN v1.3): read-only from the engine, never typed */
  escape: {
    allowed: boolean;
    /** engine refusal text, shown as is */
    reason: string | null;
    sign: "+Y" | "-Y";
    dy_um: number;
    /** e.g. "unmeasured provisional" */
    mark: string;
    /** engine default for this target (T-029: on for immersion lenses) */
    default: boolean;
  };
  immersion: "dry" | "oil" | "water";
  approach_target_um: number;
  approach_step_um: number;
  /** e.g. "unmeasured provisional" */
  approach_step_mark: string;
  refusal: string | null;
}

export interface Focus100xDefaults {
  z_4x_focus_um: number | null;
  lab_offset_um: number;
  centre_um: number | null;
  half_um: number;
  step_um: number;
  fine_half_um: number;
  fine_step_um: number;
  exposure_ms: number;
  metric: "peak" | "vollath";
  ceiling_um: number | null;
  above_4x_focus: boolean;
  immersion_loaded_this_session: boolean;
}

export interface ObjectiveApi {
  getState(): Promise<ObjectiveState>;
  getLenses(): Promise<LensRow[]>;
  getPlan(targetState: number, escape: boolean): Promise<ObjectivePlan>;
  getFocusDefaults(centreUm?: number): Promise<Focus100xDefaults>;
  /** GET /api/permissions?ops=... : the screen shows these reasons and never computes them */
  getPermissions(ops: string[]): Promise<Permissions>;
  send(cmd: Command): Promise<SendResult>;
  /** /ws/events; returns unsubscribe */
  subscribe(onEvent: (ev: EngineEvent) => void): () => void;
}

// ---------- fake client ----------

export const LAB_OFFSET_UM = -60;
const WD_100X_UM = 130;

export function ceilingFor(centreUm: number): number {
  return Math.min(3200, centreUm + 0.4 * WD_100X_UM);
}

export const FAKE_LENSES: LensRow[] = [
  { nosepiece_state: 0, label: "1-Plan Apo LmbdD20 4x", registry_key: "4x", magnification: 4, na: 0.2,
    immersion: "dry", working_distance_um: 20000, selectable: false, disabled_reason: "already on that objective" },
  { nosepiece_state: 3, label: "4-Plan Apo 40x WI", registry_key: "40x-WI", magnification: 40, na: 1.15,
    immersion: "water", working_distance_um: null, selectable: false, disabled_reason: "no working distance value" },
  { nosepiece_state: 5, label: "6-Plan Apo LmbdD0.13 100x Oil", registry_key: "100x-Oil", magnification: 100,
    na: 1.45, immersion: "oil", working_distance_um: 130, selectable: true, disabled_reason: null },
];

export interface FakeOptions {
  /** every op allowed unless set; denyAll refuses all but abort with that reason */
  denyAll?: string;
  remote?: boolean;
  /** GET /api/permissions fails (network, server error) */
  permissionsFail?: boolean;
  /** GET /api/permissions never answers (the first check stays loading) */
  permissionsPending?: boolean;
  /** ops left out of the permissions answer */
  permissionsOmit?: string[];
  /** engine refusal of the Y step-out (e.g. a stage Y limit); default: allowed */
  escapeRefusal?: string;
  state?: Partial<ObjectiveState>;
  lenses?: LensRow[];
  z4xFocusUm?: number | null;
  /** answer for send(); default: accepted with a new op_id */
  onSend?: (cmd: Command) => SendResult;
}

export interface FakeApi extends ObjectiveApi {
  sent: Command[];
  /** push one engine event to every subscriber */
  emit(ev: Omit<EngineEvent, "t"> & { t?: number }): void;
}

/**
 * TEMPORARY stand-in for GET /api/permissions (T-009b). The only place the fake
 * decides permissions; the screen just shows what it returns.
 */
export function fakePermissions(ops: string[], denyAll?: string): Permissions {
  const out: Permissions = {};
  for (const op of ops) {
    const allowed = denyAll === undefined || op === "abort";
    out[op] = { allowed, reason: allowed ? null : denyAll };
  }
  return out;
}

export function createFakeApi(opts: FakeOptions = {}): FakeApi {
  const listeners = new Set<(ev: EngineEvent) => void>();
  const sent: Command[] = [];
  let n = 0;
  const state: ObjectiveState = {
    nosepiece_state: 0,
    label: "1-Plan Apo LmbdD20 4x",
    pixel_um: 1.625,
    z_um: 3048.7,
    pfs: { enabled: false, locked: false, in_range: "Out of Range" },
    immersion_loaded_this_session: null,
    awaiting_return: null,
    running: null,
    ...opts.state,
    remote: opts.remote ?? false,
  };
  const z4x = opts.z4xFocusUm === undefined ? null : opts.z4xFocusUm;
  return {
    sent,
    async getState() {
      return state;
    },
    async getLenses() {
      return opts.lenses ?? FAKE_LENSES;
    },
    async getPlan(targetState: number, escape: boolean) {
      const lens = (opts.lenses ?? FAKE_LENSES).find((l) => l.nosepiece_state === targetState);
      const steps: PlanStep[] = [
        { step: 1, name: "Record XY, Z, objective; lights off", target: "" },
        { step: 2, name: "PFS off, retract Z", target: "Z -> 0 µm" },
        ...(escape ? [{ step: 3, name: "Step out in Y", target: "Y -> y + 15000 µm" }] : []),
        { step: 4, name: "Rotate", target: lens?.label ?? String(targetState) },
        { step: 5, name: "Load immersion", target: lens?.immersion ?? "" },
        ...(escape ? [{ step: 6, name: "Return XY", target: "XY -> start" }] : []),
        { step: 7, name: "Approach Z", target: "Z -> 2800 µm" },
      ];
      return {
        steps,
        escape: { allowed: opts.escapeRefusal === undefined, reason: opts.escapeRefusal ?? null,
          sign: "+Y", dy_um: 15000, mark: "unmeasured provisional",
          default: (lens?.immersion ?? "dry") !== "dry" },
        immersion: lens?.immersion ?? "dry",
        approach_target_um: 2800,
        approach_step_um: 10,
        approach_step_mark: "unmeasured provisional",
        refusal: lens?.disabled_reason ?? null,
      };
    },
    async getFocusDefaults(centreUm?: number) {
      const centre = centreUm ?? (z4x === null ? null : z4x + LAB_OFFSET_UM);
      return {
        z_4x_focus_um: z4x,
        lab_offset_um: LAB_OFFSET_UM,
        centre_um: centre,
        half_um: 40,
        step_um: 2,
        fine_half_um: 3,
        fine_step_um: 0.2,
        exposure_ms: 20,
        metric: "peak",
        ceiling_um: centre === null ? null : ceilingFor(centre),
        above_4x_focus: centre !== null && z4x !== null && centre > z4x,
        immersion_loaded_this_session: state.immersion_loaded_this_session?.loaded ?? false,
      };
    },
    async getPermissions(ops: string[]) {
      if (opts.permissionsFail) throw new Error("permissions unavailable");
      if (opts.permissionsPending) return new Promise<Permissions>(() => {});
      const omit = opts.permissionsOmit ?? [];
      return fakePermissions(ops.filter((op) => !omit.includes(op)), opts.denyAll);
    },
    async send(cmd: Command) {
      sent.push(cmd);
      if (opts.onSend) return opts.onSend(cmd);
      if (opts.denyAll !== undefined && cmd.kind !== "abort") {
        return { ok: false, refused: opts.denyAll };
      }
      n += 1;
      return { ok: true, op_id: cmd.op_id ?? `op-${n}` };
    },
    subscribe(onEvent) {
      listeners.add(onEvent);
      return () => listeners.delete(onEvent);
    },
    emit(ev) {
      const full: EngineEvent = { t: Date.now() / 1000, ...ev };
      for (const l of [...listeners]) l(full);
    },
  };
}

// ---------- scripted events (a 4x -> 100x Oil change, ops-spec 4.2) ----------

/** The seven steps of objective_change up to the loading card (steps 1-5). */
export function scriptToLoading(opId: string, escape = true): Omit<EngineEvent, "t">[] {
  const stepOut: Omit<EngineEvent, "t">[] = escape
    ? [{ kind: "progress", op_id: opId, data: { step: 3, axis: "y", commanded: 15571.6, readback: 15571.6 } }]
    : [];
  return [
    { kind: "started", op_id: opId, data: { op: "objective_change",
      start_state: { return_xy: [8026.0, 571.6], z_before: 3048.7, objective_before: "1-Plan Apo LmbdD20 4x" } } },
    { kind: "progress", op_id: opId, data: { step: 1, status: "done", detail: "recorded" } },
    { kind: "light_changed", op_id: opId, data: { dialamp: "off", aura: { state: 0 }, verified: true } },
    { kind: "progress", op_id: opId, data: { step: 2, axis: "z", commanded: 0, readback: 0.0, pfs_in_range: "Out of Range" } },
    { kind: "position", op_id: opId, data: { z_um: 0.0, x_um: 8026.0, y_um: 571.6 } },
    ...stepOut,
    { kind: "progress", op_id: opId, data: { step: 4, axis: "nosepiece", commanded: 5,
      label_read: "6-Plan Apo LmbdD0.13 100x Oil" } },
    { kind: "confirm_required", op_id: opId, data: { key: "load_immersion", kind: "manual_step",
      prompt: "Load oil on 6-Plan Apo LmbdD0.13 100x Oil, then press Loading done", options: ["done"],
      context: { immersion: "oil" } } },
  ];
}

/** After "Loading done": step 7 approach in steps, then finished. */
export function scriptAfterLoading(opId: string, nSteps = 3, escape = true): Omit<EngineEvent, "t">[] {
  const evs: Omit<EngineEvent, "t">[] = [
    { kind: "confirmed", op_id: opId, data: { key: "load_immersion", by: "operator@example.test", at: "17:50" } },
  ];
  if (escape) evs.push({ kind: "progress", op_id: opId, data: { step: 6, axis: "xy", commanded: "8026.0, 571.6", readback: "8026.0, 571.6" } });
  for (let i = 1; i <= nSteps; i += 1) {
    const z = (2800 * i) / nSteps;
    evs.push({ kind: "progress", op_id: opId, data: { step: 7, z_um: z, target_um: 2800, step_index: i, n_steps: nSteps } });
    evs.push({ kind: "position", op_id: opId, data: { z_um: z } });
  }
  evs.push({ kind: "finished", op_id: opId, data: { state: "done",
    end_state: { lights: "off" }, summary: { objective: "6-Plan Apo LmbdD0.13 100x Oil" } } });
  return evs;
}

/** Fake engine for the screen when no server exists yet (dev only). */
export const defaultApi: ObjectiveApi = createFakeApi({ z4xFocusUm: 3048.7 });
