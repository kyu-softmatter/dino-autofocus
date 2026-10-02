import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EncoderZ, FocusVerdict, isVerdict, VERDICTS } from "./Verdict";

describe("FocusVerdict", () => {
  it("knows exactly the five verdict words", () => {
    expect(VERDICTS).toEqual(["in_focus", "step_up", "step_down", "no_sample_here", "unsure"]);
    expect(isVerdict("step_up")).toBe(true);
    expect(isVerdict("3012.5")).toBe(false);
    expect(isVerdict(3012.5)).toBe(false);
  });

  it.each(VERDICTS)("shows %s tagged as model output", (v) => {
    const { container } = render(<FocusVerdict verdict={v} />);
    const el = container.querySelector(".verdict")!;
    expect(el.getAttribute("data-verdict")).toBe(v);
    expect(el.getAttribute("data-invalid")).toBeNull();
    expect(el.textContent).toContain("model");
  });

  it("never passes a number or an unknown word through: shows Unsure, marked invalid", () => {
    const { container } = render(<FocusVerdict verdict={3012.5} />);
    const el = container.querySelector(".verdict")!;
    expect(el.getAttribute("data-verdict")).toBe("unsure");
    expect(el.getAttribute("data-invalid")).toBe("true");
    expect(el.textContent).not.toContain("3012");
  });
});

describe("EncoderZ", () => {
  it("shows the read-back in um", () => {
    render(<EncoderZ readbackUm={3048.712} />);
    expect(screen.getByText("Z 3048.71 µm")).toBeTruthy();
  });

  it("shows a dash when Z could not be read", () => {
    render(<EncoderZ readbackUm={null} />);
    expect(screen.getByText("Z —")).toBeTruthy();
  });
});
