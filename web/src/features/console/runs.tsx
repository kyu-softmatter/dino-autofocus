/** Run list and run detail (ui-spec 7.1). Simulation progress and trajectories live in the simulation area. */

import { useState } from "react";

import { areaHref } from "../../app/route";
import { useClient } from "../../app/client";
import { AGENTS, type Agent, PATHS, type RunDetail, type RunSummary } from "./api";
import { asArray, Fields, isRecord, Json, Loaded, shortTime, show, useLoad } from "./ui";

export function RunList({ runs, onOpen }: { runs: RunSummary[]; onOpen: (agent: Agent, runId: string) => void }) {
  const [agent, setAgent] = useState("");
  const shown = runs.filter((r) => agent === "" || r.agent === agent);
  return (
    <section aria-label="Runs">
      <div className="console-filters">
        <label>
          Agent{" "}
          <select value={agent} onChange={(e) => setAgent(e.target.value)}>
            <option value="">All</option>
            {AGENTS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
        <span className="console-muted">{shown.length} of {runs.length}</span>
      </div>
      <table className="console-table">
        <thead>
          <tr>
            <th>run_id</th><th>Agent</th><th>qid</th><th>plan_id</th><th>Backend</th><th>Started</th>
            <th>Finished</th><th>Approval</th><th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={`${r.agent}/${r.run_id}`}>
              <td><button className="console-link" onClick={() => onOpen(r.agent, r.run_id)}>{r.run_id}</button></td>
              <td>{r.agent}</td>
              <td>{r.qid ?? "—"}</td>
              <td>{r.plan_id ?? "—"}</td>
              <td>{r.backend ?? "—"}</td>
              <td>{shortTime(r.created_at)}</td>
              <td>{shortTime(r.finished_at)}</td>
              <td>{r.approval_kind ?? "—"}</td>
              <td>{r.status ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {shown.length === 0 && <p className="console-muted">No runs.</p>}
    </section>
  );
}

const LOG_NOTES = ["no_plan_because", "not_dispatched", "approved_commands", "approval", "stop_criteria"] as const;
const SIM_CONFIG = ["parameters_si", "envelope_check", "seed"] as const;
const SIM_OBSERVABLES = ["observable", "fit", "uncertainty", "relaxation"] as const;

export function RunDetailView({ agent, runId, refreshKey }: { agent: Agent; runId: string; refreshKey: number }) {
  const client = useClient();
  const state = useLoad(() => client.get<RunDetail>(PATHS.run(agent, runId)), [client, agent, runId, refreshKey]);
  return <Loaded state={state}>{(d) => <RunBody run={d} />}</Loaded>;
}

function RunBody({ run }: { run: RunDetail }) {
  const s = run.summary;
  const rec = (name: string) => (isRecord(run.records[name]) ? (run.records[name] as Record<string, unknown>) : undefined);
  const log = rec("log.json");
  const config = rec("config.json");
  const observables = rec("observables.json");
  return (
    <section aria-label={`Run ${s.run_id}`} className="console-detail">
      <header className="console-detail-head">
        <h2>{s.run_id}</h2>
        <span>{s.agent}</span>
        <span className="console-status">{s.status ?? "—"}</span>
        {s.source !== "soft-matter-agents" && <span className="console-tag">{s.source}</span>}
      </header>
      <Fields obj={{ ...s }} keys={["qid", "plan_id", "backend", "created_at", "finished_at"]} />
      {s.agent === "simulation" && (
        <p>
          <a href={areaHref("simulation", `runs/${s.run_id}`)}>Open in Simulation</a>{" "}
          <span className="console-muted">progress, trajectory, download</span>
        </p>
      )}
      {log !== undefined && <Fields obj={log} keys={LOG_NOTES} />}
      {config !== undefined && <Fields obj={config} keys={SIM_CONFIG} />}
      {observables !== undefined && <Fields obj={observables} keys={SIM_OBSERVABLES} />}
      {log !== undefined && <Events events={asArray(log.events)} />}
      {run.not_opened.length > 0 && <p className="console-muted">Not opened: {run.not_opened.join(", ")}</p>}
      {Object.entries(run.records).map(([name, value]) => <Json key={name} label={name} value={value} />)}
      <p className="console-muted">Files: {run.files.map((f) => f.name).join(", ") || "—"}</p>
    </section>
  );
}

/** The log's events in file order (already time order). */
function Events({ events }: { events: unknown[] }) {
  const rows = events.filter(isRecord);
  if (rows.length === 0) return null;
  return (
    <table className="console-table" aria-label="Events">
      <thead>
        <tr><th>t</th><th>Event</th><th>Fields</th></tr>
      </thead>
      <tbody>
        {rows.map((e, i) => {
          const { event, t_wall, t_mono, ...rest } = e;
          return (
            <tr key={i}>
              <td>{show(t_wall ?? t_mono)}</td>
              <td>{show(event)}</td>
              <td className="console-ellipsis">{show(rest)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
