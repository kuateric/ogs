#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4H: A4G proved that newborn backfill elements have zero residual at the
# placement configuration while the global Newton solve still takes a large,
# lambda-invariant first correction. Instrument the surviving mechanical-removal
# transition to determine whether an old retained excavation force is being
# reintroduced when the later activation continuation resets the construction
# coordinate.
cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = cpp.read_text(encoding="utf-8")
old = '''    if (staged_construction_pending_removal_transition_)\n    {\n        auto const& transition =\n            *staged_construction_pending_removal_transition_;\n        auto const& dof_ids = transition.dofIDs();\n        std::vector<GlobalIndexType> global_indices(dof_ids.begin(),\n                                                    dof_ids.end());\n        b.add(global_indices, transition.currentForce());\n    }\n'''
new = '''    if (staged_construction_pending_removal_transition_)\n    {\n        auto const& transition =\n            *staged_construction_pending_removal_transition_;\n        auto const& dof_ids = transition.dofIDs();\n        auto const current_force = transition.currentForce();\n        double retained_force_sq_norm = 0.0;\n        for (double const f : current_force)\n        {\n            retained_force_sq_norm += f * f;\n        }\n        INFO(\n            "A4H retained removal state: release_lambda={:g}, fully_released={}, "\n            "dof_count={:d}, force_sq_norm={:g}",\n            transition.releaseCoordinate(), transition.isFullyReleased(),\n            dof_ids.size(), retained_force_sq_norm);\n        std::vector<GlobalIndexType> global_indices(dof_ids.begin(),\n                                                    dof_ids.end());\n        b.add(global_indices, current_force);\n    }\n'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected retained-force RHS injection layout")
cpp.write_text(text.replace(old, new), encoding="utf-8")

print("Applied OGS Staged Construction A4H retained-force lifecycle diagnostics")
