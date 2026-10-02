import { useCallback, useEffect, useMemo, useReducer, useState } from "react";

import { EncoderZ, isVerdict, type Verdict } from "../../app/Verdict";
import { useScreenContext } from "../../app/screenContext";
import type {
  Command,
  EngineEvent,
  Focus100xDefaults,
  LensRow,
  ObjectiveApi,
  Permission,
  Permissions,
  ObjectivePlan,
  ObjectiveState,
} from "./api";
import {
  type ChangeView,
  type FocusView,
  initialChange,
  initialFocus,
  type PendingConfirm,
  reduceChange,
  reduceFocus,
} from "./model";
import "./objective.css";

/**
 * The objective area (docs/screens/objective.md, ui-spec 7.5): objective change
 * with immersion loading, and the 100x focus sweep. All state comes from the
 * read endpoints and engine events; the screen never decides a motion limit.
 */
export function ObjectiveView({ api }: { api: ObjectiveApi }) {
  const [state, setState] = useState<ObjectiveState | null>(null);
  const [lenses, setLenses] = useState<LensRow[]>([]);
  const [change, dispatchChange] = useReducer(reduceChange, undefined, initialChange);
  const [focus, dispatchFocus] = useReducer(reduceFocus, undefined, initialFocus);
  const [message, setMessage] = useState<string | null>(null);
  const [perms, setPerms] = useState<Permissions>({});
  const [permsTick, setPermsTick] = useState(0);

  useEffect(() => {
    let live = true;
    void api.getState().then((s) => live && setState(s));
    void api.getLenses().then((l) => live && setLenses(l));
    const off = api.subscribe((ev: EngineEvent) => {
      dispatchChange(ev);
      dispatchFocus(ev);
      // engine state changed: permissions (busy, awaiting return) may have changed too
      if (["started", "finished", "aborted", "error"].includes(ev.kind)) setPermsTick((n) => n + 1);
    });
    return () => {
      live = false;
      off();
    };
  }, [api]);

  useEffect(() => {
    let live = true;
    void api.getPermissions(PERMISSION_OPS).then((p) => live && setPerms(p));
    return () => {
      live = false;
    };
  }, [api, permsTick]);

  const send = useCallback(
    async (cmd: Command) => {
      const r = await api.send(cmd);
      setMessage(r.ok ? null : (r.refused ?? "refused"));
      return r;
    },
    [api],
  );

  const details = useMemo(
    () => ({
      objective: state?.label,
      op_id: change.opId ?? focus.opId ?? undefined,
      step: currentStep(change),
    }),
    [state?.label, change, focus.opId],
  );
  useScreenContext(details);

  if (state === null) return <p className="muted">Loading objective…</p>;
  const perm = (op: string): Permission => perms[op] ?? { allowed: false, reason: "checking permissions" };
  const changePerm = perm("objective_change");
  const awaiting = state.awaiting_return !== null || change.ended?.state === "awaiting_return";

  return (
    <div className="objective">
      {!changePerm.allowed && changePerm.reason && (
        <p className="readonly" role="status">
          {changePerm.reason}
        </p>
      )}
      {message && (
        <p className="refusal" role="alert">
          {message}
        </p>
      )}
      <CurrentPanel state={state} zUm={change.zUm ?? state.z_um} />
      {awaiting && <ReturnBanner perm={changePerm} onReturn={() => send(startChange({ resume: true }))} />}
      <ChangePanel api={api} lenses={lenses} perm={changePerm} disabledBy={awaiting ? "Return to the sample position first" : null}
                   onRotate={(target) => send(startChange({ target_state: target, escape: false }))}
                   onReload={() => send(startChange({ reload: true }))} />
      <StepsPanel view={change} confirmPerm={perm("confirm")} remote={state.remote}
                  onLoadingDone={(c) => send({ kind: "confirm", op_id: c.opId, args: { key: c.key, ok: true } })}
                  onAnswer={(c, ok) => send({ kind: "confirm", op_id: c.opId, args: { key: c.key, ok } })}
                  onAbort={(opId) => send({ kind: "abort", op_id: opId })} />
      <Focus100xPanel api={api} perm={perm("focus_100x")} confirmPerm={perm("confirm")} view={focus} disabledBy={awaiting ? "Return to the sample position first" : null}
                      onStart={(args) => send({ kind: "start", op: "focus_100x", args })}
                      onAnswer={(c, ok) => send({ kind: "confirm", op_id: c.opId, args: { key: c.key, ok } })} />
    </div>
  );
}

/** ops whose permission the screen asks for (GET /api/permissions) */
const PERMISSION_OPS = ["objective_change", "focus_100x", "confirm", "abort"];

function startChange(args: Record<string, unknown>): Command {
  return { kind: "start", op: "objective_change", args };
}

function currentStep(v: ChangeView): number | undefined {
  for (const s of [7, 6, 5, 4, 3, 2, 1]) if (v.steps[s].status === "running") return s;
  return undefined;
}

function CurrentPanel({ state, zUm }: { state: ObjectiveState; zUm: number | null }) {
  return (
    <section aria-label="Current objective">
      <h3>Current</h3>
      <p>
        <strong data-testid="current-label">{state.label}</strong> · {state.pixel_um} µm/px ·{" "}
        <EncoderZ readbackUm={zUm} /> · PFS {state.pfs.enabled ? "on" : "off"}, {state.pfs.in_range}
      </p>
    </section>
  );
}

function ReturnBanner({ perm, onReturn }: { perm: Permission; onReturn: () => void }) {
  return (
    <section className="banner" role="alert" aria-label="Awaiting return">
      <p>Objective change interrupted: return to the sample position.</p>
      <button type="button" disabled={!perm.allowed} onClick={onReturn}>
        Return to sample position
      </button>
      {!perm.allowed && perm.reason && <span className="reason"> {perm.reason}</span>}
    </section>
  );
}

function ChangePanel({
  api,
  lenses,
  perm,
  disabledBy,
  onRotate,
  onReload,
}: {
  api: ObjectiveApi;
  lenses: LensRow[];
  perm: Permission;
  disabledBy: string | null;
  onRotate: (target: number) => void;
  onReload: () => void;
}) {
  const [target, setTarget] = useState<number | null>(null);
  const [plan, setPlan] = useState<ObjectivePlan | null>(null);
  const firstSelectable = lenses.find((l) => l.selectable)?.nosepiece_state ?? null;
  const chosen = target ?? firstSelectable;

  useEffect(() => {
    if (chosen === null) return;
    let live = true;
    void api.getPlan(chosen, false).then((p) => live && setPlan(p));
    return () => {
      live = false;
    };
  }, [api, chosen]);

  const blocked = !perm.allowed ? (perm.reason ?? "not allowed") : disabledBy ?? plan?.refusal ?? null;
  return (
    <section aria-label="Change objective">
      <h3>Change objective</h3>
      <ul className="lenses">
        {lenses.map((l) => (
          <li key={l.nosepiece_state}>
            <label>
              <input type="radio" name="lens" value={l.nosepiece_state} disabled={!l.selectable}
                     checked={chosen === l.nosepiece_state} onChange={() => setTarget(l.nosepiece_state)} />
              {l.label} ({l.immersion}, WD {l.working_distance_um === null ? "not set" : `${l.working_distance_um} µm`})
            </label>
            {l.disabled_reason && <span className="reason"> {l.disabled_reason}</span>}
          </li>
        ))}
      </ul>
      <p>
        <label>
          <input type="checkbox" checked={false} disabled readOnly /> Step out in Y for loading
        </label>
        <span className="reason" data-testid="escape-reason"> {plan?.escape.reason ?? "escape distance not set"}</span>
      </p>
      {plan && (
        <>
          <ol className="plan" aria-label="Plan">
            {plan.steps.map((s) => (
              <li key={s.step} value={s.step}>
                {s.name}
                {s.target && ` · ${s.target}`}
              </li>
            ))}
          </ol>
          <p className="muted">
            Approach Z to {plan.approach_target_um} µm in steps of {plan.approach_step_um} µm ({plan.approach_step_mark})
          </p>
        </>
      )}
      <button type="button" disabled={chosen === null || blocked !== null} onClick={() => chosen !== null && onRotate(chosen)}>
        Rotate
      </button>{" "}
      <button type="button" disabled={!perm.allowed || disabledBy !== null} onClick={onReload}>
        Re-load immersion
      </button>
      {blocked && <span className="reason"> {blocked}</span>}
    </section>
  );
}

const STEP_NAMES: Record<number, string> = {
  1: "Record position and objective; lights off",
  2: "PFS off, retract Z",
  3: "Step out in Y",
  4: "Rotate",
  5: "Load immersion",
  6: "Return XY",
  7: "Approach Z",
};

function StepsPanel({
  view,
  confirmPerm,
  remote,
  onLoadingDone,
  onAnswer,
  onAbort,
}: {
  view: ChangeView;
  confirmPerm: Permission;
  remote: boolean;
  onLoadingDone: (c: PendingConfirm) => void;
  onAnswer: (c: PendingConfirm, ok: boolean) => void;
  onAbort: (opId: string) => void;
}) {
  if (view.opId === null) return null;
  // "Loading done" is pressed by the person at the microscope: never remotely (ui-spec 7.5)
  const canLoad = confirmPerm.allowed && !remote;
  return (
    <section aria-label="Progress">
      <h3>Progress</h3>
      <ol className="steps">
        {[1, 2, 3, 4, 5, 6, 7].map((s) => (
          <li key={s} value={s} data-testid={`step-${s}`} data-status={view.steps[s].status}>
            {STEP_NAMES[s]} <span className="status">{view.steps[s].status}</span>{" "}
            <span className="detail">{view.steps[s].detail}</span>
          </li>
        ))}
      </ol>
      {view.loading && (
        <div className="loading-card" role="dialog" aria-label="Load immersion">
          <p>{view.loading.prompt}</p>
          {canLoad ? (
            <button type="button" className="big" onClick={() => onLoadingDone(view.loading as PendingConfirm)}>
              Loading done
            </button>
          ) : (
            <p className="muted">Waiting for the operator at the microscope PC: {view.loading.prompt}</p>
          )}
        </div>
      )}
      {view.confirm && <ConfirmBox confirm={view.confirm} perm={confirmPerm} onAnswer={onAnswer} />}
      {view.approach && (
        <div aria-label="Z approach">
          <progress max={view.approach.nSteps} value={view.approach.index} />{" "}
          <EncoderZ readbackUm={view.zUm} /> → target {view.approach.targetUm} µm (step {view.approach.index} of{" "}
          {view.approach.nSteps})
        </div>
      )}
      {view.ended ? (
        <p data-testid="change-ended">
          {view.ended.state === "done" ? "Done" : `Stopped (${view.ended.state})`}
          {view.ended.why && `: ${view.ended.why}`}
        </p>
      ) : (
        <button type="button" onClick={() => onAbort(view.opId as string)}>
          Abort
        </button>
      )}
    </section>
  );
}

function ConfirmBox({
  confirm,
  perm,
  onAnswer,
}: {
  confirm: PendingConfirm;
  perm: Permission;
  onAnswer: (c: PendingConfirm, ok: boolean) => void;
}) {
  if (!perm.allowed) {
    return <p className="muted">Waiting for the operator at the microscope PC: {confirm.prompt}</p>;
  }
  return (
    <div className="confirm" role="dialog" aria-label="Confirm">
      <p>{confirm.prompt}</p>
      <button type="button" onClick={() => onAnswer(confirm, true)}>
        {confirm.options[0] ?? "Yes"}
      </button>{" "}
      <button type="button" onClick={() => onAnswer(confirm, false)}>
        {confirm.options[1] ?? "Cancel"}
      </button>
    </div>
  );
}

// ---------- 100x focus ----------

type FocusForm = {
  centre_um: string;
  half_um: number;
  step_um: number;
  fine_half_um: number;
  fine_step_um: number;
  exposure_ms: number;
  metric: "peak" | "vollath";
};

function Focus100xPanel({
  api,
  perm,
  confirmPerm,
  view,
  disabledBy,
  onStart,
  onAnswer,
}: {
  api: ObjectiveApi;
  perm: Permission;
  confirmPerm: Permission;
  view: FocusView;
  disabledBy: string | null;
  onStart: (args: Record<string, unknown>) => void;
  onAnswer: (c: PendingConfirm, ok: boolean) => void;
}) {
  const [defaults, setDefaults] = useState<Focus100xDefaults | null>(null);
  const [form, setForm] = useState<FocusForm | null>(null);

  useEffect(() => {
    let live = true;
    void api.getFocusDefaults().then((d) => {
      if (!live) return;
      setDefaults(d);
      setForm({ centre_um: d.centre_um === null ? "" : String(d.centre_um), half_um: d.half_um, step_um: d.step_um,
        fine_half_um: d.fine_half_um, fine_step_um: d.fine_step_um, exposure_ms: d.exposure_ms, metric: d.metric });
    });
    return () => {
      live = false;
    };
  }, [api]);

  const centre = form && form.centre_um.trim() !== "" ? Number(form.centre_um) : null;
  useEffect(() => {
    if (centre === null || !Number.isFinite(centre)) return;
    let live = true;
    void api.getFocusDefaults(centre).then((d) => live && setDefaults(d));
    return () => {
      live = false;
    };
  }, [api, centre]);

  if (defaults === null || form === null) return null;
  const centreOk = centre !== null && Number.isFinite(centre);
  const blocked = !perm.allowed ? (perm.reason ?? "not allowed") : disabledBy ?? (centreOk ? null : "Enter the sweep centre");
  return (
    <section aria-label="100x focus">
      <h3>100x focus</h3>
      <table className="refs">
        <tbody>
          <tr>
            <th>4x focus here</th>
            <td>{defaults.z_4x_focus_um === null ? "not set" : `${defaults.z_4x_focus_um} µm`}</td>
          </tr>
          <tr>
            <th>Lab offset</th>
            <td>{defaults.lab_offset_um} µm (lab offset, to be re-measured)</td>
          </tr>
          <tr>
            <th>Ceiling</th>
            <td data-testid="ceiling">{defaults.ceiling_um === null ? "—" : `${defaults.ceiling_um} µm`}</td>
          </tr>
          <tr>
            <th>Immersion this session</th>
            <td>{defaults.immersion_loaded_this_session ? "loaded" : "no loading recorded"}</td>
          </tr>
        </tbody>
      </table>
      <p>
        <label>
          Centre (µm){" "}
          <input aria-label="Centre" value={form.centre_um} placeholder="not set" disabled={!perm.allowed}
                 onChange={(e) => setForm({ ...form, centre_um: e.target.value })} />
        </label>{" "}
        {defaults.above_4x_focus && centreOk && (
          <span className="reason">above the 4x focus; 100x focus is usually 60-100 µm below</span>
        )}
      </p>
      <p className="muted">
        half {form.half_um} µm · step {form.step_um} µm · fine ±{form.fine_half_um} µm at {form.fine_step_um} µm ·{" "}
        {form.exposure_ms} ms · metric {form.metric}
      </p>
      <button type="button" disabled={blocked !== null}
              onClick={() => onStart({ centre_um: centre, half_um: form.half_um, step_um: form.step_um,
                fine_half_um: form.fine_half_um, fine_step_um: form.fine_step_um, exposure_ms: form.exposure_ms,
                metric: form.metric })}>
        Find 100x focus
      </button>
      {blocked && <span className="reason"> {blocked}</span>}
      {view.confirm && <ConfirmBox confirm={view.confirm} perm={confirmPerm} onAnswer={onAnswer} />}
      {view.points.length > 0 && <SweepCurve view={view} ceilingUm={view.ceilingUm ?? defaults.ceiling_um} />}
      {view.result && (
        <p data-testid="focus-result">
          <ComputedVerdict verdict={view.result.verdict} /> <EncoderZ readbackUm={view.result.zEncoderUm} />
          {view.result.warnings.map((w) => (
            <span key={w} className="reason">
              {" "}
              {w}
            </span>
          ))}
        </p>
      )}
    </section>
  );
}

/** Grade word for verdicts computed from classical metrics (T-010 stage 2 source "computed"). */
export const COMPUTED_GRADE = "computed";

/**
 * TEMPORARY: the shell's FocusVerdict always tags "model"; the 100x result is a
 * computed (classical-metric) verdict (ui-spec 5.3). Same five words, tagged COMPUTED_GRADE, until
 * the shared component takes a source (asked of T-010). Delete this then.
 */
function ComputedVerdict({ verdict }: { verdict: string }) {
  const v: Verdict = isVerdict(verdict) ? verdict : "unsure";
  return (
    <span className={`verdict verdict-${v}`} data-verdict={v}>
      {v.replace(/_/g, " ")} <span className="grade">{COMPUTED_GRADE}</span>
    </span>
  );
}

function SweepCurve({ view, ceilingUm }: { view: FocusView; ceilingUm: number | null }) {
  const W = 360;
  const H = 140;
  const zs = view.points.map((p) => p.zReadbackUm).concat(ceilingUm === null ? [] : [ceilingUm]);
  const ss = view.points.map((p) => p.score);
  const z0 = Math.min(...zs);
  const z1 = Math.max(...zs, z0 + 1);
  const s0 = Math.min(...ss);
  const s1 = Math.max(...ss, s0 + 1e-9);
  const x = (z: number) => 20 + ((z - z0) / (z1 - z0)) * (W - 40);
  const y = (s: number) => H - 15 - ((s - s0) / (s1 - s0)) * (H - 30);
  return (
    <svg width={W} height={H} role="img" aria-label="Sweep: score against Z read-back">
      {ceilingUm !== null && (
        <line data-testid="ceiling-line" x1={x(ceilingUm)} x2={x(ceilingUm)} y1={5} y2={H - 10} stroke="#e34948" strokeDasharray="4 3" />
      )}
      {view.points.map((p, i) => (
        <circle key={i} cx={x(p.zReadbackUm)} cy={y(p.score)} r={3}
                fill={p.saturated ? "#eb6834" : "#2a78d6"} data-saturated={p.saturated ? "true" : undefined} />
      ))}
      <text x={20} y={H - 2} fontSize={10}>{z0.toFixed(0)} µm (read)</text>
      <text x={W - 20} y={H - 2} fontSize={10} textAnchor="end">{z1.toFixed(0)}</text>
    </svg>
  );
}
