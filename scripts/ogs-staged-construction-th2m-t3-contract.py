#!/usr/bin/env python3
from pathlib import Path

CANONICAL_SHA = "adf770974c7ee0435702fe617634d03d17ab7cb8"

required = {
    "canonical_authority": CANONICAL_SHA,
    "reactivation": "inactive -> active",
    "placement_displacement": "last-converged displacement reference",
    "placement_gas": "explicit gas-pressure placement state",
    "placement_capillary": "explicit capillary-pressure placement state",
    "placement_temperature": "explicit temperature placement state",
    "constitutive": "fresh constitutive state",
    "operator_mechanics": "mechanics",
    "operator_gas": "gas transport/storage",
    "operator_liquid": "liquid transport/storage",
    "operator_thermal": "thermal storage/conduction",
    "operator_coupling": "THM couplings",
    "constant_time": "same physical target time",
    "full_operator": "full physical operator",
    "nonzero_correction": "non-zero equilibrium correction",
    "forbid_stiffness": "No stiffness scaling",
    "forbid_residual": "residual scaling/homotopy",
    "forbid_material": "material interpolation/homotopy",
    "forbid_pseudotime": "artificial construction pseudo-time",
    "independent_evidence": "TH2M requires its own runtime evidence",
}

basis = Path("automation-evidence/th2m-t3-literature-basis.md").read_text(encoding="utf-8")
missing = [f"{name}: {needle}" for name, needle in required.items() if needle not in basis]
if missing:
    raise SystemExit("TH2M-T3 contract incomplete:\n" + "\n".join(missing))

print("TH2M-T3 loaded construction-equilibrium contract: PASS")
print(f"canonical_ogs_sha={CANONICAL_SHA}")
print("runtime_pass=false")
print("next_gate=authoritative_full_operator_runtime")
