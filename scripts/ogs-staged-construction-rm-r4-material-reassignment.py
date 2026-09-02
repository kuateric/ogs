#!/usr/bin/env python3
from pathlib import Path
import re

root = Path.cwd()

# RM-R4 — RichardsMechanics material reassignment RM_A -> void -> RM_B.
# Literature/precedent contract:
# * staged construction owns only a target MaterialID, never a constitutive-law
#   implementation or MFront behaviour name;
# * the target MaterialID is applied exactly on inactive -> active transition;
# * RM must re-resolve the constitutive relation before R2 fresh-state birth;
# * the new material starts from a fresh material state, stress-free placement
#   reference and explicit p_L0 already supplied by RM-R2B;
# * no interpolation/homotopy between RM_A and RM_B is permitted.
# This mirrors the authoritative HM-B6 lifecycle mechanism, adapted to RM's
# LocalAssemblerInterface material ownership.

# 1. Add optional activation material identity to the generic staged domain.
h = root / "ProcessLib/DeactivatedSubdomain.h"
text = h.read_text(encoding="utf-8")
anchor = '''    DeactivatedSubdomainMesh deactivated_subdomain_mesh;\n\n    /// A pararameter for the optional Dirichlet boundary condition applied on\n'''
replacement = '''    DeactivatedSubdomainMesh deactivated_subdomain_mesh;\n\n    /// Optional target material ID assigned when this domain becomes active.\n    /// The lifecycle remains constitutive-law neutral and resolves the ID via\n    /// the process material authority only at the activation event.\n    std::optional<int> activation_material_id;\n\n    /// A pararameter for the optional Dirichlet boundary condition applied on\n'''
if text.count(anchor) != 1:
    raise RuntimeError("RM-R4 DeactivatedSubdomain anchor changed")
h.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

cpp = root / "ProcessLib/CreateDeactivatedSubdomain.cpp"
text = cpp.read_text(encoding="utf-8")
anchor = '''    auto deactivated_subdomain_mesh = createDeactivatedSubdomainMesh(\n        mesh, deactivated_subdomain_material_ids);\n\n    return {std::move(time_interval), line_segment, ball,\n            std::move(deactivated_subdomain_mesh), boundary_value_parameter};\n'''
replacement = '''    auto deactivated_subdomain_mesh = createDeactivatedSubdomainMesh(\n        mesh, deactivated_subdomain_material_ids);\n\n    auto const activation_material_id =\n        config.getConfigParameterOptional<int>("activation_material_id");\n\n    return {std::move(time_interval), line_segment, ball,\n            std::move(deactivated_subdomain_mesh), activation_material_id,\n            boundary_value_parameter};\n'''
if text.count(anchor) != 1:
    raise RuntimeError("RM-R4 parser anchor changed")
cpp.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

# 2. Apply target MaterialIDs exactly at inactive -> active transition. This is
# process-variable lifecycle state, not a material-law operation. Both pressure
# and displacement may publish the same assignment; conflicting assignments are
# fatal. This is the already-proven HM-B6 ownership rule.
pv = root / "ProcessLib/ProcessVariable.cpp"
text = pv.read_text(encoding="utf-8")
anchor = '''void ProcessVariable::updateDeactivatedSubdomains(double const time)\n{\n'''
helper = '''void ProcessVariable::updateDeactivatedSubdomains(double const time)\n{\n    auto apply_activation_material_assignments =\n        [&](StagedConstruction::DomainTransition const& transition)\n    {\n        if (transition.newly_activated_element_ids.empty())\n        {\n            return;\n        }\n\n        auto* const material_ids = materialIDs(_mesh);\n        if (material_ids == nullptr)\n        {\n            OGS_FATAL(\n                "Staged-construction activation material reassignment requires mesh MaterialIDs.");\n        }\n\n        for (auto const element_id : transition.newly_activated_element_ids)\n        {\n            std::optional<int> target_material_id;\n            for (auto const& ds : _deactivated_subdomains)\n            {\n                if (!ds.activation_material_id ||\n                    !ds.deactivated_subdomain_mesh.bulk_element_ids.contains(\n                        element_id))\n                {\n                    continue;\n                }\n                if (target_material_id &&\n                    *target_material_id != *ds.activation_material_id)\n                {\n                    OGS_FATAL(\n                        "Conflicting staged-construction activation material IDs for element {:d}.",\n                        element_id);\n                }\n                target_material_id = ds.activation_material_id;\n            }\n\n            if (target_material_id)\n            {\n                auto const old_material_id = (*material_ids)[element_id];\n                (*material_ids)[element_id] = *target_material_id;\n                INFO("RM-R4 activation material reassigned for element {:d}: old_material_id={:d}, new_material_id={:d}",\n                     element_id, old_material_id, *target_material_id);\n            }\n        }\n    };\n'''
if text.count(anchor) != 1:
    raise RuntimeError("RM-R4 ProcessVariable function anchor changed")
text = text.replace(anchor, helper, 1)

anchor = '''        _last_domain_transition =\n            StagedConstruction::determineDomainTransition(previous_is_active,\n                                                          current_is_active);\n        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\n'''
replacement = '''        _last_domain_transition =\n            StagedConstruction::determineDomainTransition(previous_is_active,\n                                                          current_is_active);\n        apply_activation_material_assignments(_last_domain_transition);\n        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\n'''
if text.count(anchor) != 1:
    raise RuntimeError("RM-R4 no-support transition anchor changed")
text = text.replace(anchor, replacement, 1)

anchor = '''    _last_domain_transition = StagedConstruction::determineDomainTransition(\n        previous_is_active, current_is_active);\n    _ids_of_active_elements = _last_domain_transition.active_element_ids;\n'''
replacement = '''    _last_domain_transition = StagedConstruction::determineDomainTransition(\n        previous_is_active, current_is_active);\n    apply_activation_material_assignments(_last_domain_transition);\n    _ids_of_active_elements = _last_domain_transition.active_element_ids;\n'''
if text.count(anchor) != 1:
    raise RuntimeError("RM-R4 general transition anchor changed")
pv.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

# 3. RM historically binds the solid constitutive relation permanently in the
# local assembler constructor. Make the binding reassignable. Material state
# creation remains owned by the selected relation.
iface = root / "ProcessLib/RichardsMechanics/LocalAssemblerInterface.h"
text = iface.read_text(encoding="utf-8")
old = '''          solid_material_(MaterialLib::Solids::selectSolidConstitutiveRelation(\n              process_data_.solid_materials, process_data_.material_ids,\n              e.getID()))\n'''
new = '''          solid_material_(&MaterialLib::Solids::selectSolidConstitutiveRelation(\n              process_data_.solid_materials, process_data_.material_ids,\n              e.getID())),\n          bound_material_id_(process_data_.material_ids == nullptr\n                                 ? 0\n                                 : (*process_data_.material_ids)[e.getID()])\n'''
if text.count(old) != 1:
    raise RuntimeError("RM-R4 solid-material constructor anchor changed")
text = text.replace(old, new, 1)
text = text.replace('solid_material_.createMaterialStateVariables()',
                    'solid_material_->createMaterialStateVariables()')
text = text.replace('solid_material_.getInternalVariables()',
                    'solid_material_->getInternalVariables()')
old = '''    MaterialLib::Solids::MechanicsBase<DisplacementDim> const& solid_material_;\n'''
new = '''    MaterialLib::Solids::MechanicsBase<DisplacementDim> const* solid_material_;\n    int bound_material_id_;\n'''
if text.count(old) != 1:
    raise RuntimeError("RM-R4 solid-material member anchor changed")
iface.write_text(text.replace(old, new, 1), encoding="utf-8")

# 4. R2B's fresh-birth hook is the only legal rebind point. Resolve RM_B from
# the already-updated MaterialIDs BEFORE creating its fresh state variables.
fem = root / "ProcessLib/RichardsMechanics/RichardsMechanicsFEM.h"
text = fem.read_text(encoding="utf-8")
# R2B is applied before this patch in the authoritative workflow.
anchor = '''    void initializeActivationPlacementStateConcrete(double const t) override\n    {\n        // Fresh constitutive birth: discard trial and committed material history.\n'''
insert = '''    void initializeActivationPlacementStateConcrete(double const t) override\n    {\n        int const old_material_id = this->bound_material_id_;\n        int const new_material_id = this->process_data_.material_ids == nullptr\n                                        ? 0\n                                        : (*this->process_data_.material_ids)\n                                              [this->element_.getID()];\n        this->solid_material_ =\n            &MaterialLib::Solids::selectSolidConstitutiveRelation(\n                this->process_data_.solid_materials,\n                this->process_data_.material_ids, this->element_.getID());\n        this->bound_material_id_ = new_material_id;\n        INFO("RM-R4 constitutive material rebound for element {:d}: old_material_id={:d}, new_material_id={:d}",\n             this->element_.getID(), old_material_id, new_material_id);\n\n        // Fresh constitutive birth: discard trial and committed material history.\n'''
if text.count(anchor) != 1:
    raise RuntimeError("RM-R4 R2B fresh-birth hook anchor changed")
text = text.replace(anchor, insert, 1)
# Pointerize all RM accesses introduced by canonical code and R2B.
text = text.replace('this->solid_material_.', 'this->solid_material_->')
fem.write_text(text, encoding="utf-8")

impl = root / "ProcessLib/RichardsMechanics/RichardsMechanicsFEM-impl.h"
text = impl.read_text(encoding="utf-8")
text = text.replace('this->solid_material_.', 'this->solid_material_->')
# Canonical RM also passes the material by const reference into helper calls.
text = text.replace('this->solid_material_,', '*this->solid_material_,')
text = text.replace('this->solid_material_)', '*this->solid_material_)')
impl.write_text(text, encoding="utf-8")

# Defensive checks: no old dot-access may remain after pointerization, and no
# forbidden numerical weakening mechanism may appear in the combined patch.
joined = '\n'.join(p.read_text(encoding='utf-8') for p in
                   (h, cpp, pv, iface, fem, impl))
if 'solid_material_.' in joined:
    raise RuntimeError('RM-R4 incomplete solid-material pointer conversion')
for forbidden in ('activation_contribution_scale', 'stiffness_scale',
                  'residual_homotopy', 'material_homotopy'):
    if forbidden in joined:
        raise RuntimeError(f'RM-R4 forbidden numerical weakening mechanism detected: {forbidden}')

print('RM-R4 patch applied: lifecycle MaterialID reassignment + true constitutive rebind + R2 fresh state')
print('canonical_ogs_sha=adf770974c7ee0435702fe617634d03d17ab7cb8')
