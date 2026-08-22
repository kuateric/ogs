#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

header = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.h"
text = header.read_text(encoding="utf-8")

if '#include <optional>\n' not in text:
    text = text.replace('#include <unordered_map>\n', '#include <optional>\n#include <unordered_map>\n')

include_anchor = '#include "ProcessLib/Process.h"\n'
includes = '''#include "ProcessLib/Process.h"\n#include "ProcessLib/StagedConstruction/MechanicalRemovalDofTableAdapter.h"\n#include "ProcessLib/StagedConstruction/MechanicalRemovalEventBridge.h"\n'''
if 'MechanicalRemovalEventBridge.h' not in text:
    if text.count(include_anchor) != 1:
        raise RuntimeError("Unexpected SmallDeformationProcess.h include layout")
    text = text.replace(include_anchor, includes)

member_anchor = '''    std::unordered_map<std::size_t, std::vector<double>>
        staged_construction_committed_element_residuals_;

    MeshLib::PropertyVector<double>* material_forces_ = nullptr;
'''
member_replacement = '''    std::unordered_map<std::size_t, std::vector<double>>
        staged_construction_committed_element_residuals_;

    // Prepared exclusively from the last accepted (committed) FE residuals.
    // R2J only constructs and stores the transition; it does not yet inject the
    // retained force into the global RHS, so this gate is behavior-neutral.
    std::optional<StagedConstruction::MechanicalRemovalTransition>
        staged_construction_pending_removal_transition_;

    MeshLib::PropertyVector<double>* material_forces_ = nullptr;
'''
if member_anchor not in text:
    raise RuntimeError("Unexpected SmallDeformationProcess.h R2I member layout")
text = text.replace(member_anchor, member_replacement)
header.write_text(text, encoding="utf-8")

cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = cpp.read_text(encoding="utf-8")

anchor = '''    DBUG("PreTimestep SmallDeformationProcess.");

    GlobalExecutor::executeSelectedMemberOnDereferenced(
'''
replacement = '''    DBUG("PreTimestep SmallDeformationProcess.");

    // updateDeactivatedSubdomains() has already computed the lifecycle change
    // for this timestep.  Build the equilibrium-preserving removal transition
    // only from the residual cache committed at the previous accepted timestep.
    // This avoids any additional constitutive integration and makes failed
    // nonlinear attempts unable to contaminate the pre-removal force state.
    auto const& domain_transition =
        getProcessVariables(process_id)[0].get().getLastDomainTransition();
    if (!domain_transition.newly_deactivated_element_ids.empty())
    {
        std::unordered_map<
            std::size_t,
            StagedConstruction::MechanicalRemovalElementContribution>
            removed_element_contributions;
        removed_element_contributions.reserve(
            domain_transition.newly_deactivated_element_ids.size());

        for (auto const element_id :
             domain_transition.newly_deactivated_element_ids)
        {
            auto const residual_it =
                staged_construction_committed_element_residuals_.find(
                    element_id);
            if (residual_it ==
                staged_construction_committed_element_residuals_.end())
            {
                OGS_FATAL(
                    "Staged construction cannot remove element {:d}: no "
                    "committed pre-removal residual is available.",
                    element_id);
            }

            removed_element_contributions.emplace(
                element_id,
                StagedConstruction::MechanicalRemovalElementContribution{
                    StagedConstruction::getOwnedElementDofIDs(
                        element_id, *_local_to_global_index_map),
                    residual_it->second});
        }

        auto const remaining_active_element_dofs =
            StagedConstruction::getOwnedElementDofIDs(
                domain_transition.active_element_ids,
                *_local_to_global_index_map);

        staged_construction_pending_removal_transition_ =
            StagedConstruction::buildMechanicalRemovalFromDomainTransition(
                domain_transition, removed_element_contributions,
                remaining_active_element_dofs);
    }

    GlobalExecutor::executeSelectedMemberOnDereferenced(
'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformationProcess preTimestep layout")
text = text.replace(anchor, replacement)
cpp.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction R2J committed-state removal transition wiring")
