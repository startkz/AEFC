#!/usr/bin/env python3
"""Audit six fixed, already completed MathWorks IEEE39 boundary-activation cells.

Data are downloaded from GitHub Actions run 39387453311, not rerun. Strictly
separate empirical sampled native checks from G1/G3/G5 theorem verification.
"""
import csv
import hashlib
import io
import json
import random
import tarfile
from pathlib import Path
from statistics import mean

ROOT = Path("results/p0_native_boundary_20261021")
ARCH = ROOT / "archives"
ROOT.mkdir(parents=True, exist_ok=True)
FROZEN_COMMIT = "67aa2c3cb5cb8d6d79b344e638c282f4f346ee39"
CELLS = {
    "qmin-0p43": ("qmin", 0.43),
    "qmin-0p48": ("qmin", 0.48),
    "rho-0p09": ("rho", 0.09),
    "rho-0p12": ("rho", 0.12),
    "trust-0p002": ("trust", 0.002),
    "trust-0p005": ("trust", 0.005),
}
COMMON_METRICS = (
    "safety_violation", "min_native_margin", "false_authorization_rate",
    "max_belief_distortion", "max_policy_drift", "recovery_success",
    "recovery_time", "shield_intervention_ratio",
)
errors = []
all_cells = {}
for cell_name, (kind, value) in CELLS.items():
    folder = ARCH / ("AEFC-P0-native-" + cell_name)
    if not folder.is_dir():
        errors.append("missing artifact " + cell_name)
        continue
    manifest = json.loads((folder/"manifest.json").read_text())
    if (manifest.get("commit_sha") != FROZEN_COMMIT or
            manifest.get("experiment_kind") != kind or
            abs(float(manifest.get("level_value", -999)) - value) > 1e-12 or
            manifest.get("seeds") != 20 or manifest.get("rows") != 20 or
            manifest.get("mapping_policy") != "paired-generator-physical-speed-v2" or
            not manifest.get("main_experiment_untouched")):
        errors.append(cell_name + " manifest mismatch")
    tarbytes = (folder/"raw-traces.tar.gz").read_bytes()
    sha256 = hashlib.sha256(tarbytes).hexdigest()
    recorded = (folder/"raw-traces.sha256").read_text().split()[0]
    if sha256 != recorded:
        errors.append(cell_name + " inner archive SHA256 mismatch")
    with tarfile.open(fileobj=io.BytesIO(tarbytes), mode="r:gz") as tar:
        members = {m.name: tar.extractfile(m).read()
                   for m in tar if m.isfile()}
    rows = list(csv.DictReader((folder/"summary.csv").open()))
    if len(rows) != 20 or {int(r["seed"]) for r in rows} != set(range(20)):
        errors.append(cell_name + " 20 seed summary mismatch")
    byseed = {}
    for seed in range(20):
        tracefile = f"AEFC-Full/seed_{seed:02d}.jsonl"
        summaryfile = f"AEFC-Full/seed_{seed:02d}.summary.json"
        if tracefile not in members or summaryfile not in members:
            errors.append(cell_name + f" tar missing seed {seed}")
            continue
        for name in (tracefile, summaryfile):
            if (folder/name).read_bytes() != members[name]:
                errors.append(cell_name + f" tar/files disagreement: {name}")
        trace = [json.loads(line) for line in members[tracefile].decode().splitlines()]
        summary = json.loads(members[summaryfile])
        if len(trace) != 73 or int(summary["seed"]) != seed:
            errors.append(cell_name + f" trace identity or 73 sample count: {seed}")
        if any(r.get("seed") != seed or r.get("scenario") != "joint" or
               r.get("method") != "AEFC-Full" for r in trace):
            errors.append(cell_name + f" trace row identity: {seed}")
        checks = {
            "max_belief_distortion": max(r["belief_distortion"] for r in trace),
            "max_policy_drift": max(r["policy_drift"] for r in trace),
            "min_native_margin": min(1-max(abs(z) for z in r["observation_normalized"]) for r in trace),
            "dangerous_proposal_count": sum(bool(r["dangerous_proposal"]) for r in trace),
            "dangerous_authorization_count": sum(bool(r["dangerous_proposal"]) and bool(r["gate_decision"]) for r in trace),
            "shield_intervention_ratio": sum(r["shield_intervention"] > 1e-8 for r in trace)/73,
            "gate_authorization_rate": sum(bool(r["gate_decision"]) for r in trace)/73,
            "mean_trust": sum(r["trust_score"] for r in trace)/73,
            "max_risk": max(r["risk_upper_bound"] for r in trace),
        }
        for field, value_check in checks.items():
            if abs(float(summary[field])-value_check) > 1e-9:
                errors.append(f"{cell_name}/{seed} trace/summary mismatch {field}")
        byseed[seed] = (summary, checks)
    for row in rows:
        s = byseed.get(int(row["seed"]))
        if s is None:
            continue
        for field in COMMON_METRICS + ("gate_authorization_rate", "mean_trust", "max_risk"):
            if abs(float(row[field])-float(s[0][field])) > 1e-9:
                errors.append(f"{cell_name}/{row['seed']} CSV/JSON mismatch {field}")
    all_cells[cell_name] = {
        "kind": kind, "setting": value, "manifest": manifest,
        "archive_sha256": sha256, "seed_rows": byseed
    }

# Verify two non-activating parameter cells are exact seed-matched copies of
# authoritative native Main joint Full; don't alter or regenerate Main.
main = {(r["method"], r["scenario"], int(r["seed"])): r
        for r in csv.DictReader(Path("results/ieee39_joint20/summary.csv").open())}
reproduction_max = 0.0
reproduction_count = 0
for name in ("qmin-0p43", "rho-0p12"):
    for seed, (summary, _) in all_cells[name]["seed_rows"].items():
        old = main.get(("AEFC-Full", "joint", seed))
        if old is None:
            errors.append(f"Main native joint missing seed {seed}")
            continue
        for field in COMMON_METRICS:
            difference = abs(float(old[field])-float(summary[field]))
            reproduction_max = max(reproduction_max, difference)
            reproduction_count += 1
if reproduction_count != 320 or reproduction_max > 1e-9:
    errors.append(f"Main reproduction {reproduction_count} comparisons, max difference {reproduction_max}")

# Deterministic exploratory paired bootstrap across 20 independent run seeds;
# not confidence intervals on independent samples within each episode.
rng = random.Random(20261021)
def paired_interval(x, baseline, B=10000):
    delta = [a-b for a,b in zip(x,baseline)]
    sims = sorted(mean(delta[rng.randrange(len(delta))] for _ in delta) for _ in range(B))
    return [mean(delta), sims[int(0.025*B)], sims[int(0.975*B)]]
baseline = all_cells["qmin-0p43"]["seed_rows"]
output = []
for name, cell in all_cells.items():
    v = cell["seed_rows"]
    drift = [v[i][0]["max_policy_drift"] for i in range(20)]
    base_drift = [baseline[i][0]["max_policy_drift"] for i in range(20)]
    row = {
        "cell": name,
        "parameter": cell["setting"], "method": "AEFC-Full",
        "seed_count": 20, "sample_count": 1460,
        "gate_rejections": sum(round((1-v[i][0]["gate_authorization_rate"])*73) for i in range(20)),
        "gate_authorization_mean": mean(v[i][0]["gate_authorization_rate"] for i in range(20)),
        "adapt_accept_mean": mean(sum(bool(j["adapt_accepted"]) for j in
                        [json.loads(s) for s in (ARCH/("AEFC-P0-native-"+name)/"AEFC-Full"/f"seed_{i:02d}.jsonl").read_text().splitlines()])/73 for i in range(20)),
        "max_policy_drift_mean": mean(drift),
        "max_belief_distortion_mean": mean(v[i][0]["max_belief_distortion"] for i in range(20)),
        "min_native_margin_mean": mean(v[i][0]["min_native_margin"] for i in range(20)),
        "safety_violation_count": sum(int(v[i][0]["safety_violation"]) for i in range(20)),
        "dangerous_proposal_count": sum(int(v[i][0]["dangerous_proposal_count"]) for i in range(20)),
        "shield_intervention_ratio_mean": mean(v[i][0]["shield_intervention_ratio"] for i in range(20)),
        "recovery_time_marker_mean": mean(v[i][0]["recovery_time"] for i in range(20)),
        "archive_sha256": cell["archive_sha256"],
    }
    row["paired_drift_difference"], row["paired_drift_ci_low"], row["paired_drift_ci_high"] = paired_interval(drift,base_drift)
    output.append(row)
with (ROOT/"summary.csv").open("w", newline="") as f:
    writer=csv.DictWriter(f,fieldnames=list(output[0]))
    writer.writeheader()
    writer.writerows(output)
report = {
    "github_actions_run": 39387453311, "run_commit": FROZEN_COMMIT,
    "status": "validated" if not errors else "FAILED",
    "experiments": 120, "samples": 8760, "cells": 6,
    "source_level": "native IEEE39 sampled parameter sensitivity, NOT G1/G3/G5 certificate",
    "main_experiment": "560 authoritative episodes preserved",
    "main_seedwise_reproduction_count": reproduction_count,
    "main_seedwise_reproduction_max_abs": reproduction_max,
    "cells_summary": output,
    "errors": errors,
}
(ROOT/"audit.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
print(json.dumps({"status":report["status"],"episodes":120,"samples":8760,
                  "main_check_max":reproduction_max,"cells":[{"cell":x["cell"],"gate_rejections":x["gate_rejections"],"mean_drift":x["max_policy_drift_mean"]} for x in output],
                  "errors":errors},indent=2))
if errors:
    raise SystemExit("P0 IEEE39 native archive acceptance FAILED")
