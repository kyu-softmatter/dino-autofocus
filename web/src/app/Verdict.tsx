/**
 * Shared display of model output and of Z (PLAN 6, rule 3): a model gives a
 * verdict from a fixed vocabulary, never a Z; Z shown to people comes from the
 * encoder read-back only.
 */

export const VERDICTS = ["in_focus", "step_up", "step_down", "no_sample_here", "unsure"] as const;
export type Verdict = (typeof VERDICTS)[number];

export function isVerdict(v: unknown): v is Verdict {
  return typeof v === "string" && (VERDICTS as readonly string[]).includes(v);
}

const LABEL: Record<Verdict, string> = {
  in_focus: "In focus",
  step_up: "Step up",
  step_down: "Step down",
  no_sample_here: "No sample here",
  unsure: "Unsure",
};

/**
 * A model verdict, tagged "model". Anything outside the five words is shown as
 * "Unsure" (and marked invalid) rather than passed through.
 */
export function FocusVerdict({ verdict }: { verdict: unknown }) {
  const ok = isVerdict(verdict);
  const v: Verdict = ok ? verdict : "unsure";
  return (
    <span className={`verdict verdict-${v}`} data-verdict={v} data-invalid={ok ? undefined : "true"}
          title={ok ? undefined : `not a verdict word: ${String(verdict)}`}>
      {LABEL[v]} <span className="grade">model</span>
    </span>
  );
}

/** Z from the encoder read-back (ZDrive), in um. null when it could not be read. */
export function EncoderZ({ readbackUm, digits = 2 }: { readbackUm: number | null | undefined; digits?: number }) {
  const ok = typeof readbackUm === "number" && Number.isFinite(readbackUm);
  return (
    <span className="encoder-z" title="ZDrive encoder read-back">
      Z {ok ? `${readbackUm.toFixed(digits)} µm` : "—"}
    </span>
  );
}
