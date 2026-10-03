import { useCallback, useEffect, useState } from "react";

import { useClient, useEngineEvents } from "../../app/client";
import {
  type PatternOut,
  type PatternSummary,
  patternDuration,
  PatternReadout,
  PatternScrubber,
  patternTime,
  targetLabel,
} from "../../app/patterns";
import { areaHref, useAreaPath } from "../../app/route";
import { type CamFrame, LiveView, PatternOverlay, type Trap, TrapOverlay } from "../../app/live";

const TRAP_EVENTS = ["motion", "finished"] as const;

/** `?pattern=<id>` in the route rest */
function patternIdOf(rest: string): string {
  return new URLSearchParams(rest.replace(/^[^?]*\??/, "")).get("pattern") ?? "";
}

/**
 * The live area (owned by the shell, T-010). Route: `#/live`, or `#/live?pattern=<id>` to draw a
 * saved motion pattern over the frames (coloured by time, gray to dark green) with a time slider.
 * With tweezers on the setup, "Traps" draws where each trap is now (the Tweezers area moves them).
 * The overlays are display only: they move nothing.
 */
export default function LiveScreen() {
  const client = useClient();
  const [rest, setRest] = useAreaPath();
  const id = patternIdOf(rest);
  const [list, setList] = useState<PatternSummary[]>([]);
  const [pattern, setPattern] = useState<PatternOut | null>(null);
  const [t, setT] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [traps, setTraps] = useState<Trap[] | null>(null);
  const [showTraps, setShowTraps] = useState(true);

  useEffect(() => {
    client.get<PatternSummary[]>("/api/patterns").then(setList, () => setList([]));
  }, [client]);

  const readTraps = useCallback(() => {
    client.get<{ tweezers?: { traps?: Trap[] } | null }>("/api/state").then(
      (s) => setTraps(s.tweezers ? (s.tweezers.traps ?? []) : null),
      () => setTraps(null),
    );
  }, [client]);
  useEffect(readTraps, [readTraps]);
  useEngineEvents(readTraps, TRAP_EVENTS);

  useEffect(() => {
    setT(0);
    if (!id) {
      setPattern(null);
      setError(null);
      return;
    }
    client.get<PatternOut>(`/api/patterns/${encodeURIComponent(id)}`).then(
      (p) => {
        setPattern(p);
        setError(null);
      },
      (e) => {
        setPattern(null);
        setError(e instanceof Error ? e.message : String(e));
      },
    );
  }, [client, id]);

  const trapsShown = showTraps && traps !== null;
  const overlay = useCallback(
    (frame: CamFrame) => (
      <>
        {pattern && <PatternOverlay pattern={pattern} t={t} meta={frame.meta} />}
        {trapsShown && traps && <TrapOverlay traps={traps} meta={frame.meta} />}
      </>
    ),
    [pattern, t, trapsShown, traps],
  );

  return (
    <section aria-label="Live view">
      <h2>Live view</h2>
      <div className="patterns-bar">
        <label>
          Pattern overlay{" "}
          <select
            aria-label="Pattern overlay"
            value={id}
            onChange={(e) => setRest(e.target.value ? `?pattern=${encodeURIComponent(e.target.value)}` : "")}
          >
            <option value="">none</option>
            {list.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        {pattern && (
          <>
            <span className="muted">{pattern.tracks.map((tr) => targetLabel(tr.target)).join(", ")}</span>
            <a href={areaHref("patterns", pattern.id)}>Edit</a>
          </>
        )}
        {error && <span className="warn">{error}</span>}
        {traps !== null && (
          <label>
            <input type="checkbox" checked={showTraps} onChange={(e) => setShowTraps(e.target.checked)} /> Traps
          </label>
        )}
      </div>
      {pattern && (
        <>
          <PatternScrubber duration={patternDuration(pattern)} t={t} onTime={setT} loop={pattern.loop} />
          <PatternReadout tracks={pattern.tracks} t={patternTime(pattern, t)} />
        </>
      )}
      <LiveView overlay={pattern || trapsShown ? overlay : undefined} />
    </section>
  );
}
