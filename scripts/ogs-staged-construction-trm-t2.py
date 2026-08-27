#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# TRM-T2 — fresh thermo-hydro-mechanical birth state.
# Literature-guided semantics inherited from A4L/HM-B3:
# newly activated material is born in the current configuration with a fresh
# constitutive history. Explicit absolute p_L,0 and T_0 placement are deferred
# to T3; this gate only proves that stale pre-void solid/MFront history is not
# reused.

iface = root / "ProcessLib/ThermoRichardsMechanics/LocalAssemblerInterface.h"
text = iface.read_text(encoding="utf-8")
anchor = '''    void postTimestepConcrete(Eigen::VectorXd const& /*local_x*/,\n'''
method = '''    virtual void initializeActivationPlacementState(\n        std::size_t element_id, double t) = 0;\n\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected TRM LocalAssemblerInterface postTimestep anchor")
iface.write_text(text.replace(anchor, method + anchor, 1), encoding="utf-8")

fem = root / "ProcessLib/ThermoRichardsMechanics/ThermoRichardsMechanicsFEM.h"
text = fem.read_text(encoding="utf-8")
anchor = '''    void initializeConcrete() override\n    {\n'''
method = '''    void initializeActivationPlacementState(\n        std::size_t const element_id, double const t) override\n    {\n        if (element_id != this->element_.getID())\n        {\n            OGS_FATAL("TRM-T2 activation element id mismatch.");\n        }\n\n        unsigned const n_integration_points =\n            this->integration_method_.getNumberOfPoints();\n        auto const& medium =\n            *this->process_data_.media_map.getMedium(this->element_.getID());\n\n        for (unsigned ip = 0; ip < n_integration_points; ++ip)\n        {\n            auto& current_state = this->current_states_[ip];\n            auto& prev_state = this->prev_states_[ip];\n\n            ConstitutiveTraits::ConstitutiveSetting::statefulStress(\n                current_state) = KelvinVectorType::Zero();\n            std::get<StrainData<DisplacementDim>>(current_state).eps =\n                KelvinVectorType::Zero();\n            prev_state = current_state;\n\n            this->material_states_[ip] = MaterialStateData<DisplacementDim>(\n                this->solid_material_.createMaterialStateVariables());\n\n            ParameterLib::SpatialPosition const x_position{\n                std::nullopt, this->element_.getID(),\n                MathLib::Point3d(NumLib::interpolateCoordinates<\n                    ShapeFunctionDisplacement,\n                    ShapeMatricesTypeDisplacement>(\n                    this->element_, this->ip_data_[ip].N_u))};\n            this->solid_material_.initializeInternalStateVariables(\n                t, x_position,\n                *this->material_states_[ip].material_state_variables);\n            this->material_states_[ip].pushBackState();\n        }\n\n        INFO("TRM-T2 fresh coupled birth state initialized for element {:d}",\n             element_id);\n    }\n\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected TRM FEM initializeConcrete anchor")
fem.write_text(text.replace(anchor, method + anchor, 1), encoding="utf-8")

cpp = root / "ProcessLib/ThermoRichardsMechanics/ThermoRichardsMechanicsProcess.cpp"
text = cpp.read_text(encoding="utf-8")
anchor = '''    AssemblyMixin<ThermoRichardsMechanicsProcess<\n        DisplacementDim, ConstitutiveTraits>>::updateActiveElements();\n}\n'''
replacement = '''    AssemblyMixin<ThermoRichardsMechanicsProcess<\n        DisplacementDim, ConstitutiveTraits>>::updateActiveElements();\n\n    auto const& variables = getProcessVariables(0);\n    if (variables.size() != 3)\n    {\n        OGS_FATAL("TRM staged construction expects T/p_L/u monolithic variables.");\n    }\n\n    auto const& temperature_transition =\n        variables[0].get().getLastDomainTransition();\n    auto const& pressure_transition =\n        variables[1].get().getLastDomainTransition();\n    auto const& displacement_transition =\n        variables[2].get().getLastDomainTransition();\n\n    if (temperature_transition.newly_activated_element_ids !=\n            pressure_transition.newly_activated_element_ids ||\n        temperature_transition.newly_activated_element_ids !=\n            displacement_transition.newly_activated_element_ids)\n    {\n        OGS_FATAL(\n            "TRM staged construction requires synchronized temperature, "\n            "pressure and displacement activation domains.");\n    }\n\n    if (!temperature_transition.newly_activated_element_ids.empty())\n    {\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &LocalAssemblerIF::initializeActivationPlacementState,\n            local_assemblers_,\n            temperature_transition.newly_activated_element_ids, t);\n    }\n}\n'''
# The canonical signature currently comments t out; make it available first.
sig_old = '''    preTimestepConcreteProcess(std::vector<GlobalVector*> const& /*x*/,\n                               const double /*t*/,\n                               const double /*dt*/,\n                               const int /*process_id*/)\n'''
sig_new = '''    preTimestepConcreteProcess(std::vector<GlobalVector*> const& /*x*/,\n                               const double t,\n                               const double /*dt*/,\n                               const int /*process_id*/)\n'''
if text.count(sig_old) != 1:
    raise RuntimeError("unexpected TRM preTimestep signature")
text = text.replace(sig_old, sig_new, 1)
if text.count(anchor) != 1:
    raise RuntimeError("unexpected TRM active-element update anchor")
cpp.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

print("Applied TRM-T2 fresh coupled birth-state hook")
