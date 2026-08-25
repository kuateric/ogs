#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4C: a newly placed material must be stress/strain free in the configuration
# in which it is born. Fresh MFront history alone is not sufficient when the
# host mesh already carries non-zero displacement: using B*u directly would
# feed the old host deformation into the new material as an instantaneous
# strain jump. Store the nodal displacement at first assembly after activation
# and evaluate the placed material with displacement relative to that reference.

la = root / "ProcessLib/SmallDeformation/LocalAssemblerInterface.h"
text = la.read_text(encoding="utf-8")

# A3 extends A1 by rebinding the constitutive relation before creating the fresh
# state. Preserve that exact method body and only append the placement-reference
# initialization before the method returns. This avoids coupling A4C to the
# historical A1-only method spelling.
method_start = "    void initializeActivationPlacementState(std::size_t const element_id)\n    {\n"
commit_anchor = "    // Commit the already converged constitutive trial state as the baseline for\n"
if text.count(method_start) != 1 or text.count(commit_anchor) != 1:
    raise RuntimeError("Unexpected A3 activation placement-state method layout")
start = text.index(method_start)
end = text.index(commit_anchor, start)
method = text[start:end]
method_tail = "    }\n\n"
if not method.endswith(method_tail):
    raise RuntimeError("Unexpected A3 activation placement-state method tail")
method = method[:-len(method_tail)] + '''\n        activation_reference_displacement_.resize(0);\n        activation_reference_pending_ = true;\n    }\n\n    void captureActivationReferenceDisplacement(\n        Eigen::Ref<Eigen::VectorXd const> const u)\n    {\n        if (!activation_reference_pending_)\n        {\n            return;\n        }\n        activation_reference_displacement_ = u;\n        activation_reference_pending_ = false;\n    }\n\n    Eigen::VectorXd activationRelativeDisplacement(\n        Eigen::Ref<Eigen::VectorXd const> const u) const\n    {\n        if (activation_reference_displacement_.size() == 0)\n        {\n            return u;\n        }\n        if (activation_reference_displacement_.size() != u.size())\n        {\n            OGS_FATAL(\n                "Activation placement reference size does not match local "\n                "displacement size.");\n        }\n        return u - activation_reference_displacement_;\n    }\n\n'''
text = text[:start] + method + text[end:]

member_anchor = '''protected:\n    double activation_contribution_scale_ = 1.0;\n\n    SmallDeformationProcessData<DisplacementDim>& process_data_;\n'''
member_replacement = '''protected:\n    double activation_contribution_scale_ = 1.0;\n    bool activation_reference_pending_ = false;\n    Eigen::VectorXd activation_reference_displacement_;\n\n    SmallDeformationProcessData<DisplacementDim>& process_data_;\n'''
if text.count(member_anchor) != 1:
    raise RuntimeError("Unexpected A4B activation member anchor")
la.write_text(text.replace(member_anchor, member_replacement), encoding="utf-8")

fem = root / "ProcessLib/SmallDeformation/SmallDeformationFEM.h"
text = fem.read_text(encoding="utf-8")

# The first assembly after activation owns the exact placement configuration.
# Capture it before any MFront integration and use relative displacements for
# both current and previous constitutive strain arguments.
old = '''        auto [u] = localDOF(local_x);\n        auto [u_prev] = localDOF(local_x_prev);\n\n        unsigned const n_integration_points =\n'''
new = '''        auto [u] = localDOF(local_x);\n        auto [u_prev] = localDOF(local_x_prev);\n\n        this->captureActivationReferenceDisplacement(u);\n        Eigen::VectorXd const u_constitutive =\n            this->activationRelativeDisplacement(u);\n        Eigen::VectorXd const u_prev_constitutive =\n            this->activationRelativeDisplacement(u_prev);\n\n        unsigned const n_integration_points =\n'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected SmallDeformation assemble local-DOF anchor")
text = text.replace(old, new)

old = '''            auto const CD = updateConstitutiveRelations(\n                B, u, u_prev, x_position, t, dt, constitutive_setting, medium,\n'''
new = '''            auto const CD = updateConstitutiveRelations(\n                B, u_constitutive, u_prev_constitutive, x_position, t, dt,\n                constitutive_setting, medium,\n'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected SmallDeformation constitutive assembly call")
text = text.replace(old, new)

# Commit the same placement-relative kinematics in postTimestep. The placement
# reference is fixed once captured; trial rollback changes constitutive state,
# not the geometric birth configuration.
old = '''    void postTimestepConcrete(Eigen::VectorXd const& local_x,\n                              Eigen::VectorXd const& local_x_prev,\n                              double const t, double const dt,\n                              int const /*process_id*/) override\n    {\n        unsigned const n_integration_points =\n'''
new = '''    void postTimestepConcrete(Eigen::VectorXd const& local_x,\n                              Eigen::VectorXd const& local_x_prev,\n                              double const t, double const dt,\n                              int const /*process_id*/) override\n    {\n        Eigen::VectorXd const local_x_constitutive =\n            this->activationRelativeDisplacement(local_x);\n        Eigen::VectorXd const local_x_prev_constitutive =\n            this->activationRelativeDisplacement(local_x_prev);\n\n        unsigned const n_integration_points =\n'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected SmallDeformation postTimestep anchor")
text = text.replace(old, new)

old = '''            updateConstitutiveRelations(\n                B, local_x, local_x_prev, x_position, t, dt,\n                constitutive_setting, medium, this->current_states_[ip],\n'''
new = '''            updateConstitutiveRelations(\n                B, local_x_constitutive, local_x_prev_constitutive, x_position,\n                t, dt, constitutive_setting, medium, this->current_states_[ip],\n'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected SmallDeformation postTimestep constitutive call")
fem.write_text(text.replace(old, new), encoding="utf-8")

print("Applied OGS Staged Construction A4C placement-reference kinematics")
