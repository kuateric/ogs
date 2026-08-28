#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 3:
    raise SystemExit("usage: th2m-t2a-fresh-birth-contract.py TH2MFEM.h TH2MFEM-impl.h")

header = Path(sys.argv[1]).read_text(encoding="utf-8")
impl = Path(sys.argv[2]).read_text(encoding="utf-8")

# TH2M-T2A — literature-guided fresh-birth architecture contract.
#
# Established staged-construction semantics used by the next runtime gate:
# - Abaqus MODEL CHANGE strain-free reactivation: the configuration at
#   reactivation is the new stress-free reference; full physical stiffness is
#   present immediately.
# - PLAXIS staged construction/reset semantics: newly placed/reactivated soil
#   can be treated as virgin material while stresses/state variables are reset
#   independently of the deformed mesh geometry.
# - Stress-free-state construction theory: an installed element's reference
#   state is an explicit state variable; global equilibrium is solved for the
#   construction-induced disequilibrium rather than by softening the element.
#
# This gate does not change production TH2M. It freezes the canonical state
# ownership points that T2B must use for an actual fresh-birth implementation.

required_header = {
    "canonical material-state initialization":
        "initializeInternalStateVariables(",
    "canonical material-state commit":
        "material_state.pushBackState();",
    "trial/committed constitutive state separation":
        "this->material_states_[ip].pushBackState();",
    "TH2M current-to-previous state commit":
        "this->prev_states_[ip] = this->current_states_[ip];",
    "TH2M local initialization hook":
        "void initializeConcrete() override",
    "TH2M post-timestep commit hook":
        "void postTimestepConcrete(",
}
for label, token in required_header.items():
    if token not in header:
        raise RuntimeError(f"TH2M-T2A missing {label}: {token}")

required_impl = {
    "current total strain from displacement":
        "ip_out.eps_data.eps.noalias() = Bu * displacement;",
    "previous displacement enters mechanical strain history":
        "Bu * displacement_prev, prev_state.mechanical_strain_data,",
    "previous effective stress enters solid constitutive integration":
        "prev_state.eff_stress_data,",
    "material state is passed to constitutive model":
        "this->material_states_[ip],",
}
for label, token in required_impl.items():
    if token not in impl:
        raise RuntimeError(f"TH2M-T2A missing {label}: {token}")

# Safety invariants for T2B. These are deliberately explicit: the birth event
# must rebase kinematics and reset constitutive history together. Resetting only
# one side would either import stale inactive-domain strain/stress or corrupt a
# material model's internal history (including MFront/MGIS state variables).
contract = {
    "u_birth": "capture last converged displacement at activation and use u-u_birth constitutively",
    "previous_birth_kinematics": "zero in birth-relative coordinates for the birth equilibrium solve",
    "effective_stress_birth": "zero unless an explicit placement stress is supplied",
    "material_state_birth": "fresh initializeInternalStateVariables state plus committed baseline",
    "scalar_birth_state": "explicit p_g, p_c, T placement values; never implicit zero",
    "operator": "full physical stiffness/coupling from first active assembly",
    "equilibrium": "solve only global construction-induced disequilibrium at constant physical time",
    "forbidden": "stiffness scaling, residual homotopy, material homotopy, stale constitutive history",
}

print("TH2M-T2A PASS — canonical fresh-birth state ownership verified")
for key, value in contract.items():
    print(f"{key}={value}")
print("canonical_ogs_sha=adf770974c7ee0435702fe617634d03d17ab7cb8")
print("production_patch=none")
