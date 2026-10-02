/**
 * Ask a question (F1.1). The server decides who may submit (D16: operator on the microscope PC,
 * mock store only); this form only shows that decision and its reason.
 */

import { type FormEvent, useState } from "react";

import {
  AGENTS,
  type Agent,
  type Permission,
  PURPOSES,
  type QuestionSummary,
  READ_ONLY_REASON,
  type StoreInfo,
  SUBMIT_OP,
  useConsoleApi,
} from "./api";
import { errorText, type LoadState } from "./ui";

/** The one fallback for every screen when `/api/permissions` cannot be read. Reads stay available. */
export const PERMISSION_UNAVAILABLE = "Permission check unavailable";
/** Shown on every screen while the first permission check is loading. */
export const PERMISSION_CHECKING = "Checking permissions…";

/**
 * Why submit is off, or undefined when it is on. The shared permission answer comes first
 * (remote, role, login: ui-spec 7.0 order), then the console's own rule, a read-only store.
 */
export function submitReason(
  perms: LoadState<Record<string, Permission>>,
  store: LoadState<StoreInfo>,
): string | undefined {
  if (perms.error !== undefined) return PERMISSION_UNAVAILABLE;
  if (perms.data === undefined) return PERMISSION_CHECKING;
  const p = perms.data[SUBMIT_OP];
  if (p === undefined) return PERMISSION_UNAVAILABLE;
  if (store.error !== undefined) return `Cannot read the store: ${store.error}`;
  if (store.data === undefined) return "Checking…";
  if (!p.allowed) return p.reason ?? "Not allowed";
  if (!store.data.writable) return READ_ONLY_REASON;
  return undefined;
}

export function SubmitForm({
  reason,
  onSubmitted,
}: {
  reason: string | undefined;
  onSubmitted: (q: QuestionSummary) => void;
}) {
  const api = useConsoleApi();
  const [text, setText] = useState("");
  const [target, setTarget] = useState<Agent>("microscope");
  const [purpose, setPurpose] = useState("");
  const [observable, setObservable] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);
  const [done, setDone] = useState<string | undefined>(undefined);

  const disabled = reason !== undefined || busy || text.trim() === "";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (disabled) return;
    setBusy(true);
    setError(undefined);
    setDone(undefined);
    try {
      const q = await api.submitQuestion({
        text,
        target,
        ...(purpose !== "" ? { purpose } : {}),
        ...(observable.trim() !== "" ? { observable: observable.trim() } : {}),
      });
      setText("");
      setDone(`Submitted as ${q.qid}`);
      onSubmitted(q);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form aria-label="Ask a question" className="console-submit" onSubmit={submit}>
      <label>
        Question
        <textarea value={text} rows={5} onChange={(e) => setText(e.target.value)} />
      </label>
      <div className="console-filters">
        <label>
          Agent{" "}
          <select value={target} onChange={(e) => setTarget(e.target.value as Agent)}>
            {AGENTS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
        <label>
          Purpose{" "}
          <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            <option value="">(leave to the person)</option>
            {PURPOSES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label>
          Observable <input value={observable} onChange={(e) => setObservable(e.target.value)} />
        </label>
      </div>
      <div className="console-filters">
        <button type="submit" disabled={disabled}>Submit question</button>
        {reason !== undefined && <span className="console-reason">{reason}</span>}
      </div>
      {error !== undefined && <p role="alert" className="console-error">{error}</p>}
      {done !== undefined && <p role="status">{done}</p>}
    </form>
  );
}
