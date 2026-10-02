import { useReadOnly } from "./client";
import { type AssistantStatus, type EngineStatus, type LastShutdown, useAssistantStatus, useEngineStatus } from "./status";
import { EncoderZ } from "./Verdict";

function fmt(v: unknown, digits = 1): string {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "—";
}

function LightsPart({ lights }: { lights: EngineStatus["lights"] }) {
  if (!lights) return <span className="sb-item muted">lights: unknown</span>;
  if (lights.error) return <span className="sb-item warn">lights: {lights.error}</span>;
  const anyOn = lights.lights.some((l) => l.on === true);
  return (
    <span className={`sb-item${anyOn ? " light-on" : ""}`} data-testid="sb-lights">
      {lights.lights.length === 0 && "lights: unknown"}
      {lights.lights.map((l) => (
        <span key={l.name} className="sb-light" data-on={String(l.on)}>
          {l.name} {l.on === true ? "ON" : l.on === false ? "off" : "?"}
        </span>
      ))}
      {lights.verified === false && <span className="warn"> (not read back)</span>}
    </span>
  );
}

function AssistantPart({ a }: { a: AssistantStatus }) {
  if (!a.available) return <span className="sb-item muted" data-testid="sb-assistant">assistant: unavailable</span>;
  return (
    <span className="sb-item" data-testid="sb-assistant" title="What the assistant may send to Claude (PLAN D7)">
      assistant: {a.provider ?? "?"} · data {a.data_stage ?? "?"}
      {a.connected === false && <span className="muted"> · not connected</span>}
    </span>
  );
}

/** Pure view, for tests and for screens that want the same line. */
export function StatusBarView({
  status,
  assistant,
  readOnly,
}: {
  status: EngineStatus;
  assistant: AssistantStatus;
  readOnly: { readOnly: boolean; why: string | null };
}) {
  const p = status.positions;
  return (
    <div className="status-bar" role="status" aria-live="polite">
      <span className={`sb-item ${status.connected ? "" : "warn"}`} data-testid="sb-server">
        {status.connected ? "server: connected" : "server: disconnected"}
      </span>
      {readOnly.readOnly && (
        <span className="sb-item badge" data-testid="sb-readonly" title={readOnly.why ?? undefined}>
          remote · read only
        </span>
      )}
      <LightsPart lights={status.lights} />
      <span className="sb-item" data-testid="sb-position">
        XY {fmt(p?.x_um)}, {fmt(p?.y_um)} µm · <EncoderZ readbackUm={p?.z_um ?? null} />
      </span>
      <span className="sb-item" data-testid="sb-running">
        {status.running.length === 0 ? "idle" : `running: ${status.running.map((o) => o.op).join(", ")}`}
      </span>
      <AssistantPart a={assistant} />
      {status.error && <span className="sb-item warn">state: {status.error}</span>}
    </div>
  );
}

export function StatusBar() {
  const status = useEngineStatus();
  const assistant = useAssistantStatus();
  const readOnly = useReadOnly();
  return <StatusBarView status={status} assistant={assistant} readOnly={readOnly} />;
}

/**
 * ui-spec 5.2: on the first screen, the light readback from the last shutdown.
 * Nothing when the engine reports none; a clear warning when a light did not read off.
 */
export function ShutdownNoticeView({ last, onDismiss }: { last: LastShutdown | null; onDismiss?: () => void }) {
  if (!last) return null;
  const when = typeof last.t === "number" ? new Date(last.t * 1000).toLocaleString() : "unknown time";
  const ok = last.all_off === true;
  return (
    <div className={`notice ${ok ? "" : "notice-warn"}`} role={ok ? "status" : "alert"} data-testid="shutdown-notice">
      {ok
        ? `Last shutdown (${when}): all lights read back off.`
        : `Last shutdown (${when}): a light did not read back off. Check the lights before you start.`}
      {onDismiss && (
        <button type="button" onClick={onDismiss}>
          Dismiss
        </button>
      )}
    </div>
  );
}
