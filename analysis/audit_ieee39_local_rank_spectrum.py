#!/usr/bin/env python3
"""Audit local IEEE39 linearized observability/controllability spectra.

MATLAB v7.3 files are HDF5; MATLAB stores dimensions in column-major order,
so each dataset is transposed after reading with h5py. This script computes
the same finite-horizon observability/controllability matrices used by the
MATLAB probe, then reports numerical ranks at several relative tolerances.
These are local linearized diagnostics, not nonlinear DAE safety certificates.
"""
from __future__ import annotations
import argparse
import glob
import json
import os
from pathlib import Path
import h5py
import numpy as np

RELATIVE_TOLERANCES = (1e-6, 1e-8, 1e-10, 1e-12, 1e-14)

def read_mat73(path: str):
    with h5py.File(path, "r") as f:
        def get(name):
            return np.asarray(f[name]).T.astype(np.float64, copy=False)
        A, B = get("A"), get("B")
        C_online, C_all10 = get("C_online"), get("C_all10")
    return A, B, C_online, C_all10

def observability_matrix(A, C):
    n = A.shape[0]
    blocks = []
    P = C.copy()
    for _ in range(n):
        blocks.append(P)
        P = P @ A
    return np.vstack(blocks)

def controllability_matrix(A, B):
    n = A.shape[0]
    blocks = []
    P = B.copy()
    for _ in range(n):
        blocks.append(P)
        P = A @ P
    return np.hstack(blocks)

def spectrum_summary(M):
    s = np.linalg.svd(M, compute_uv=False)
    machine_tol = max(M.shape) * np.finfo(np.float64).eps * s[0]
    return {
        "matrix_shape": list(M.shape),
        "singular_value_count": int(s.size),
        "sigma_max": float(s[0]),
        "sigma_min": float(s[-1]),
        "condition_number": float(s[0] / max(s[-1], np.finfo(float).tiny)),
        "machine_precision_tolerance": float(machine_tol),
        "machine_precision_rank": int(np.sum(s > machine_tol)),
        "relative_tolerance_ranks": {
            f"{tol:.0e}": int(np.sum(s > tol * s[0]))
            for tol in RELATIVE_TOLERANCES
        },
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", help="Directory containing native_local_abc_t*.mat")
    ap.add_argument("--output", default="local_rank_spectrum_audit.json")
    args = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(args.directory, "native_local_abc_t*.mat")))
    if len(paths) != 2:
        raise SystemExit(f"Expected exactly two MATLAB operating-point files, found {len(paths)}")
    results = []
    for path in paths:
        A, B, C_online, C_all10 = read_mat73(path)
        n = A.shape[0]
        if A.shape != (n, n) or B.shape[1] != n or C_online.shape[1] != n or C_all10.shape[1] != n:
            raise SystemExit(f"Inconsistent matrix dimensions in {path}")
        O_online = observability_matrix(A, C_online)
        O_all10 = observability_matrix(A, C_all10)
        Co = controllability_matrix(A, B)
        results.append({
            "file": Path(path).name,
            "state_dimension": int(n),
            "input_channels": int(B.shape[1]),
            "online_output_channels": int(C_online.shape[0]),
            "offline_all_generator_output_channels": int(C_all10.shape[0]),
            "online_observability": spectrum_summary(O_online),
            "offline_ten_speed_observability": spectrum_summary(O_all10),
            "four_action_channel_controllability": spectrum_summary(Co),
        })
    payload = {
        "scope": "local linearized IEEE39 model only",
        "relative_tolerances": list(RELATIVE_TOLERANCES),
        "full_network_observer_verified": False,
        "nonlinear_DAE_reachability_certified": False,
        "intersample_safety_certified": False,
        "operating_points": results,
    }
    Path(args.output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))

if __name__ == "__main__":
    main()
