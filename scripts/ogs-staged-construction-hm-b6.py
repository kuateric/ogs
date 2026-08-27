#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# HM-B6 — coupled material reassignment on activation.
# Literature-guided semantics:
# * PLAXIS stores material assignment per construction phase and initializes
#   state variables when a newly activated/changed soil model becomes active.
# * FLAC3D permits null/excavated zones to be assigned a new constitutive model
#   for backfill. The lifecycle therefore owns material identity; the HM local
#   assembler must re-resolve the constitutive relation before fresh-state birth.
# Staged construction remains material-law neutral: it stores only a target
# MaterialID, never an MFront behaviour name.

# 1. Add optional activation material identity to the generic deactivated-domain
# contract and parser. This mirrors the already-authoritative mechanical A3
# contract, but avoids pulling SmallDeformation-specific code into the HM gate.
h = root / "ProcessLib/DeactivatedSubdomain.h"
text = h.read_text(encoding="utf-8")
anchor = '''    DeactivatedSubdomainMesh deactivated_subdomain_mesh;\n\n    /// A pararameter for the optional Dirichlet boundary condition applied on\n'''
replacement = '''    DeactivatedSubdomainMesh deactivated_subdomain_mesh;\n\n    /// Optional target material ID assigned when this domain becomes active.\n    /// The ID is resolved through the existing OGS material authorities; the\n    /// staged-construction lifecycle remains constitutive-law neutral.\n    std::optional<int> activation_material_id;\n\n    /// A pararameter for the optional Dirichlet boundary condition applied on\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected HM-B6 DeactivatedSubdomain anchor")
h.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

cpp = root / "ProcessLib/CreateDeactivatedSubdomain.cpp"
text = cpp.read_text(encoding="utf-8")
anchor = '''    auto deactivated_subdomain_mesh = createDeactivatedSubdomainMesh(\n        mesh, deactivated_subdomain_material_ids);\n\n    return {std::move(time_interval), line_segment, ball,\n            std::move(deactivated_subdomain_mesh), boundary_value_parameter};\n'''
replacement = '''    auto deactivated_subdomain_mesh = createDeactivatedSubdomainMesh(\n        mesh, deactivated_subdomain_material_ids);\n\n    auto const activation_material_id =\n        config.getConfigParameterOptional<int>("activation_material_id");\n\n    return {std::move(time_interval), line_segment, ball,\n            std::move(deactivated_subdomain_mesh), activation_material_id,\n            boundary_value_parameter};\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected HM-B6 parser anchor")
cpp.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

# 2. Apply target MaterialIDs exactly at inactive->active transition, before HM
# B3 initializes the fresh placement state. Conflicting assignments are fatal.
pv = root / "ProcessLib/ProcessVariable.cpp"
text = pv.read_text(encoding="utf-8")
anchor = '''void ProcessVariable::updateDeactivatedSubdomains(double const time)\n{\n'''
helper = '''void ProcessVariable::updateDeactivatedSubdomains(double const time)\n{\n    auto apply_activation_material_assignments =\n        [&](StagedConstruction::DomainTransition const& transition)\n    {\n        if (transition.newly_activated_element_ids.empty())\n        {\n            return;\n        }\n\n        auto* const material_ids = materialIDs(_mesh);\n        if (material_ids == nullptr)\n        {\n            OGS_FATAL(\n                "HM activation material reassignment requires mesh MaterialIDs.");\n        }\n\n        for (auto const element_id : transition.newly_activated_element_ids)\n        {\n            std::optional<int> target_material_id;\n            for (auto const& ds : _deactivated_subdomains)\n            {\n                if (!ds.activation_material_id ||\n                    !ds.deactivated_subdomain_mesh.bulk_element_ids.contains(\n                        element_id))\n                {\n                    continue;\n                }\n                if (target_material_id &&\n                    *target_material_id != *ds.activation_material_id)\n                {\n                    OGS_FATAL(\n                        "Conflicting HM activation material IDs for element {:d}.",\n                        element_id);\n                }\n                target_material_id = ds.activation_material_id;\n            }\n\n            if (target_material_id)\n            {\n                (*material_ids)[element_id] = *target_material_id;\n                INFO("HM-B6 activation material reassigned for element {:d}: material_id={:d}",\n                     element_id, *target_material_id);\n            }\n        }\n    };\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected HM-B6 ProcessVariable function anchor")
text = text.replace(anchor, helper, 1)

anchor = '''        _last_domain_transition =\n            StagedConstruction::determineDomainTransition(previous_is_active,\n                                                          current_is_active);\n        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\n'''
replacement = '''        _last_domain_transition =\n            StagedConstruction::determineDomainTransition(previous_is_active,\n                                                          current_is_active);\n        apply_activation_material_assignments(_last_domain_transition);\n        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected HM-B6 no-support transition anchor")
text = text.replace(anchor, replacement, 1)

anchor = '''    _last_domain_transition = StagedConstruction::determineDomainTransition(\n        previous_is_active, current_is_active);\n    _ids_of_active_elements = _last_domain_transition.active_element_ids;\n'''
replacement = '''    _last_domain_transition = StagedConstruction::determineDomainTransition(\n        previous_is_active, current_is_active);\n    apply_activation_material_assignments(_last_domain_transition);\n    _ids_of_active_elements = _last_domain_transition.active_element_ids;\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected HM-B6 general transition anchor")
pv.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

# 3. HydroMechanics IntegrationPointData historically stores a permanent
# reference to the material selected when the local assembler is constructed.
# Make it rebindable. Fresh birth then selects the current MaterialID first and
# creates state variables from that material, which is essential for MFront/MGIS
# because state layouts can differ across behaviours.
fem = root / "ProcessLib/HydroMechanics/HydroMechanicsFEM.h"
text = fem.read_text(encoding="utf-8")
text = text.replace('''        : solid_material(solid_material),\n          material_state_variables(\n              solid_material.createMaterialStateVariables())\n''', '''        : solid_material(&solid_material),\n          material_state_variables(\n              solid_material.createMaterialStateVariables())\n''', 1)
text = text.replace(
    '''    MaterialLib::Solids::MechanicsBase<DisplacementDim> const& solid_material;\n''',
    '''    MaterialLib::Solids::MechanicsBase<DisplacementDim> const* solid_material;\n''', 1)
# IntegrationPointData methods must dereference the rebindable material.
text = text.replace('solid_material.createMaterialStateVariables()',
                    'solid_material->createMaterialStateVariables()')
text = text.replace('solid_material.initializeInternalStateVariables(',
                    'solid_material->initializeInternalStateVariables(')
text = text.replace('solid_material.integrateStress(',
                    'solid_material->integrateStress(')

# B3 added the birth hook. Replace it with B6 material rebinding + fresh state.
old = '''        for (auto& ip_data : _ip_data)\n        {\n            ip_data.material_state_variables =\n                ip_data.solid_material.createMaterialStateVariables();\n            ip_data.sigma_eff.setZero();\n'''
new = '''        auto const& birth_material =\n            MaterialLib::Solids::selectSolidConstitutiveRelation(\n                _process_data.solid_materials, _process_data.material_ids,\n                element_id);\n\n        for (auto& ip_data : _ip_data)\n        {\n            ip_data.solid_material = &birth_material;\n            ip_data.material_state_variables =\n                birth_material.createMaterialStateVariables();\n            ip_data.sigma_eff.setZero();\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected HM-B6 B3 birth-state anchor")
text = text.replace(old, new, 1)

old = '''        INFO("HM-B3 fresh coupled birth state initialized for element {:d}",\n             element_id);\n'''
new = '''        int const material_id = _process_data.material_ids\n                                    ? (*_process_data.material_ids)[element_id]\n                                    : 0;\n        INFO("HM-B3 fresh coupled birth state initialized for element {:d}",\n             element_id);\n        INFO("HM-B6 coupled birth material bound for element {:d}: material_id={:d}",\n             element_id, material_id);\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected HM-B6 B3 evidence anchor")
text = text.replace(old, new, 1)
fem.write_text(text, encoding="utf-8")

print("Applied HM-B6 coupled activation material reassignment runtime")
