import { useState } from "react";

import type { SimulationClient } from "./client";
import { Graphs } from "./Graphs";
import { useFrame, usePolled } from "./hooks";
import { usePlayback } from "./playback";
import { ProgressPanel } from "./Progress";
import type { ZipEntryJson } from "./types";
import { Viewers } from "./Viewers";

/** How often a running run is read again. Later the server pushes progress (T-009). */
export const PROGRESS_MS = 2000;
export const SERIES_MS = 10000;

function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} kB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

/** F6.2: the run folder as one zip; the trajectory goes in only when ticked. */
function Download({ client, runId, entries }: { client: SimulationClient; runId: string; entries: ZipEntryJson[] | null }) {
  const [withOptional, setWithOptional] = useState(false);
  const optional = entries?.filter((e) => e.optional) ?? [];
  const total = (entries ?? []).filter((e) => withOptional || !e.optional).reduce((s, e) => s + e.size, 0);
  const href = client.zipUrl(runId, withOptional);
  return (
    <section className="sim-panel" aria-label="Download">
      <div className="sim-row">
        {href ? (
          <a className="sim-button" href={href} download={`${runId}.zip`}>
            Download {runId}.zip
          </a>
        ) : (
          <button type="button" disabled title="The mock has no files to send; the server serves the zip">
            Download {runId}.zip
          </button>
        )}
        {entries ? <span className="muted">about {size(total)}</span> : null}
        {optional.length ? (
          <label>
            <input type="checkbox" checked={withOptional} onChange={(e) => setWithOptional(e.target.checked)} /> include{" "}
            {optional.map((e) => `${e.name.split("/").pop()} (${size(e.size)})`).join(", ")}
          </label>
        ) : null}
      </div>
    </section>
  );
}

export function RunDetail({ client, runId, onBack }: { client: SimulationClient; runId: string; onBack: () => void }) {
  const [running, setRunning] = useState(false);
  const info = usePolled(runId, () => client.getRun(runId), running ? PROGRESS_MS : null);
  const series = usePolled(runId, () => client.getSeries(runId), running ? SERIES_MS : null);
  const entries = usePolled(`${runId}:${info.data?.files.length ?? 0}`, () => client.zipEntries(runId), null);

  const isRunning = info.data?.progress.state === "running";
  if (isRunning !== running && info.data) setRunning(isRunning);

  const hasTrajectory = !!info.data?.trajectory;
  const nFrames = hasTrajectory ? (info.data?.progress.frames_saved ?? 0) : 0;
  const playback = usePlayback(nFrames);
  const { frame, error: frameError } = useFrame(client, runId, playback.index, hasTrajectory && nFrames > 0);

  return (
    <div className="sim-detail">
      <p>
        <a
          href="#/simulation"
          onClick={(e) => {
            e.preventDefault();
            onBack();
          }}
        >
          ← all runs
        </a>
      </p>
      <h2>{runId}</h2>
      {info.error ? <p role="alert">{info.error}</p> : null}
      {info.data ? (
        <>
          <p className="muted">
            {info.data.backend ?? "unknown backend"}
            {info.data.qid ? ` · question ${info.data.qid}` : ""} · from {info.data.source}
          </p>
          <ProgressPanel p={info.data.progress} />
          <Download client={client} runId={runId} entries={entries.data} />
          {hasTrajectory ? (
            <Viewers frame={frame} nFrames={nFrames} playback={playback} error={frameError} />
          ) : (
            <section className="sim-panel" aria-label="Trajectory">
              <p className="muted">No trajectory to show: {info.data.trajectory_unavailable ?? "none recorded"}.</p>
            </section>
          )}
          {series.data ? <Graphs series={series.data} /> : series.error ? <p role="alert">{series.error}</p> : null}
        </>
      ) : info.loading ? (
        <p className="muted">Loading…</p>
      ) : null}
    </div>
  );
}
