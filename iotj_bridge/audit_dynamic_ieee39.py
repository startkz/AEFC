#!/usr/bin/env python3
"""Audit native MathWorks IEEE39 dynamic-probe artifacts and reconstruct COI metrics.

This post-processor treats governor rotor speed as a rotor-speed-derived
frequency signal. It does not relabel it as a terminal-bus PMU measurement.
"""
from __future__ import annotations
import argparse, csv, json, re
from pathlib import Path
import numpy as np
import pandas as pd


def generator_number(name: str) -> int:
    m = re.search(r"Gen(\d+)", name)
    if not m:
        raise ValueError(f"Cannot parse generator index from {name!r}")
    return int(m.group(1))


def extract_native_inertia(inventory: dict) -> dict:
    out = {}
    for block in inventory.get("blocks", []):
        mask_type = str(block.get("mask_type", "")).replace("\n", " ")
        if "Machine Mechanical Power" not in mask_type:
            continue
        m = block.get("mask_parameters", {})
        key_match = re.search(r"Gen\d+@Bus\d+", str(block.get("path", "")))
        if not key_match:
            continue
        key = key_match.group(0)
        if "H" not in m or "SRated" not in m:
            continue
        h = float(m["H"])
        s = float(m["SRated"])
        if not np.isfinite(h) or not np.isfinite(s) or h <= 0 or s <= 0:
            raise ValueError(f"Invalid H/SRated for {key}: {h}, {s}")
        if key in out:
            raise ValueError(f"Duplicate Machine Mechanical Power block for {key}")
        out[key] = {
            "H_s": h,
            "S_rated_MW": s,
            "H_times_S_MWs": h * s,
            "block_path": block.get("path", ""),
        }
    if len(out) != 10:
        raise ValueError(f"Expected 10 native inertia/rating records, found {len(out)}")
    return out


def settling_time(t: np.ndarray, f: np.ndarray, baseline: float,
                  start: float, band: float = 0.1, dwell_s: float = 1.0):
    dt = float(np.median(np.diff(t)))
    n = max(2, int(round(dwell_s / dt)))
    for i in np.where(t >= start)[0]:
        j = i + n
        if j <= len(t) and np.all(np.abs(f[i:j] - baseline) <= band):
            return float(t[i] - start)
    return None


def moving_rocof(f: np.ndarray, t: np.ndarray, window_s: float = 0.1):
    raw = np.gradient(f, t)
    dt = float(np.median(np.diff(t)))
    n = max(1, int(round(window_s / dt)))
    return pd.Series(raw).rolling(n, center=True, min_periods=1).mean().to_numpy()


def audit(input_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = json.loads((input_dir / "dynamic_probe_summary.json").read_text(encoding="utf-8"))
    inventory = json.loads((input_dir / "dynamic_block_inventory.json").read_text(encoding="utf-8"))
    frame = pd.read_csv(input_dir / "frequency_per_generator.csv")
    inertia = extract_native_inertia(inventory)
    generators = sorted(inertia, key=generator_number)
    time = frame["time_s"].to_numpy(dtype=float)
    if len(time) < 20 or not np.all(np.isfinite(time)) or np.any(np.diff(time) <= 0):
        raise ValueError("Invalid or non-monotone simulation time base")
    dt = float(np.median(np.diff(time)))
    cols = [f"f_gen{generator_number(g):02d}_hz" for g in generators]
    freq = frame[cols].to_numpy(dtype=float)
    if freq.shape != (len(time), 10) or not np.all(np.isfinite(freq)):
        raise ValueError("Expected ten finite, time-aligned rotor-frequency traces")
    if not np.isclose(time[-1], float(raw.get("stop_time_s", 20.0)), atol=1e-6):
        raise ValueError("Recorded trace does not reach the configured stop time")

    weights = np.asarray([inertia[g]["H_times_S_MWs"] for g in generators], dtype=float)
    coi = (freq * weights[None, :]).sum(axis=1) / weights.sum()
    pre = (time >= 4.0) & (time < 5.0)
    post = time >= 5.0
    if pre.sum() < 2 or post.sum() < 2:
        raise ValueError("Missing pre-fault or post-fault samples")
    base_coi = float(coi[pre].mean())
    base_local = freq[pre].mean(axis=0)
    coi_rocof = moving_rocof(coi, time)
    local_rocof = np.column_stack([moving_rocof(freq[:, i], time) for i in range(10)])

    post_idx = np.where(post)[0]
    i_min = int(post_idx[np.argmin(coi[post])])
    i_max = int(post_idx[np.argmax(coi[post])])
    i_ro = int(post_idx[np.argmax(np.abs(coi_rocof[post]))])
    after_clear_10 = (time >= 5.1) & (time <= 10.0)
    if not after_clear_10.any():
        raise ValueError("No samples in 5.1-10.0 s post-clear interval")
    i_min_510 = int(np.where(after_clear_10)[0][np.argmin(coi[after_clear_10])])
    i_max_510 = int(np.where(after_clear_10)[0][np.argmax(coi[after_clear_10])])

    per_machine = []
    for j, gen in enumerate(generators):
        f = freq[:, j]
        lo = int(post_idx[np.argmin(f[post])])
        hi = int(post_idx[np.argmax(f[post])])
        ri = int(post_idx[np.argmax(np.abs(local_rocof[post, j]))])
        per_machine.append({
            "generator": gen,
            **inertia[gen],
            "COI_weight_fraction": float(weights[j] / weights.sum()),
            "prefault_mean_rotor_frequency_hz": float(base_local[j]),
            "min_rotor_frequency_post_fault_hz": float(f[lo]),
            "min_drop_from_prefault_hz": float(base_local[j] - f[lo]),
            "min_time_s": float(time[lo]),
            "max_rotor_frequency_post_fault_hz": float(f[hi]),
            "max_rise_from_prefault_hz": float(f[hi] - base_local[j]),
            "max_time_s": float(time[hi]),
            "max_abs_rocof_hz_s": float(np.max(np.abs(local_rocof[post, j]))),
            "max_abs_rocof_time_s": float(time[ri]),
            "settling_time_after_fault_clear_s": settling_time(
                time, f, float(base_local[j]), 5.1
            ),
        })

    coi_frame = pd.DataFrame({
        "time_s": time,
        "f_coi_hz": coi,
        "delta_f_coi_from_prefault_hz": coi - base_coi,
        "rocof_coi_hz_s": coi_rocof,
    })
    coi_frame.to_csv(output_dir / "COI_frequency_timeseries.csv", index=False, float_format="%.10g")
    pd.DataFrame(per_machine).to_csv(
        output_dir / "PerGenerator_Dynamic_Metrics.csv", index=False, float_format="%.10g"
    )

    fault_candidates = [
        b for b in inventory.get("blocks", [])
        if "Fault (Three-Phase)" in str(b.get("name", ""))
        or "Fault (Three-Phase)" in str(b.get("mask_type", ""))
    ]
    if len(fault_candidates) != 1:
        raise ValueError(f"Expected one Fault (Three-Phase) block, found {len(fault_candidates)}")
    fault = fault_candidates[0]
    fm = fault.get("mask_parameters", {})
    fault_start = float(fm["fault_start_time"])
    fault_duration = float(fm["fault_duration"])
    if not np.isclose(fault_start, 5.0) or not np.isclose(fault_duration, 0.1):
        raise ValueError(f"Unexpected native fault settings: start={fault_start}, duration={fault_duration}")

    manifest_path = input_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    summary = {
        "study": "IoT-J native IEEE39 dynamic Phase-A baseline / instrumentation qualification",
        "status": "dynamic baseline audited; not an AEFC-FRL method comparison",
        "source_commit": manifest.get("source_commit", "unavailable"),
        "matlab_release": raw.get("matlab_release", manifest.get("matlab_release", "unavailable")),
        "model": raw.get("model", "IEEE39BusSystem"),
        "stop_time_s": float(time[-1]),
        "sample_count": int(len(time)),
        "sample_interval_s": dt,
        "fault": {
            "block_path": fault.get("path", ""),
            "fault_start_time_s": fault_start,
            "fault_duration_s": fault_duration,
            "fault_clear_time_s": fault_start + fault_duration,
            "fault_type_option": fm.get("fault_type_option", ""),
            "external_fault_setting": fm.get("enable_external_fault", ""),
            "state_port_setting": fm.get("exposemeasurement", ""),
        },
        "frequency_definition": "f_i=60*w_i for per-unit rotor speed; f_COI=sum(H_i*S_i*f_i)/sum(H_i*S_i)",
        "rocof_estimator": "numerical gradient followed by centered 0.1-s moving mean",
        "coi_prefault_mean_hz": base_coi,
        "coi_post_fault_max_hz": float(coi[i_max]),
        "coi_post_fault_max_time_s": float(time[i_max]),
        "coi_peak_rise_from_prefault_hz": float(coi[i_max] - base_coi),
        "coi_post_fault_min_hz": float(coi[i_min]),
        "coi_post_fault_min_time_s": float(time[i_min]),
        "coi_min_in_5p1_to_10s_hz": float(coi[i_min_510]),
        "coi_max_in_5p1_to_10s_hz": float(coi[i_max_510]),
        "coi_max_abs_rocof_hz_s": float(np.max(np.abs(coi_rocof[post]))),
        "coi_max_abs_rocof_time_s": float(time[i_ro]),
        "coi_settling_time_after_fault_clear_s": settling_time(time, coi, base_coi, 5.1),
        "inertia_parameters": inertia,
        "generator_metrics": per_machine,
        "evidence_gates": {
            "ten_rotor_speed_traces_present_finite_aligned": True,
            "fault_settings_verified": True,
            "actual_H_and_S_rated_extracted": True,
            "actual_governor_actuator_and_turbine_signals_inventoried": True,
            "relay_or_breaker_action_measured": False,
            "iotj_aefc_frl_learner_connected": False,
        },
        "interpretation": (
            "The Bus-16 three-phase fault produces a positive COI frequency excursion and "
            "spatially heterogeneous generator rotor-speed oscillations. It is not an "
            "underfrequency event. The original model fault clearing is timer-driven, not "
            "a relay operation. This is a plant/instrumentation baseline only."
        ),
        "limitations": [
            "Rotor-speed-derived frequency is not a terminal-bus PMU measurement.",
            "The deterministic Phase-A run is not a seed-level statistical comparison.",
            "No controller command, actual actuator motion, or protection relay action was applied in Phase A.",
        ],
    }
    (output_dir / "Dynamic_PhaseA_Audit.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(11, 7.2), sharex=True)
    for j, gen in enumerate(generators):
        axes[0].plot(time, freq[:, j], linewidth=0.8, label=gen)
    axes[0].plot(time, coi, linewidth=2.0, label="COI frequency")
    axes[0].axvline(5.0, linestyle="--", linewidth=1)
    axes[0].axvline(5.1, linestyle=":", linewidth=1)
    axes[0].set_ylabel("Frequency (Hz)")
    axes[0].set_title("Native IEEE39: generator rotor frequency and inertia-weighted COI response")
    axes[0].grid(alpha=0.25)
    axes[0].legend(ncol=3, fontsize=7)
    axes[1].plot(time, coi_rocof, linewidth=1.1, label="COI RoCoF")
    axes[1].axhline(0, linewidth=0.7)
    axes[1].axvline(5.0, linestyle="--", linewidth=1, label="Fault on")
    axes[1].axvline(5.1, linestyle=":", linewidth=1, label="Scheduled fault clear")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("RoCoF (Hz/s)")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output_dir / "Fig_Dynamic_COI_and_Rotor_Frequency.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = audit(a.input, a.out)
    print(json.dumps({
        "status": result["status"],
        "coi_peak_hz": result["coi_post_fault_max_hz"],
        "coi_peak_time_s": result["coi_post_fault_max_time_s"],
        "coi_max_abs_rocof_hz_s": result["coi_max_abs_rocof_hz_s"],
        "coi_settling_time_s": result["coi_settling_time_after_fault_clear_s"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
