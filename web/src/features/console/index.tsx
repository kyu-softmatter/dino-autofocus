/**
 * Console area: the agents' questions, runs and inbox, and asking a question
 * (PLAN F1, ui-spec 7.1, docs/screens/console.md). Reads only; the one write is a question to
 * the mock store, which the server allows or refuses.
 *
 * `rest` forms (after `#/console/`):
 *   "" | "questions"          question list
 *   "questions/<qid>"         one question, latest version
 *   "runs"                    run list
 *   "runs/<agent>/<run_id>"   one run
 *   "inbox"                   inbox threads
 *   "ask"                     ask a question
 *
 * Data is read when the area opens and on "Refresh"; nothing polls.
 */

import { useCallback, useMemo, useState } from "react";

import { useAreaPath } from "../../app/route";
import { useScreenContext } from "../../app/screenContext";
import { AGENTS, type Agent, SUBMIT_OP, useConsoleApi } from "./api";
import "./console.css";
import { Inbox } from "./inbox";
import { QuestionDetailView, QuestionList, type QuestionSelection } from "./questions";
import { RunDetailView, RunList } from "./runs";
import { SubmitForm, submitReason } from "./submit";
import { Loaded, useLoad } from "./ui";

type Tab = "questions" | "runs" | "inbox" | "ask";

interface View {
  tab: Tab;
  qid?: string;
  agent?: Agent;
  runId?: string;
}

export function parseRest(rest: string): View {
  const parts = rest.replace(/[?#].*$/, "").split("/").filter((p) => p !== "").map(decodeURIComponent);
  switch (parts[0]) {
    case "questions":
      return parts[1] ? { tab: "questions", qid: parts[1] } : { tab: "questions" };
    case "runs": {
      const agent = AGENTS.find((a) => a === parts[1]);
      return agent && parts[2] ? { tab: "runs", agent, runId: parts[2] } : { tab: "runs" };
    }
    case "inbox":
      return { tab: "inbox" };
    case "ask":
      return { tab: "ask" };
    default:
      return { tab: "questions" };
  }
}

const TABS: { id: Tab; label: string }[] = [
  { id: "questions", label: "Questions" },
  { id: "runs", label: "Runs" },
  { id: "inbox", label: "Inbox" },
  { id: "ask", label: "Ask" },
];

export default function ConsoleScreen() {
  const api = useConsoleApi();
  const [rest, setRest] = useAreaPath();
  const view = parseRest(rest);
  const [refreshKey, setRefreshKey] = useState(0);
  const [sel, setSel] = useState<QuestionSelection | undefined>(undefined);
  const onSelect = useCallback((s: QuestionSelection) => setSel(s), []);

  const storeInfo = useLoad(() => api.storeInfo(), [api, refreshKey]);
  const perms = useLoad(() => api.permissions([SUBMIT_OP]), [api, refreshKey]);
  const questions = useLoad(() => api.listQuestions(), [api, refreshKey]);
  const runs = useLoad(() => api.listRuns(), [api, refreshKey]);
  const inbox = useLoad(() => api.listInbox(), [api, refreshKey]);

  // prompt context (X1): short ids only, no card bodies (D7)
  const qid = view.qid;
  const version = qid !== undefined ? sel?.version : undefined;
  const cardKind = qid !== undefined ? sel?.card_kind : undefined;
  const details = useMemo(() => {
    const d: Record<string, string | number> = {};
    if (qid !== undefined) d.qid = qid;
    if (version !== undefined) d.version = version;
    if (cardKind !== undefined) d.card_kind = cardKind;
    if (view.runId !== undefined) d.run_id = view.runId;
    if (view.agent !== undefined) d.agent = view.agent;
    return d;
  }, [qid, version, cardKind, view.runId, view.agent]);
  useScreenContext(details);

  const store = storeInfo.data;
  return (
    <div className="console">
      <div className="console-bar">
        <nav role="tablist" aria-label="Console" className="console-tabs">
          {TABS.map((t) => (
            <button key={t.id} role="tab" aria-selected={view.tab === t.id} onClick={() => setRest(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
        {store !== undefined && (
          <span className="console-tag">
            Store: {store.store}{store.writable ? "" : " (read-only)"}
          </span>
        )}
        <button onClick={() => setRefreshKey((k) => k + 1)}>Refresh</button>
      </div>

      {view.tab === "questions" && view.qid === undefined && (
        <Loaded state={questions}>
          {(qs) => <QuestionList questions={qs} onOpen={(q) => setRest(`questions/${encodeURIComponent(q)}`)} />}
        </Loaded>
      )}
      {view.tab === "questions" && view.qid !== undefined && (
        <>
          <button className="console-link" onClick={() => setRest("questions")}>← All questions</button>
          <QuestionDetailView key={view.qid} qid={view.qid} refreshKey={refreshKey} onSelect={onSelect} />
        </>
      )}
      {view.tab === "runs" && view.runId === undefined && (
        <Loaded state={runs}>
          {(rs) => (
            <RunList runs={rs} onOpen={(a, r) => setRest(`runs/${a}/${encodeURIComponent(r)}`)} />
          )}
        </Loaded>
      )}
      {view.tab === "runs" && view.agent !== undefined && view.runId !== undefined && (
        <>
          <button className="console-link" onClick={() => setRest("runs")}>← All runs</button>
          <RunDetailView agent={view.agent} runId={view.runId} refreshKey={refreshKey} />
        </>
      )}
      {view.tab === "inbox" && <Loaded state={inbox}>{(ts) => <Inbox threads={ts} />}</Loaded>}
      {view.tab === "ask" && (
        <SubmitForm reason={submitReason(perms, storeInfo)} onSubmitted={() => setRefreshKey((k) => k + 1)} />
      )}
    </div>
  );
}
