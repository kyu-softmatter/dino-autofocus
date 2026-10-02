/**
 * What the simulation API sends, field for field the `to_dict()` of Python
 * `dino_autofocus.agents.simulation` (RunProgress, SimRunInfo, RunSeries, Curve, ZipEntry).
 * When the server router lands these are checked against the generated `src/api/` types.
 */

export type ProgressState = "running" | "complete" | "fault" | "aborted" | "unknown";

export interface RunProgressJson {
  run_id: string;
  state: ProgressState;
  source: "log" | "trajectory_meta" | "none";
  steps_taken: number | null;
  steps_total: number | null;
  fraction: number | null;
  frames_saved: number | null;
  frames_expected: number | null;
  simulated_time: number | null;
  started_at: string | null;
  updated_at: string | null;
  finished_at: string | null;
  elapsed_s: number | null;
  remaining_s: number | null;
  eta: string | null;
  stopped_by: string | null;
  failure: unknown;
}

export interface FileInfoJson {
  name: string;
  size: number;
}

export interface SimRunInfoJson {
  run_id: string;
  qid: string | null;
  backend: string | null;
  progress: RunProgressJson;
  files: FileInfoJson[];
  /** "<format>:<file>" when the server can read the trajectory */
  trajectory: string | null;
  trajectory_unavailable: string | null;
  source: string;
}

export interface CurveJson {
  path: string;
  x_name: string | null;
  x: (number | null)[];
  y: (number | null)[];
  /** a histogram has bin edges in x, one more than y */
  kind: "line" | "histogram";
}

export interface RunSeriesJson {
  run_id: string;
  /** one column per numeric field of the progress events, plus t_mono */
  log: Record<string, (number | null)[]>;
  observable: string | null;
  curves: CurveJson[];
  scalars: Record<string, number>;
  observables: unknown;
}

export interface ZipEntryJson {
  name: string;
  size: number;
  optional: boolean;
}
