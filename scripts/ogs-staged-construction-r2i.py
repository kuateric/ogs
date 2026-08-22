#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

header = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.h"
text = header.read_text(encoding="utf-8")

if '#include <unordered_map>\n' not in text:
    text = text.replace('#pragma once\n\n', '#pragma once\n\n#include <unordered_map>\n#include <vector>\n\n')

member_anchor = '''    std::vector<std::unique_ptr<LocalAssemblerInterface>> local_assemblers_;

    MeshLib::PropertyVector<double>* material_forces_ = nullptr;
'''
member_replacement = '''    std::vector<std::unique_ptr<LocalAssemblerInterface>> local_assemblers_;

    // Element-local residuals are copied from the regular assembly path.  The
    // trial cache may be overwritten by nonlinear iterations.  It becomes the
    // authoritative pre-removal state only after an accepted timestep, when it
    // is promoted to the committed cache in postTimestepConcreteProcess().
    std::unordered_map<std::size_t, std::vector<double>>
        staged_construction_trial_element_residuals_;
    std::unordered_map<std::size_t, std::vector<double>>
        staged_construction_committed_element_residuals_;

    MeshLib::PropertyVector<double>* material_forces_ = nullptr;
'''
if member_anchor not in text:
    raise RuntimeError("Unexpected SmallDeformationProcess.h member layout")
text = text.replace(member_anchor, member_replacement)
header.write_text(text, encoding="utf-8")

cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = cpp.read_text(encoding="utf-8")

initialize_anchor = '''    GlobalExecutor::executeMemberOnDereferenced(
        &LocalAssemblerInterface::initialize, local_assemblers_,
        *_local_to_global_index_map);
}
'''
initialize_replacement = '''    GlobalExecutor::executeMemberOnDereferenced(
        &LocalAssemblerInterface::initialize, local_assemblers_,
        *_local_to_global_index_map);

    // Observe the exact local residual produced by the normal OGS assembly.
    // Only copy data here: no constitutive integration and no material-state
    // mutation is performed by staged construction.
    this->setLocalResidualObserver(
        [this](std::size_t const element_id,
               std::vector<double> const& local_residual)
        {
            staged_construction_trial_element_residuals_[element_id] =
                local_residual;
        });
}
'''
if text.count(initialize_anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformationProcess initialize tail")
text = text.replace(initialize_anchor, initialize_replacement)

post_anchor = '''    GlobalExecutor::executeSelectedMemberOnDereferenced(
        &LocalAssemblerInterface::postTimestep, local_assemblers_,
        getActiveElementIDs(), dof_tables, x, x_prev, t, dt, process_id);

    std::unique_ptr<GlobalVector> material_forces;
'''
post_replacement = '''    GlobalExecutor::executeSelectedMemberOnDereferenced(
        &LocalAssemblerInterface::postTimestep, local_assemblers_,
        getActiveElementIDs(), dof_tables, x, x_prev, t, dt, process_id);

    // postTimestepConcreteProcess() is reached only for an accepted timestep.
    // Promote the latest assembled residuals atomically at this acceptance
    // boundary.  Failed nonlinear attempts therefore never overwrite the
    // committed pre-removal cache used by later construction events.
    staged_construction_committed_element_residuals_ =
        staged_construction_trial_element_residuals_;
    staged_construction_trial_element_residuals_.clear();

    std::unique_ptr<GlobalVector> material_forces;
'''
if text.count(post_anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformationProcess postTimestep layout")
text = text.replace(post_anchor, post_replacement)
cpp.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction R2I committed residual caching")
