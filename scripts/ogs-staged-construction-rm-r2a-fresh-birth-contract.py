#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 4:
    raise SystemExit("usage: rm-r2a-fresh-birth-contract.py LocalAssemblerInterface.h RichardsMechanicsFEM.h RichardsMechanicsFEM-impl.h")

iface = Path(sys.argv[1]).read_text(encoding="utf-8")
header = Path(sys.argv[2]).read_text(encoding="utf-8")
impl = Path(sys.argv[3]).read_text(encoding="utf-8")

# RM-R2A freezes canonical ownership points required by the runtime fresh-birth
# implementation. This is intentionally not the full R2 PASS.
required_iface = {
    "fresh material state factory": "solid_material_.createMaterialStateVariables()",
    "material state storage": "material_states_",
    "committed state update": "s.pushBackState();",
    "current to previous state commit": "prev_states_[ip] = current_states_[ip];",
}
for label, token in required_iface.items():
    if token not in iface:
        raise RuntimeError(f"RM-R2A missing {label}: {token}")

required_header = {
    "material internal initialization": "initializeInternalStateVariables(",
    "initial material state commit": "this->material_states_[ip].pushBackState();",
    "current/previous state baseline": "this->prev_states_[ip] = SD;",
    "RM initialization hook": "void initializeConcrete() override",
}
for label, token in required_header.items():
    if token not in header:
        raise RuntimeError(f"RM-R2A missing {label}: {token}")

required_impl = {
    "explicit liquid pressure DOF": "auto const [p_L, u] = localDOF(local_x);",
    "liquid placement state current": "*p_L_m = -p_cap_ip;",
    "liquid placement state previous": "**p_L_m_prev = -p_cap_ip;",
    "mechanical strain from displacement": "eps.noalias() = B * u;",
    "assembled mechanical strain from displacement": "eps.eps.noalias() = B * u;",
    "constitutive state passed to material": "*this->material_states_[ip].material_state_variables",
}
for label, token in required_impl.items():
    if token not in impl:
        raise RuntimeError(f"RM-R2A missing {label}: {token}")

contract = {
    "u_birth": "last converged displacement; constitutive strain uses u-u_birth",
    "birth_stress": "zero effective stress unless explicit placement stress is supplied",
    "p_L0": "explicit hydraulic placement state, copied consistently to current and previous hydraulic state",
    "material_state": "fresh createMaterialStateVariables + initializeInternalStateVariables + committed baseline",
    "mfront_mgis": "no stale state variables may survive inactive interval",
    "operator": "full physical RM pressure/displacement operator from first active assembly",
    "equilibrium": "construction-induced disequilibrium only, constant physical time",
    "forbidden": "stiffness scaling, residual homotopy, material homotopy",
}

print("RM-R2A PASS — canonical fresh-birth ownership points verified")
for k, v in contract.items():
    print(f"{k}={v}")
print("canonical_ogs_sha=adf770974c7ee0435702fe617634d03d17ab7cb8")
print("runtime_pass=not_claimed")
