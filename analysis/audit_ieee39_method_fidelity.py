#!/usr/bin/env python3
"""TDSC-R1 *implementation identity* gate for genuine trained AEFC.

Prevents the scientific mistake of interpreting AEFC-style 4-dimensional
heuristic online updates (in this native MATLAB diagnostic) as evidence
for a fully trained federated reinforcement-learning recovery agent.
"""
from pathlib import Path
import json
import re

ROOT=Path(__file__).resolve().parents[1]
controller=(ROOT/"experiments/matlab/AEFCNativeController.m").read_text()
harness=(ROOT/"experiments/matlab/AEFCNativeStressAttackHarness.m").read_text()
runner=(ROOT/"experiments/matlab/aefc_ieee39_stress_recovery.m").read_text()
policy_ext={".pt",".pth",".onnx",".ckpt",".safetensors",".h5"}
trained=[str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
         if p.is_file() and p.suffix.lower() in policy_ext]
report=dict(
  full_AEFC_federated_reinforcement_learning_trained_checkpoint_verified=False,
  actual_neural_policy_weights_present_in_native_controller=False,
  MATLAB_controller_uses_four_dimensional_heuristic_adaptation=(
      "obj.theta=obj.theta-0.12*agg" in controller or
      "delta=-c.adaptation.eta*trust*g" in controller),
  original_offline_knowledge_updates_derived_from_normalized_speed=(
      "g=0.65*z+0.15*noise_g" in harness and
      "ev=-0.55*z+0.08*noise_e" in harness),
  native_stress_uses_true_physical_Simulink_plant=True,
  full_IEEE39_electrical_safety_proof_present=False,
  eligible_only_for="physical response diagnostic of AEFC mechanism prototype, not full trained RL algorithm performance",
  available_training_checkpoint_file_paths=trained,
  intended_publication_claim="BLOCKED_UNTIL_GENUINE_FROZEN_TRAINING_AND_POLICY_CHECKPOINT_EVIDENCE"
)
assert report["MATLAB_controller_uses_four_dimensional_heuristic_adaptation"]
assert report["original_offline_knowledge_updates_derived_from_normalized_speed"]
assert not report["actual_neural_policy_weights_present_in_native_controller"]
assert not report["full_AEFC_federated_reinforcement_learning_trained_checkpoint_verified"]
if __name__=="__main__":
    import argparse
    a=argparse.ArgumentParser()
    a.add_argument("--output",type=Path)
    opts=a.parse_args()
    if opts.output:
        opts.output.parent.mkdir(parents=True,exist_ok=True)
        opts.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(report,indent=2,ensure_ascii=False))
