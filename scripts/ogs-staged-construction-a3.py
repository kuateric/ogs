#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# 1. Extend the deactivated-subdomain contract with an optional material ID to
#    be assigned when the domain becomes active again.  The material ID remains
#    the authority for both MPL medium selection and the solid constitutive
#    relation; staged construction never stores an MFront behaviour name.
h = root / "ProcessLib/DeactivatedSubdomain.h"
text = h.read_text(encoding="utf-8")
anchor = '''    DeactivatedSubdomainMesh deactivated_subdomain_mesh;\n\n    /// A pararameter for the optional Dirichlet boundary condition applied on\n'''
replacement = '''    DeactivatedSubdomainMesh deactivated_subdomain_mesh;\n\n    /// Optional target material ID assigned to all elements of this subdomain\n    /// when they transition from inactive to active.  The target material ID\n    /// is resolved through the existing OGS material definitions; staged\n    /// construction remains independent of a particular constitutive model.\n    std::optional<int> activation_material_id;\n\n    /// A pararameter for the optional Dirichlet boundary condition applied on\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected DeactivatedSubdomain material-assignment anchor")
h.write_text(text.replace(anchor, replacement), encoding="utf-8")

cpp = root / "ProcessLib/CreateDeactivatedSubdomain.cpp"
text = cpp.read_text(encoding="utf-8")
parse_anchor = '''    auto deactivated_subdomain_mesh = createDeactivatedSubdomainMesh(\n        mesh, deactivated_subdomain_material_ids);\n\n    return {std::move(time_interval), line_segment, ball,\n            std::move(deactivated_subdomain_mesh), boundary_value_parameter};\n'''
parse_replacement = '''    auto deactivated_subdomain_mesh = createDeactivatedSubdomainMesh(\n        mesh, deactivated_subdomain_material_ids);\n\n    // Optional material identity for a later placement/backfill event.  This\n    // deliberately references the existing material-ID authority instead of a\n    // constitutive-law name, so MFront and non-MFront materials are both valid.\n    auto const activation_material_id =\n        config.getConfigParameterOptional<int>("activation_material_id");\n\n    return {std::move(time_interval), line_segment, ball,\n            std::move(deactivated_subdomain_mesh), activation_material_id,\n            boundary_value_parameter};\n'''
if text.count(parse_anchor) != 1:
    raise RuntimeError("Unexpected CreateDeactivatedSubdomain return layout")
cpp.write_text(text.replace(parse_anchor, parse_replacement), encoding="utf-8")

# 2. When an inactive element becomes active, change the authoritative mesh
#    MaterialIDs value before the owning process initializes the placement
#    state.  MaterialSpatialDistributionMap observes that same property vector.
pv = root / "ProcessLib/ProcessVariable.cpp"
text = pv.read_text(encoding="utf-8")

helper_anchor = '''void ProcessVariable::updateDeactivatedSubdomains(double const time)\n{\n'''
helper = '''void ProcessVariable::updateDeactivatedSubdomains(double const time)\n{\n    auto apply_activation_material_assignments =\n        [&](StagedConstruction::DomainTransition const& transition)\n    {\n        if (transition.newly_activated_element_ids.empty())\n        {\n            return;\n        }\n\n        auto* const material_ids = materialIDs(_mesh);\n        if (material_ids == nullptr)\n        {\n            OGS_FATAL(\n                "Activation material reassignment requires mesh MaterialIDs.");\n        }\n\n        for (auto const element_id : transition.newly_activated_element_ids)\n        {\n            std::optional<int> target_material_id;\n            for (auto const& ds : _deactivated_subdomains)\n            {\n                if (!ds.activation_material_id ||\n                    !ds.deactivated_subdomain_mesh.bulk_element_ids.contains(\n                        element_id))\n                {\n                    continue;\n                }\n                if (target_material_id &&\n                    *target_material_id != *ds.activation_material_id)\n                {\n                    OGS_FATAL(\n                        "Conflicting activation material IDs for element {:d}.",\n                        element_id);\n                }\n                target_material_id = ds.activation_material_id;\n            }\n\n            if (target_material_id)\n            {\n                (*material_ids)[element_id] = *target_material_id;\n            }\n        }\n    };\n'''
if text.count(helper_anchor) != 1:
    raise RuntimeError("Unexpected ProcessVariable update function anchor")
text = text.replace(helper_anchor, helper)

# R2G's no-support branch is the canonical backfill/reactivation path.
anchor = '''        _last_domain_transition =\n            StagedConstruction::determineDomainTransition(previous_is_active,\n                                                          current_is_active);\n        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\n'''
replacement = '''        _last_domain_transition =\n            StagedConstruction::determineDomainTransition(previous_is_active,\n                                                          current_is_active);\n        apply_activation_material_assignments(_last_domain_transition);\n        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected R2G no-support transition anchor")
text = text.replace(anchor, replacement)

# Also cover any activation transition produced by a moving deactivation curve.
anchor = '''    _last_domain_transition = StagedConstruction::determineDomainTransition(\n        previous_is_active, current_is_active);\n    _ids_of_active_elements = _last_domain_transition.active_element_ids;\n'''
replacement = '''    _last_domain_transition = StagedConstruction::determineDomainTransition(\n        previous_is_active, current_is_active);\n    apply_activation_material_assignments(_last_domain_transition);\n    _ids_of_active_elements = _last_domain_transition.active_element_ids;\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected R2G general transition anchor")
pv.write_text(text.replace(anchor, replacement), encoding="utf-8")

# 3. A local assembler was historically bound forever to the material selected
#    at construction.  Make the binding re-selectable and rebind it immediately
#    before A1 creates the fresh activation state.
la = root / "ProcessLib/SmallDeformation/LocalAssemblerInterface.h"
text = la.read_text(encoding="utf-8")
old = '''          solid_material_(MaterialLib::Solids::selectSolidConstitutiveRelation(\n              process_data_.solid_materials, process_data_.material_ids,\n              element_.getID()))\n'''
new = '''          solid_material_(&MaterialLib::Solids::selectSolidConstitutiveRelation(\n              process_data_.solid_materials, process_data_.material_ids,\n              element_.getID()))\n'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected LocalAssembler solid-material constructor binding")
text = text.replace(old, new)
text = text.replace("solid_material_.", "solid_material_->")

old_method = '''    void initializeActivationPlacementState(std::size_t const /*element_id*/)\n    {\n        for (std::size_t ip = 0; ip < material_states_.size(); ++ip)\n'''
new_method = '''    void initializeActivationPlacementState(std::size_t const element_id)\n    {\n        // MaterialIDs may have been reassigned by the lifecycle immediately\n        // before this hook. Re-resolve the constitutive relation first, then\n        // create a completely fresh state from the new material.\n        solid_material_ = &MaterialLib::Solids::selectSolidConstitutiveRelation(\n            process_data_.solid_materials, process_data_.material_ids,\n            element_id);\n\n        for (std::size_t ip = 0; ip < material_states_.size(); ++ip)\n'''
if text.count(old_method) != 1:
    raise RuntimeError("Unexpected A1 activation initialization method")
text = text.replace(old_method, new_method)

old_member = '''    MaterialLib::Solids::MechanicsBase<DisplacementDim> const& solid_material_;\n'''
new_member = '''    MaterialLib::Solids::MechanicsBase<DisplacementDim> const* solid_material_;\n'''
if text.count(old_member) != 1:
    raise RuntimeError("Unexpected LocalAssembler solid-material member")
la.write_text(text.replace(old_member, new_member), encoding="utf-8")

# SmallDeformationFEM uses the material relation directly. Adapt those call
# sites to the rebindable pointer while retaining const material semantics.
fem = root / "ProcessLib/SmallDeformation/SmallDeformationFEM.h"
text = fem.read_text(encoding="utf-8")
text = text.replace("this->solid_material_.initializeInternalStateVariables(",
                    "this->solid_material_->initializeInternalStateVariables(")
text = text.replace("this->process_data_, this->solid_material_);",
                    "this->process_data_, *this->solid_material_);")
fem.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction A3 activation material reassignment runtime")
