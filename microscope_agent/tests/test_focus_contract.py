# origin: dino-autofocus, public since 2026-10-03:
#   https://github.com/kyu-softmatter/dino-autofocus/blob/fa9790378ea3f06e94b933a2fb65219322f6702a/microscope_agent/tests/test_focus_contract.py
# body-sha256: 1a6a1d8993a3f2422c3c01af5e6094485a144331a46b85af1bfcf60ec5963971
"""The verdict and run-log event contracts (D-07): what goes in, what comes out, in JSON.

Pins the module docstrings' "Contract" sections of focus_verdict.py and focus_run_log.py so a
change to either shape is a failing test here before it is a surprise in soft-matter-agents.
Loaded by path, stdlib + numpy only; runs with `python -m unittest` and under pytest."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parents[1] / "src"


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


classical = _load("_mic_focus_classical", SRC / "focus_classical.py")
verdict = _load("_mic_focus_verdict", SRC / "focus_verdict.py")
run_log = _load("_mic_focus_run_log", SRC / "focus_run_log.py")

# This repository's provisional thresholds; the modules hold none of their own (D-02).
RULES = {"min_dynamic_range_adu": 20.0, "min_contrast": 0.05, "min_frames": 3,
         "dropout_tolerance": 0.02, "max_saturated": 0.001}
DOF = {"in_focus_dof": 1.0, "max_sigma_dof": 3.0}
SMA_BRANCHES = ("in_focus", "step_up", "step_down", "no_sample_here", "unsure")


def _frame(sigma_px):
    yy, xx = np.mgrid[0:64, 0:64]
    spot = np.exp(-((yy - 32.0) ** 2 + (xx - 32.0) ** 2) / (2 * sigma_px ** 2))
    return (200 + 3000 * spot * (2.0 / sigma_px) ** 2).astype(np.uint16)


def _sweep(blurs=(6.0, 3.5, 2.0, 3.5, 6.0)):
    z = [100.0 + 2.0 * i for i in range(len(blurs))]
    stats = [classical.frame_stats(_frame(s), "vollath4") for s in blurs]
    return z, stats


class Reading:
    """What the live module's ``FocusReading`` provides, with model numbers."""

    def __init__(self, score, sigma, tiles=(0, 1, 2), n_used=3, sign_known=True):
        self.score, self.sigma, self.n_used = score, sigma, n_used
        self.tiles, self.sign_known = list(tiles), sign_known


class Vocabulary(unittest.TestCase):
    def test_the_vocabulary_is_the_soft_matter_agents_focus_branches(self):
        self.assertEqual(verdict.VERDICTS, SMA_BRANCHES)
        self.assertEqual(verdict.SOURCES, ("sweep", "dino"))
        self.assertEqual(verdict.GRADES, ("measured", "computed", "model"))


class SweepRecord(unittest.TestCase):
    def test_record_has_exactly_the_contract_keys_and_is_json(self):
        z, stats = _sweep()
        rec = verdict.from_sweep(z, stats, **RULES).as_record()
        self.assertEqual(tuple(rec), verdict.RECORD_KEYS)
        self.assertEqual(json.loads(json.dumps(rec, allow_nan=False)), rec)
        self.assertIn(rec["verdict"], verdict.VERDICTS)
        self.assertEqual(rec["source"], "sweep")
        self.assertTrue(rec["reason"])
        for e in rec["evidence"]:
            self.assertEqual(set(e), {"name", "value", "grade", "unit"})
            self.assertIn(e["grade"], verdict.GRADES)

    def test_z_is_the_readback_of_the_frame_the_verdict_points_at(self):
        z, stats = _sweep()
        v = verdict.from_sweep(z, stats, **RULES)
        self.assertEqual(v.verdict, verdict.Verdict.IN_FOCUS)
        self.assertIsNotNone(v.frame_index)
        self.assertEqual(v.z_um, z[v.frame_index])
        self.assertEqual(v.as_record()["z_grade"], "measured")
        self.assertFalse(v.has_model_numbers)

    def test_a_refusing_verdict_carries_no_z_and_no_frame(self):
        z, stats = _sweep()
        dark = [classical.frame_stats(np.full((64, 64), 100, np.uint16), "vollath4")
                for _ in z]
        v = verdict.from_sweep(z, dark, **RULES)
        self.assertEqual(v.verdict, verdict.Verdict.NO_SAMPLE_HERE)
        rec = v.as_record()
        self.assertIsNone(rec["z_um"])
        self.assertIsNone(rec["frame_index"])
        self.assertIsNone(rec["z_grade"])

    def test_thresholds_are_required_and_lengths_must_match(self):
        z, stats = _sweep()
        with self.assertRaises(TypeError):
            verdict.from_sweep(z, stats)  # no defaults: the caller names every threshold
        with self.assertRaises(ValueError):
            verdict.from_sweep(z[:-1], stats, **RULES)


class ReadingRecord(unittest.TestCase):
    def test_model_numbers_are_evidence_graded_model_and_z_stays_the_readback(self):
        v = verdict.from_reading(Reading(score=2.5, sigma=0.5), 3010.0, 7, **DOF)
        self.assertEqual(v.verdict, verdict.Verdict.STEP_DOWN)
        self.assertEqual((v.source, v.frame_index, v.z_um), ("dino", 7, 3010.0))
        self.assertTrue(v.has_model_numbers)
        grades = {e.name: e.grade for e in v.evidence}
        self.assertEqual((grades["dz"], grades["sigma"]), ("model", "model"))
        rec = v.as_record()
        self.assertEqual(tuple(rec), verdict.RECORD_KEYS)
        self.assertEqual(json.loads(json.dumps(rec, allow_nan=False)), rec)

    def test_dof_thresholds_are_required(self):
        with self.assertRaises(TypeError):
            verdict.from_reading(Reading(score=0.1, sigma=0.5), 3000.0, 0)

    def test_each_branch_is_reachable(self):
        v = verdict.from_reading
        self.assertEqual(v(Reading(0.1, 0.5), 3000.0, 0, **DOF).verdict, verdict.Verdict.IN_FOCUS)
        self.assertEqual(v(Reading(-2.0, 0.5), 3000.0, 0, **DOF).verdict, verdict.Verdict.STEP_UP)
        self.assertEqual(v(Reading(2.0, 0.5), 3000.0, 0, **DOF).verdict, verdict.Verdict.STEP_DOWN)
        self.assertEqual(v(Reading(2.0, 0.5, tiles=()), 3000.0, 0, **DOF).verdict,
                         verdict.Verdict.NO_SAMPLE_HERE)
        self.assertEqual(v(Reading(2.0, 9.0), 3000.0, 0, **DOF).verdict, verdict.Verdict.UNSURE)


class RunLogEvent(unittest.TestCase):
    def test_event_has_exactly_the_contract_keys_and_no_command_fields(self):
        z, stats = _sweep()
        ev = run_log.to_run_log_event(verdict.from_sweep(z, stats, **RULES), 12.5)
        self.assertEqual(tuple(ev), run_log.EVENT_KEYS)
        self.assertFalse(set(run_log.COMMAND_KEYS) & set(ev))
        self.assertEqual(json.loads(json.dumps(ev, allow_nan=False)), ev)
        self.assertEqual((ev["event"], ev["time_base"], ev["t_mono"]),
                         (run_log.EVENT, "software", 12.5))
        self.assertIn(ev["choice"], SMA_BRANCHES)
        self.assertEqual(set(ev["z"]), {"value", "unit", "grade", "read_from"})
        self.assertEqual((ev["z"]["unit"], ev["z"]["grade"], ev["z"]["read_from"]),
                         ("um", "E1", "z_drive"))
        self.assertEqual(ev["z"]["value"], z[ev["frame_index"]])
        for e in ev["evidence"]:
            self.assertIn(e["grade"], ("E1", "E4"))
            self.assertTrue({"name", "value"} <= set(e) <= {"name", "value", "unit", "grade"})
        self.assertEqual(ev["signals"], [])

    def test_model_numbers_become_signals_without_a_grade_and_no_e6_anywhere(self):
        ev = run_log.to_run_log_event(
            verdict.from_reading(Reading(2.5, 0.5), 3010.0, 7, **DOF), 3.0, time_base="device")
        self.assertEqual(ev["time_base"], "device")
        self.assertEqual({s["name"] for s in ev["signals"]}, {"dz", "sigma", "n_used"})
        for s in ev["signals"]:
            self.assertNotIn("grade", s)
        self.assertNotIn("E6", json.dumps(ev))
        self.assertEqual(ev["z"]["value"], 3010.0)

    def test_refused_inputs(self):
        z, stats = _sweep()
        v = verdict.from_sweep(z, stats, **RULES)
        with self.assertRaises(ValueError):
            run_log.to_run_log_event(v, float("nan"))
        with self.assertRaises(ValueError):
            run_log.to_run_log_event(v, 1.0, time_base="wall")

    def test_non_finite_evidence_becomes_none(self):
        v = verdict.from_reading(Reading(float("nan"), 0.5), None, None, **DOF)
        ev = run_log.to_run_log_event(v, 0.0)
        self.assertIsNone(ev["z"])
        dz = next(s for s in ev["signals"] if s["name"] == "dz")
        self.assertIsNone(dz["value"])
        json.dumps(ev, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
