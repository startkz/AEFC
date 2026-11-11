#!/usr/bin/env python3
"""Supplemental detached SHA256 inventory for the 96-cell IoT-J R4 heterogeneity pilot.

This script does not retrain or alter any experiment. It verifies the 96 JSON/PT
pairs against their per-run manifests, computes a detached SHA256 for every
manifest file, and writes a machine-readable inventory for the exact source run.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json

SEEDS = (80, 81, 82)
FACTORS = (
    "base", "dim", "saturation", "shift", "dim_saturation",
    "dim_shift", "saturation_shift", "dim_saturation_shift",
)
CONTROLS = ("adv", "adapter_frozen", "proto_alignment_off", "dense")
SOURCE_SHA = "be2d40a4c884a9b6730607e9bbfd8a045e9190db"
SOURCE_RUN_ID = 42959386414
SOURCE_ARTIFACT_ID = 13835176012
SOURCE_ARTIFACT_SHA256 = "82a572cb4b44edf8f9ea5f2262921876b625bc47a3e0a203a7a0b716c152144c"
EXPECTED = {(seed, factor, control) for seed in SEEDS for factor in FACTORS for control in CONTROLS}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def control_of(summary):
    mode = summary["method"]
    adapters = int(summary["disable_adapters"])
    proto = int(summary["disable_proto"])
    if mode == "dense" and not adapters and not proto:
        return "dense"
    if mode == "adv" and not adapters and not proto:
        return "adv"
    if mode == "adv" and adapters and not proto:
        return "adapter_frozen"
    if mode == "adv" and not adapters and proto:
        return "proto_alignment_off"
    raise ValueError(f"Unexpected control configuration: {mode}, {adapters}, {proto}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.root, args.out
    require(root.is_dir(), f"Evidence root does not exist: {root}")
    out.mkdir(parents=True, exist_ok=True)

    json_files = sorted(
        path for path in root.rglob("*.json")
        if not path.name.endswith(".manifest.json")
    )
    manifests = sorted(root.rglob("*.manifest.json"))
    checkpoints = sorted(root.rglob("*.pt"))
    require(len(json_files) == 96, f"Expected 96 raw JSON files, found {len(json_files)}")
    require(len(manifests) == 96, f"Expected 96 manifests, found {len(manifests)}")
    require(len(checkpoints) == 96, f"Expected 96 PT checkpoints, found {len(checkpoints)}")

    records = {}
    rows = []
    for path in json_files:
        manifest_path = path.with_suffix(".manifest.json")
        checkpoint_path = path.with_suffix(".pt")
        require(manifest_path.is_file(), f"Missing manifest: {manifest_path}")
        require(checkpoint_path.is_file(), f"Missing checkpoint: {checkpoint_path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = data["summary"]
        seed = int(summary["seed"])
        factor = summary["hetero"]
        control = control_of(summary)
        key = (seed, factor, control)
        require(key in EXPECTED, f"Unexpected experiment cell: {key}")
        require(key not in records, f"Duplicate experiment cell: {key}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        json_hash = sha256(path)
        checkpoint_hash = sha256(checkpoint_path)
        manifest_hash = sha256(manifest_path)
        require(manifest.get("git_commit") == SOURCE_SHA, f"{key}: source commit mismatch")
        require(manifest.get("source_json_sha256") == json_hash, f"{key}: JSON SHA256 mismatch")
        require(manifest.get("checkpoint_sha256") == checkpoint_hash, f"{key}: PT SHA256 mismatch")
        require(int(manifest.get("training_episodes_executed", -1)) == 1000,
                f"{key}: manifest training budget mismatch")
        require(len(data.get("train_episodes", [])) == 1000, f"{key}: missing training episodes")
        require(len(data.get("rounds", [])) == 200, f"{key}: missing federated rounds")
        require(len(data.get("tests", [])) == 10, f"{key}: missing held-out tests")
        summary_uplink = int(summary["uplink_bytes"])
        for round_record in data["rounds"]:
            actual = sum(int(value) for value in round_record["actual_serialized_client_bytes"])
            require(actual == int(round_record["uplink_bytes"]),
                    f"{key}: per-round serialized byte accounting mismatch")
        require(sum(int(record["uplink_bytes"]) for record in data["rounds"]) == summary_uplink,
                f"{key}: cumulative upload byte accounting mismatch")

        records[key] = True
        rows.append({
            "seed": seed,
            "factor": factor,
            "control": control,
            "json_sha256": json_hash,
            "checkpoint_sha256": checkpoint_hash,
            "manifest_sha256": manifest_hash,
            "git_commit": SOURCE_SHA,
            "training_episodes": len(data["train_episodes"]),
            "federated_rounds": len(data["rounds"]),
            "heldout_tests": len(data["tests"]),
            "application_uplink_bytes": summary_uplink,
        })

    missing = sorted(EXPECTED - set(records))
    require(not missing, f"Missing experiment cells: {missing}")
    rows.sort(key=lambda row: (row["seed"], FACTORS.index(row["factor"]), CONTROLS.index(row["control"])))

    inventory_path = out / "r4_hetero_manifest_sha256.csv"
    with inventory_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "passed": True,
        "source_run_id": SOURCE_RUN_ID,
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "source_artifact_sha256": SOURCE_ARTIFACT_SHA256,
        "source_code_sha": SOURCE_SHA,
        "expected_cells": 96,
        "audited_cells": len(rows),
        "json_files": len(json_files),
        "checkpoint_files": len(checkpoints),
        "manifest_files": len(manifests),
        "json_sha256_matches_manifest": 96,
        "checkpoint_sha256_matches_manifest": 96,
        "detached_manifest_sha256_computed": 96,
        "training_episode_records": sum(row["training_episodes"] for row in rows),
        "federated_round_records": sum(row["federated_rounds"] for row in rows),
        "heldout_test_records": sum(row["heldout_tests"] for row in rows),
        "independent_statistical_unit": "training seed; three-seed exploratory pilot only",
        "inventory": inventory_path.name,
        "scope": "hash and budget supplement; physical safety, censoring and intervention checks are rerun by audit_hetero_factorial.py",
    }
    (out / "r4_hetero_manifest_audit.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
