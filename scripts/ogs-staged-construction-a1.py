#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

la_h = root / "ProcessLib/SmallDeformation/LocalAssemblerInterface.h"
text = la_h.read_text(encoding="utf-8")
anchor = '''    // Commit the already converged constitutive trial state as the baseline for\n'''
method = '''    // Initialize a newly activated/placed element from a genuinely fresh\n    // constitutive state. This deliberately discards any stale material history\n    // left from an earlier active life of the same mesh element. Primary\n    // variables remain process-owned and are not modified here.\n    void initializeActivationPlacementState(std::size_t const /*element_id*/)\n    {\n        for (std::size_t ip = 0; ip < material_states_.size(); ++ip)\n        {\n            material_states_[ip] = MaterialStateData<DisplacementDim>{\n                solid_material_.createMaterialStateVariables()};\n\n            current_states_[ip] = {};\n            std::get<StressData<DisplacementDim>>(current_states_[ip])\n                .sigma.noalias() = MathLib::KelvinVector::KelvinVectorType<\n                DisplacementDim>::Zero();\n            prev_states_[ip] = current_states_[ip];\n            output_data_[ip] = {};\n        }\n    }\n\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected R3E local-assembler commit anchor")
text = text.replace(anchor, method + anchor)
la_h.write_text(text, encoding="utf-8")

cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = cpp.read_text(encoding="utf-8")
anchor = '''    auto const& domain_transition =\n        getProcessVariables(process_id)[0].get().getLastDomainTransition();\n    if (!domain_transition.newly_deactivated_element_ids.empty())\n'''
replacement = '''    auto const& domain_transition =\n        getProcessVariables(process_id)[0].get().getLastDomainTransition();\n\n    // Activation/backfill is a placement event, not an undo of excavation.\n    // Reset only the newly activated elements before their first preTimestep()\n    // call so no stale plastic/MFront history can leak into the new material.\n    if (!domain_transition.newly_activated_element_ids.empty())\n    {\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &LocalAssemblerInterface::initializeActivationPlacementState,\n            local_assemblers_, domain_transition.newly_activated_element_ids);\n    }\n\n    if (!domain_transition.newly_deactivated_element_ids.empty())\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected R2J lifecycle transition anchor")
text = text.replace(anchor, replacement)
cpp.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction A1 fresh activation constitutive-state initialization")

# CI touch: force the registered A1 workflow to execute the embedded A2 full-backfill gate.
# A2 execution trigger: activation/backfill full-horizon MFront regression.
