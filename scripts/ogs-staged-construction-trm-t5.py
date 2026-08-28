#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# TRM-T5 — material reassignment at thermo-hydro-mechanical birth.
# Reuses the authoritative HM-B6 lifecycle semantics: staged construction owns
# only a target MaterialID; the TRM local assembler resolves that ID through the
# existing OGS constitutive-relation map at inactive->active transition, then
# T2 creates a fresh constitutive/MFront state from the rebound material.
# No stiffness scaling, residual homotopy, or behaviour-name coupling is added.

# 1. Generic activation material identity.
h = root / "ProcessLib/DeactivatedSubdomain.h"
text = h.read_text(encoding="utf-8")
anchor = '''    DeactivatedSubdomainMesh deactivated_subdomain_mesh;\n\n    /// A pararameter for the optional Dirichlet boundary condition applied on\n'''
replacement = '''    DeactivatedSubdomainMesh deactivated_subdomain_mesh;\n\n    /// Optional target material ID assigned when this domain becomes active.\n    /// The lifecycle remains constitutive-law neutral; process local assemblers\n    /// resolve the ID through their existing material authority.\n    std::optional<int> activation_material_id;\n\n    /// A pararameter for the optional Dirichlet boundary condition applied on\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected TRM-T5 DeactivatedSubdomain anchor")
h.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

cpp = root / "ProcessLib/CreateDeactivatedSubdomain.cpp"
text = cpp.read_text(encoding="utf-8")
anchor = '''    auto deactivated_subdomain_mesh = createDeactivatedSubdomainMesh(\n        mesh, deactivated_subdomain_material_ids);\n\n    return {std::move(time_interval), line_segment, ball,\n            std::move(deactivated_subdomain_mesh), boundary_value_parameter};\n'''
replacement = '''    auto deactivated_subdomain_mesh = createDeactivatedSubdomainMesh(\n        mesh, deactivated_subdomain_material_ids);\n\n    auto const activation_material_id =\n        config.getConfigParameterOptional<int>("activation_material_id");\n\n    return {std::move(time_interval), line_segment, ball,\n            std::move(deactivated_subdomain_mesh), activation_material_id,\n            boundary_value_parameter};\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected TRM-T5 parser anchor")
cpp.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

# 2. Apply target MaterialIDs on inactive->active transition, before the TRM
# process invokes its fresh placement-state hook.
pv = root / "ProcessLib/ProcessVariable.cpp"
text = pv.read_text(encoding="utf-8")
anchor = '''void ProcessVariable::updateDeactivatedSubdomains(double const time)\n{\n'''
helper = '''void ProcessVariable::updateDeactivatedSubdomains(double const time)\n{\n    auto apply_activation_material_assignments =\n        [&](StagedConstruction::DomainTransition const& transition)\n    {\n        if (transition.newly_activated_element_ids.empty())\n        {\n            return;\n        }\n        auto* const material_ids = materialIDs(_mesh);\n        if (material_ids == nullptr)\n        {\n            OGS_FATAL("TRM activation material reassignment requires mesh MaterialIDs.");\n        }\n        for (auto const element_id : transition.newly_activated_element_ids)\n        {\n            std::optional<int> target_material_id;\n            for (auto const& ds : _deactivated_subdomains)\n            {\n                if (!ds.activation_material_id ||\n                    !ds.deactivated_subdomain_mesh.bulk_element_ids.contains(element_id))\n                {\n                    continue;\n                }\n                if (target_material_id && *target_material_id != *ds.activation_material_id)\n                {\n                    OGS_FATAL("Conflicting TRM activation material IDs for element {:d}.",\n                              element_id);\n                }\n                target_material_id = ds.activation_material_id;\n            }\n            if (target_material_id)\n            {\n                (*material_ids)[element_id] = *target_material_id;\n                INFO("TRM-T5 activation material reassigned for element {:d}: material_id={:d}",\n                     element_id, *target_material_id);\n            }\n        }\n    };\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected TRM-T5 ProcessVariable function anchor")
text = text.replace(anchor, helper, 1)
anchor = '''        _last_domain_transition =\n            StagedConstruction::determineDomainTransition(previous_is_active,\n                                                          current_is_active);\n        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\n'''
replacement = '''        _last_domain_transition =\n            StagedConstruction::determineDomainTransition(previous_is_active,\n                                                          current_is_active);\n        apply_activation_material_assignments(_last_domain_transition);\n        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected TRM-T5 no-support transition anchor")
text = text.replace(anchor, replacement, 1)
anchor = '''    _last_domain_transition = StagedConstruction::determineDomainTransition(\n        previous_is_active, current_is_active);\n    _ids_of_active_elements = _last_domain_transition.active_element_ids;\n'''
replacement = '''    _last_domain_transition = StagedConstruction::determineDomainTransition(\n        previous_is_active, current_is_active);\n    apply_activation_material_assignments(_last_domain_transition);\n    _ids_of_active_elements = _last_domain_transition.active_element_ids;\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected TRM-T5 general transition anchor")
pv.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

# 3. Make the TRM constitutive binding reassignable. The pointer always points
# to an OGS-owned relation in process_data_.solid_materials, so lifetime remains
# unchanged. All constitutive calls continue through the same relation interface.
iface = root / "ProcessLib/ThermoRichardsMechanics/LocalAssemblerInterface.h"
text = iface.read_text(encoding="utf-8")
old = '''          solid_material_(MaterialLib::Solids::selectSolidConstitutiveRelation(\n              process_data_.solid_materials, process_data_.material_ids,\n              e.getID()))\n'''
new = '''          solid_material_(&MaterialLib::Solids::selectSolidConstitutiveRelation(\n              process_data_.solid_materials, process_data_.material_ids,\n              e.getID()))\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected TRM-T5 constructor material anchor")
text = text.replace(old, new, 1)
text = text.replace('solid_material_.', 'solid_material_->')
old = '''    typename ConstitutiveTraits::SolidConstitutiveRelation const&\n        solid_material_;\n'''
new = '''    typename ConstitutiveTraits::SolidConstitutiveRelation const*\n        solid_material_;\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected TRM-T5 material member anchor")
iface.write_text(text.replace(old, new, 1), encoding="utf-8")

# Derived TRM code uses this->solid_material_ both as an object and as an
# argument to constitutive model factories. Convert those uses mechanically to
# pointer dereference/member access after T2/T3 have been applied.
for path in [
    root / "ProcessLib/ThermoRichardsMechanics/ThermoRichardsMechanicsFEM.h",
    root / "ProcessLib/ThermoRichardsMechanics/ThermoRichardsMechanicsFEM-impl.h",
]:
    text = path.read_text(encoding="utf-8")
    text = text.replace('this->solid_material_.', 'this->solid_material_->')
    text = text.replace('this->solid_material_)', '*this->solid_material_)')
    text = text.replace('this->solid_material_,', '*this->solid_material_,')
    path.write_text(text, encoding="utf-8")

# 4. Re-resolve the current material ID before T2 creates the fresh birth state.
fem = root / "ProcessLib/ThermoRichardsMechanics/ThermoRichardsMechanicsFEM.h"
text = fem.read_text(encoding="utf-8")
anchor = '''        unsigned const n_integration_points =\n            this->integration_method_.getNumberOfPoints();\n        auto const& medium =\n'''
replacement = '''        this->solid_material_ =\n            &MaterialLib::Solids::selectSolidConstitutiveRelation(\n                this->process_data_.solid_materials,\n                this->process_data_.material_ids, element_id);\n\n        int const material_id = this->process_data_.material_ids\n                                    ? (*this->process_data_.material_ids)[element_id]\n                                    : 0;\n        INFO("TRM-T5 coupled birth material bound for element {:d}: material_id={:d}",\n             element_id, material_id);\n\n        unsigned const n_integration_points =\n            this->integration_method_.getNumberOfPoints();\n        auto const& medium =\n'''
# T2 adds this exact sequence once inside initializeActivationPlacementState;
# initializeConcrete has a similar sequence but no element_id argument nearby.
idx = text.find('void initializeActivationPlacementState')
if idx < 0:
    raise RuntimeError("TRM-T5 requires T2 fresh-birth hook")
pos = text.find(anchor, idx)
if pos < 0:
    raise RuntimeError("unexpected TRM-T5 fresh-birth material anchor")
text = text[:pos] + text[pos:].replace(anchor, replacement, 1)
fem.write_text(text, encoding="utf-8")

print("Applied TRM-T5 activation material reassignment runtime")
