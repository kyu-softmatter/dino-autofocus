/**
 * `hardware` area (PLAN F2, ui-spec 7.2, contract docs/screens/hardware.md).
 * Shows the last detection, the gate verdict and the light read-back. Commands
 * go to the common command endpoint; refusals are drawn, not decided, here.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { useScreenContext } from "../../app/screenContext";
import {
  type CommandIn,
  type EngineEvent,
  type GateRow,
  type HardwareProfileOut,
  type LightState,
  type Permissions,
  SCREEN_OPS,
  type StatusResultOut,
  useHardwareApi,
} from "./api";
import {
  blockedBy,
  CameraPiezoPanel,
  ConfirmedPanel,
  CurrentStatePanel,
  DevicesPanel,
  GatesPanel,
  LightsPanel,
  ObjectivesPanel,
  Reason,
  SummaryPanel,
} from "./panels";
import "./hardware.css";

type NoticeKey = "scan" | "confirm" | "status" | "lights";

const NOTICE_OF_OP: Record<string, NoticeKey> = {
  hardware_scan: "scan",
  hardware_confirm: "confirm",
  status: "status",
  light_set: "lights",
};

const EMPTY_PROFILE: HardwareProfileOut = { profile: null, path: null, sha256: null };

function failureText(ev: EngineEvent): string {
  const d = ev.data;
  if (ev.kind === "error") return `error: ${String(d.message ?? "unknown")}`;
  const checks = Array.isArray(d.checks) ? (d.checks as { ok?: boolean; why?: string; name?: string }[]) : [];
  const why = checks.filter((c) => c.ok === false).map((c) => c.why ?? c.name ?? "check failed");
  return `preflight failed: ${why.length > 0 ? why.join("; ") : String(d.why ?? "no reason given")}`;
}

export default function HardwareScreen() {
  const api = useHardwareApi();
  const [profile, setProfile] = useState<HardwareProfileOut>(EMPTY_PROFILE);
  const [gates, setGates] = useState<GateRow[]>([]);
  const [status, setStatus] = useState<StatusResultOut | null>(null);
  const [permissions, setPermissions] = useState<Permissions>({});
  const [lights, setLights] = useState<{ state: LightState | null; t: number | null }>({ state: null, t: null });
  const [zUm, setZUm] = useState<number | null | undefined>(undefined);
  const [running, setRunning] = useState<{ op: string; op_id: string } | null>(null);
  const [notices, setNotices] = useState<Partial<Record<NoticeKey, string>>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [device, setDevice] = useState<string | null>(null);
  const [gate, setGate] = useState<string | null>(null);
  const [includeProperties, setIncludeProperties] = useState(true);
  const [piezoPort, setPiezoPort] = useState(""); // "" skips the piezo (contract G10)

  const reloadProfile = useCallback(async () => {
    const [p, g] = await Promise.all([api.profile(), api.gates()]);
    setProfile(p);
    setGates(g);
  }, [api]);

  // re-read after anything that changes the engine's answer (start, end of an op)
  const reloadPermissions = useCallback(async () => {
    setPermissions(await api.permissions(SCREEN_OPS));
  }, [api]);

  useEffect(() => {
    let live = true;
    Promise.all([api.profile(), api.gates(), api.status(), api.state(), api.permissions(SCREEN_OPS)])
      .then(([p, g, s, st, perms]) => {
        if (!live) return;
        setProfile(p);
        setGates(g);
        setStatus(s);
        setPermissions(perms);
        setRunning(st.running ?? null);
        setZUm(st.position?.z_um);
        if (st.lights) setLights({ state: st.lights, t: st.lights_t ?? null });
      })
      .catch((e: unknown) => live && setLoadError(String(e)));
    return () => {
      live = false;
    };
  }, [api]);

  useEffect(
    () =>
      api.subscribe((ev) => {
        const op = typeof ev.data.op === "string" ? ev.data.op : "";
        switch (ev.kind) {
          case "position":
            setZUm(ev.data.z_um as number | null | undefined);
            return;
          case "light_changed":
            setLights({ state: ev.data as unknown as LightState, t: ev.t });
            return;
          case "started":
            setRunning({ op, op_id: ev.op_id });
            void reloadPermissions();
            return;
          case "finished":
          case "aborted":
          case "error":
          case "preflight_failed":
            setRunning((r) => (r && (r.op_id === ev.op_id || r.op === op) ? null : r));
            if (ev.kind === "finished" && op === "status") {
              setStatus({ op_id: ev.op_id, t: ev.t, user_id: null, summary: (ev.data.summary ?? {}) as StatusResultOut["summary"] });
            }
            if (NOTICE_OF_OP[op]) {
              const key = NOTICE_OF_OP[op];
              const text = ev.kind === "error" || ev.kind === "preflight_failed" ? failureText(ev) : undefined;
              setNotices((n) => ({ ...n, [key]: ev.kind === "aborted" ? `stopped: ${String(ev.data.why ?? "")}` : text }));
            }
            if (op === "hardware_scan" || op === "hardware_confirm") void reloadProfile();
            void reloadPermissions();
            return;
        }
      }),
    [api, reloadProfile, reloadPermissions],
  );

  const details = useMemo(() => {
    const d: Record<string, unknown> = {};
    if (device) d.device = device;
    if (gate) {
      d.gate = gate;
      d.gate_reasons = gates.find((g) => g.op === gate)?.reasons ?? [];
    }
    return d;
  }, [device, gate, gates]);
  useScreenContext(details);

  const send = useCallback(
    async (key: NoticeKey, cmd: CommandIn) => {
      setNotices((n) => ({ ...n, [key]: undefined }));
      const r = await api.submit(cmd);
      if (!r.ok) setNotices((n) => ({ ...n, [key]: `refused: ${r.detail}` }));
    },
    [api],
  );

  const gateOf = (op: string) => gates.find((g) => g.op === op);
  const blocked = (op: string) => blockedBy(permissions[op], gateOf(op));
  const runningOp = running?.op ?? null;
  const scanBlocked = blocked("hardware_scan");
  const confirmBlocked = blocked("hardware_confirm");
  const statusBlocked = blocked("status");
  const lightBlocked = blocked("light_set");
  const offBlocked = blockedBy(permissions.lights_off);

  return (
    <div className="hw-screen">
      <h2>Hardware</h2>
      {loadError ? <p className="hw-warn">Could not load the hardware state: {loadError}</p> : null}

      <section aria-label="Scan">
        <div className="hw-row">
          <button type="button" disabled={scanBlocked !== null}
                  onClick={() => send("scan", { kind: "start", op: "hardware_scan", args: { include_properties: includeProperties, piezo_port: piezoPort } })}>
            Scan hardware
          </button>
          <label>
            <input type="checkbox" checked={includeProperties} disabled={scanBlocked !== null}
                   onChange={(e) => setIncludeProperties(e.target.checked)} /> all properties
          </label>
          <input aria-label="Piezo port" placeholder="piezo port (empty = skip)" value={piezoPort}
                 disabled={scanBlocked !== null} onChange={(e) => setPiezoPort(e.target.value)} />
          <span className="muted">Reads only. Nothing moves or turns on.</span>
          <Reason text={scanBlocked} />
        </div>
        <Reason text={notices.scan ?? null} />
      </section>

      <div className="hw-grid">
        <SummaryPanel out={profile} />
        <CurrentStatePanel status={status} zUm={zUm} blocked={statusBlocked}
                           onRun={() => send("status", { kind: "start", op: "status" })} />
        <LightsPanel lights={lights.state} lightsT={lights.t} setBlocked={lightBlocked} offBlocked={offBlocked}
                     running={runningOp}
                     onBrightfield={() => send("lights", { kind: "start", op: "light_set", args: { mode: "brightfield" } })}
                     onAura={(line, percent) => send("lights", { kind: "start", op: "light_set", args: { mode: "aura", line, percent } })}
                     onOff={() => send("lights", { kind: "lights_off" })} />
        <CameraPiezoPanel out={profile} />
      </div>
      <Reason text={notices.status ?? notices.lights ?? null} />

      <GatesPanel gates={gates} selected={gate} onSelect={setGate} />
      <DevicesPanel devices={profile.profile?.devices ?? []} selected={device} onSelect={setDevice} />
      <ObjectivesPanel out={profile} />
      <ConfirmedPanel out={profile} blocked={confirmBlocked}
                      onSave={(name, value) => send("confirm", { kind: "start", op: "hardware_confirm", args: { items: { [name]: value } } })} />
      <Reason text={notices.confirm ?? null} />
    </div>
  );
}
