#!/usr/bin/env python3
"""Audit archived native supplemental traces; do not rerun or alter simulations."""
import csv
import json
import math
import os
from pathlib import Path

ROOT = Path("results/p0-audit-artifacts")
MAIN = Path("results/ieee39_joint20/summary.csv")
OUT = Path("results/p0_audit_20261020")
OUT.mkdir(parents=True, exist_ok=True)
CELLS = {
    "intensity-0p5": 100, "intensity-1": 100, "intensity-1p5": 100, "intensity-2": 100,
    "gate-0": 40, "gate-0p25": 40, "gate-0p5": 40, "gate-0p75": 40, "gate-1": 40,
    "qmin-0p1": 20, "qmin-0p3": 20, "rho-0p4": 20, "rho-0p7": 20,
    "trust-0p02": 20, "trust-0p06": 20,
}
FIELDS = (
    "max_belief_distortion", "max_policy_drift", "min_native_margin",
    "dangerous_proposal_count", "dangerous_authorization_count", "shield_intervention_ratio"
)
COMPARE = (
    "safety_violation", "min_native_margin", "false_authorization_rate",
    "max_belief_distortion", "max_policy_drift", "recovery_success",
    "recovery_time", "shield_intervention_ratio"
)
main = {(r["method"], int(r["seed"])): r
        for r in csv.DictReader(MAIN.open(encoding="utf8"))
        if r["scenario"] == "joint"}
errors, results = [], []
count_checks = samples = episodes = count_compare = 0
max_reproduction_error = 0.0
for name, expected in CELLS.items():
    dirs = list(ROOT.glob("supp-native-" + name + "-*"))
    if len(dirs) != 1:
        errors.append(f"{name}: expected one downloaded artifact folder, got {len(dirs)}")
        continue
    folder = dirs[0]
    traces = sorted(folder.glob("*/*.jsonl"))
    if len(traces) != expected:
        errors.append(f"{name}: expected {expected} episodes, got {len(traces)}")
    cell_samples = cell_checks = cell_dangers = cell_authorized = 0
    cell_max = 0.0
    for path in traces:
        summary_path = path.with_name(path.stem + ".summary.json")
        if not summary_path.exists():
            errors.append(f"{path}: no matching summary"); continue
        summary = json.loads(summary_path.read_text())
        rows = [json.loads(s) for s in path.read_text().splitlines() if s]
        if len(rows) != 73:
            errors.append(f"{path}: expected 73 samples, got {len(rows)}")
        if any(r["seed"] != summary["seed"] or r["method"] != summary["method"] for r in rows):
            errors.append(f"{path}: identity mismatch")
        actual = {
            "max_belief_distortion": max(r["belief_distortion"] for r in rows),
            "max_policy_drift": max(r["policy_drift"] for r in rows),
            "min_native_margin": min(1-max(abs(z) for z in r["observation_normalized"]) for r in rows),
            "dangerous_proposal_count": sum(int(r["dangerous_proposal"]) for r in rows),
            "dangerous_authorization_count": sum(int(r["dangerous_proposal"]) and int(r["gate_decision"]) for r in rows),
            "shield_intervention_ratio": sum(r["shield_intervention"] > 1e-8 for r in rows) / len(rows),
        }
        for key in FIELDS:
            diff = abs(actual[key] - float(summary[key]))
            cell_max = max(cell_max, diff)
            cell_checks += 1
            if not math.isfinite(diff) or diff > 1e-8:
                errors.append(f"{path}: {key} discrepancy {diff}")
        if name == "intensity-1":
            identifier = (summary["method"], int(summary["seed"]))
            old = main.get(identifier)
            if old is None:
                errors.append(f"Main lacks {identifier}")
            else:
                for field in COMPARE:
                    d = abs(float(summary[field])-float(old[field]))
                    max_reproduction_error = max(max_reproduction_error, d)
                    count_compare += 1
        cell_dangers += actual["dangerous_proposal_count"]
        cell_authorized += actual["dangerous_authorization_count"]
        cell_samples += len(rows)
    samples += cell_samples
    episodes += len(traces)
    count_checks += cell_checks
    results.append({"cell": name, "episodes": len(traces), "samples": cell_samples,
                    "metric_checks": cell_checks, "dangerous": cell_dangers,
                    "authorized": cell_authorized, "max_discrepancy": cell_max})
if episodes != 720 or samples != 52560 or count_checks != 4320 or count_compare != 800:
    errors.append(f"unexpected totals episodes={episodes}, samples={samples}, checks={count_checks}, reproduction={count_compare}")
if max_reproduction_error > 1e-9:
    errors.append(f"gamma=1 reproduction error {max_reproduction_error} exceeded 1e-9")
report = {"kind": "archived-evidence-recomputation-only", "new_simulations": 0,
          "source_run": 33713969987, "total_episodes": episodes, "samples": samples,
          "metric_checks": count_checks, "main_reproduction_comparisons": count_compare,
          "main_reproduction_max_difference": max_reproduction_error,
          "cells": results, "errors": errors}
(OUT/"audit.json").write_text(json.dumps(report, indent=2)+"\n")
print(json.dumps(report, indent=2))
if errors:
    raise SystemExit(f"Failed P0 archived-evidence audit: {len(errors)} problems")
