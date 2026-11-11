#!/usr/bin/env python3
"""Detached manifest SHA256 inventory for the 40-cell IoTJ R4 coordinate audit."""
from pathlib import Path
import argparse
import csv
import hashlib
import json

SEEDS = tuple(range(80, 90))
MODES = ("adv", "ordinary", "coord_random", "coord_gradtopk")
SOURCE_SHA = "e674db8b7d00ce908614154bd6f3f21c1a3495ce"
SOURCE_RUN_ID = 42957084297
SOURCE_ARTIFACT_ID = 13830018801
SOURCE_ARTIFACT_SHA256 = "4421bb8a925f27f04d14fa48ac8922ff89f6bf9da6583551ce76b975db89879f"
EXPECTED = {(seed, mode) for seed in SEEDS for mode in MODES}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
    require(len(json_files) == 40, f"Expected 40 raw JSON files, found {len(json_files)}")
    require(len(manifests) == 40, f"Expected 40 manifests, found {len(manifests)}")
    require(len(checkpoints) == 40, f"Expected 40 PT checkpoints, found {len(checkpoints)}")

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
        mode = summary["method"]
        key = (seed, mode)
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

        round_bytes = []
        for round_record in data["rounds"]:
            actual = sum(int(value) for value in round_record["actual_serialized_client_bytes"])
            require(actual == int(round_record["uplink_bytes"]),
                    f"{key}: per-round serialized byte accounting mismatch")
            round_bytes.append(actual)
        uplink = int(summary["uplink_bytes"])
        require(sum(round_bytes) == uplink, f"{key}: cumulative byte accounting mismatch")
        records[key] = uplink
        rows.append({
            "seed": seed,
            "method": mode,
            "json_sha256": json_hash,
            "checkpoint_sha256": checkpoint_hash,
            "manifest_sha256": manifest_hash,
            "git_commit": SOURCE_SHA,
            "training_episodes": len(data["train_episodes"]),
            "federated_rounds": len(data["rounds"]),
            "heldout_tests": len(data["tests"]),
            "application_uplink_bytes": uplink,
        })

    missing = sorted(EXPECTED - set(records))
    require(not missing, f"Missing experiment cells: {missing}")
    for seed in SEEDS:
        values = [records[(seed, mode)] for mode in MODES]
        require(len(set(values)) == 1, f"Seed {seed}: methods do not have equal actual upload bytes")

    rows.sort(key=lambda row: (row["seed"], MODES.index(row["method"])))
    inventory_path = out / "r4_coordinate_manifest_sha256.csv"
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
        "expected_cells": 40,
        "audited_cells": len(rows),
        "json_files": len(json_files),
        "checkpoint_files": len(checkpoints),
        "manifest_files": len(manifests),
        "json_sha256_matches_manifest": 40,
        "checkpoint_sha256_matches_manifest": 40,
        "detached_manifest_sha256_computed": 40,
        "training_episode_records": sum(row["training_episodes"] for row in rows),
        "federated_round_records": sum(row["federated_rounds"] for row in rows),
        "heldout_test_records": sum(row["heldout_tests"] for row in rows),
        "actual_uplink_bytes_equal_across_four_methods_within_each_seed": True,
        "independent_statistical_unit": "training seed; ten paired seeds",
        "inventory": inventory_path.name,
        "scope": "hash and budget supplement; coordinate, serialized-byte and physical recovery checks are rerun by audit_coordinate_ablation.py",
    }
    (out / "r4_coordinate_manifest_audit.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
