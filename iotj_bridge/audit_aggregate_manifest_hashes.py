#!/usr/bin/env python3
"""Detached manifest SHA256 inventory for the 10-seed R4 aggregate-update study."""
from pathlib import Path
import argparse
import csv
import hashlib
import json

SEEDS = tuple(range(80, 90))
SOURCE_SHA = "65f28231f3c3d13d8a50893cc99f224edf670faa"
SOURCE_RUN_ID = 42962801194
SOURCE_ARTIFACT_ID = 13831945798
SOURCE_ARTIFACT_SHA256 = "759532d8f5af32122b533d5865aac7d97c86515efe98c41434db61033fb45213"


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
    require(len(json_files) == 10, f"Expected 10 raw JSON files, found {len(json_files)}")
    require(len(manifests) == 10, f"Expected 10 manifests, found {len(manifests)}")
    require(len(checkpoints) == 10, f"Expected 10 PT checkpoints, found {len(checkpoints)}")

    seen = set()
    rows = []
    for path in json_files:
        manifest_path = path.with_suffix(".manifest.json")
        checkpoint_path = path.with_suffix(".pt")
        require(manifest_path.is_file(), f"Missing manifest: {manifest_path}")
        require(checkpoint_path.is_file(), f"Missing checkpoint: {checkpoint_path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = data["summary"]
        seed = int(summary["seed"])
        require(seed in SEEDS and seed not in seen, f"Unexpected/duplicate seed: {seed}")
        seen.add(seed)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        json_hash = sha256(path)
        checkpoint_hash = sha256(checkpoint_path)
        manifest_hash = sha256(manifest_path)
        require(manifest.get("git_commit") == SOURCE_SHA, f"Seed {seed}: source commit mismatch")
        require(manifest.get("source_json_sha256") == json_hash, f"Seed {seed}: JSON SHA256 mismatch")
        require(manifest.get("checkpoint_sha256") == checkpoint_hash, f"Seed {seed}: PT SHA256 mismatch")
        require(int(manifest.get("training_episodes_executed", -1)) == 1000,
                f"Seed {seed}: manifest training budget mismatch")
        require(len(data.get("train_episodes", [])) == 1000, f"Seed {seed}: missing training episodes")
        require(len(data.get("rounds", [])) == 200, f"Seed {seed}: missing federation rounds")
        require(len(data.get("tests", [])) == 10, f"Seed {seed}: missing held-out tests")
        impact = summary.get("aggregate_candidate_update_impact", [])
        require(len(impact) == 9, f"Seed {seed}: expected 9 paired physical profiles")
        rows.append({
            "seed": seed,
            "json_sha256": json_hash,
            "checkpoint_sha256": checkpoint_hash,
            "manifest_sha256": manifest_hash,
            "git_commit": SOURCE_SHA,
            "training_episodes": len(data["train_episodes"]),
            "federated_rounds": len(data["rounds"]),
            "heldout_tests": len(data["tests"]),
            "paired_physical_profiles": len(impact),
            "application_uplink_bytes": int(summary["uplink_bytes"]),
        })

    require(seen == set(SEEDS), f"Missing seeds: {sorted(set(SEEDS)-seen)}")
    rows.sort(key=lambda row: row["seed"])
    inventory_path = out / "r4_aggregate_manifest_sha256.csv"
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
        "expected_seeds": 10,
        "audited_seeds": len(rows),
        "json_files": len(json_files),
        "checkpoint_files": len(checkpoints),
        "manifest_files": len(manifests),
        "json_sha256_matches_manifest": 10,
        "checkpoint_sha256_matches_manifest": 10,
        "detached_manifest_sha256_computed": 10,
        "training_episode_records": sum(row["training_episodes"] for row in rows),
        "federated_round_records": sum(row["federated_rounds"] for row in rows),
        "heldout_test_records": sum(row["heldout_tests"] for row in rows),
        "paired_physical_profiles": sum(row["paired_physical_profiles"] for row in rows),
        "independent_statistical_unit": "training seed; ten seeds",
        "inventory": inventory_path.name,
        "scope": "hash and budget supplement; physical recovery, demand perturbation and applied-update checks are rerun by audit_aggregate_gain.py",
    }
    (out / "r4_aggregate_manifest_audit.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
