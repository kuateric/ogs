#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = cpp.read_text(encoding="utf-8")

anchor = '''    AssemblyMixin<SmallDeformationProcess<DisplacementDim>>::
        assembleWithJacobian(t, dt, x, x_prev, process_id, b, Jac);
}
'''
replacement = '''    AssemblyMixin<SmallDeformationProcess<DisplacementDim>>::
        assembleWithJacobian(t, dt, x, x_prev, process_id, b, Jac);

    // R2K: retain the full pre-removal nodal action after the removed elements
    // have disappeared from the active assembly.  MechanicalRemovalTransition
    // stores the exact local residual contribution captured from the last
    // accepted FE state, restricted to DOFs shared with the remaining domain.
    // At lambda = 0 the full action is retained.  The force is external and
    // independent of the current Newton iterate, hence no Jacobian contribution
    // is added.  A later gate will replace the fixed lambda with an adaptive
    // construction-continuation controller and clear the transition at
    // lambda = 1.
    if (staged_construction_pending_removal_transition_)
    {
        auto const& transition =
            *staged_construction_pending_removal_transition_;
        auto const& dof_ids = transition.dofIDs();
        std::vector<GlobalIndexType> global_indices(dof_ids.begin(),
                                                    dof_ids.end());
        b.add(global_indices, transition.forceAt(0.0));
    }
}
'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformationProcess assembleWithJacobian layout")
text = text.replace(anchor, replacement)
cpp.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction R2K retained-force RHS injection")
