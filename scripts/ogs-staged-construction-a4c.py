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

# Insert placement-reference reset into initializeActivationPlacementState()
# itself. A4B inserts activationContributionScale() between that function and
# the next historical comment, so using the comment as the end anchor would
# accidentally mutate the const scale getter.
method_start = "    void initializeActivationPlacementState(std::size_t const element_id)\n    {\n"
if text.count(method_start) != 1:
    raise RuntimeError("Unexpected A3 activation placement-state method layout")
start = text.index(method_start)
brace_start = text.index("{", start)
depth = 0
end_brace = None
for i in range(brace_start, len(text)):
    if text[i] == "{":
        depth += 1
    elif text[i] == "}":
        depth -= 1
        if depth == 0:
            end_brace = i
            break
if end_brace is None:
    raise RuntimeError("Could not locate activation placement-state method end")
# end_brace points at the closing brace itself, while the four indentation
# spaces preceding it are already part of text[:end_brace]. Start the inserted
# text with four additional spaces and end with four spaces so no whitespace-
# only line is generated in the resulting C++ patch.
insert = "    activation_reference_displacement_.resize(0);\n        activation_reference_pending_ = true;\n    "
text = text[:end_brace] + insert + text[end_brace:]

# Add placement-reference helpers immediately before the already existing A4B
# scale setter. They intentionally mutate state only in non-const methods.
scale_setter = "    void setActivationContributionScale(std::size_t const /*element_id*/,\n"
if text.count(scale_setter) != 1:
    raise RuntimeError("Unexpected A4B scale-setter anchor")
helpers = '''    void captureActivationReferenceDisplacement(\n        Eigen::Ref<Eigen::VectorXd const> const u)\n    {\n        if (!activation_reference_pending_)\n        {\n            return;\n        }\n        activation_reference_displacement_ = u;\n        activation_reference_pending_ = false;\n    }\n\n    Eigen::VectorXd activationRelativeDisplacement(\n        Eigen::Ref<Eigen::VectorXd const> const u) const\n    {\n        if (activation_reference_displacement_.size() == 0)\n        {\n            return u;\n        }\n        if (activation_reference_displacement_.size() != u.size())\n        {\n            OGS_FATAL(\n                "Activation placement reference size does not match local "\n                "displacement size.");\n        }\n        return u - activation_reference_displacement_;\n    }\n\n'''
text = text.replace(scale_setter, helpers + scale_setter)

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
