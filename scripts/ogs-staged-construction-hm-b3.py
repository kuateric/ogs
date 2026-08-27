#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# HM-B3 — fresh coupled birth state.
# Literature-guided semantics:
# * PLAXIS staged construction: reactivated soil is born stress-free in the
#   current configuration and the construction imbalance is solved afterwards.
# * Abaqus element activation: full activation uses the current configuration
#   as the stress-free reference; material state starts from the activation
#   state, not from a previous inactive life.
# This gate introduces the HM lifecycle hook only. Explicit p_L placement and
# cross-material rebinding are subsequent gates.

la = root / "ProcessLib/HydroMechanics/LocalAssemblerInterface.h"
text = la.read_text(encoding="utf-8")
anchor = '''    virtual std::vector<double> getSigma() const = 0;\n'''
method = '''    // Reset a newly activated HM element to a fresh constitutive state.\n    // The element id is supplied by GlobalExecutor for deterministic evidence.\n    virtual void initializeActivationPlacementState(\n        std::size_t element_id) = 0;\n\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected HM LocalAssemblerInterface anchor")
la.write_text(text.replace(anchor, method + anchor, 1), encoding="utf-8")

fem = root / "ProcessLib/HydroMechanics/HydroMechanicsFEM.h"
text = fem.read_text(encoding="utf-8")
anchor = '''    void postTimestepConcrete(Eigen::VectorXd const& local_x,\n                              Eigen::VectorXd const& local_x_prev,\n                              double const t, double const dt,\n                              int const process_id) override;\n'''
method = '''    void initializeActivationPlacementState(\n        std::size_t const element_id) override\n    {\n        if (element_id != _element.getID())\n        {\n            OGS_FATAL("HM-B3 activation element id mismatch.");\n        }\n\n        for (auto& ip_data : _ip_data)\n        {\n            ip_data.material_state_variables =\n                ip_data.solid_material.createMaterialStateVariables();\n            ip_data.sigma_eff.setZero();\n            ip_data.sigma_eff_prev.setZero();\n            ip_data.eps.setZero();\n            ip_data.eps_prev.setZero();\n            ip_data.strain_rate_variable = 0.0;\n        }\n\n        INFO("HM-B3 fresh coupled birth state initialized for element {:d}",\n             element_id);\n    }\n\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected HM FEM postTimestep anchor")
fem.write_text(text.replace(anchor, method + anchor, 1), encoding="utf-8")

cpp = root / "ProcessLib/HydroMechanics/HydroMechanicsProcess.cpp"
text = cpp.read_text(encoding="utf-8")
anchor = '''    if (hasMechanicalProcess(process_id))\n    {\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &LocalAssemblerIF::preTimestep, local_assemblers_,\n'''
replacement = '''    if (hasMechanicalProcess(process_id))\n    {\n        auto const& variables = getProcessVariables(process_id);\n        if (variables.size() >= 2)\n        {\n            auto const& pressure_transition =\n                variables[0].get().getLastDomainTransition();\n            auto const& displacement_transition =\n                variables[1].get().getLastDomainTransition();\n\n            if (pressure_transition.newly_activated_element_ids !=\n                displacement_transition.newly_activated_element_ids)\n            {\n                OGS_FATAL(\n                    "HM staged construction requires synchronized pressure "\n                    "and displacement activation domains.");\n            }\n\n            if (!pressure_transition.newly_activated_element_ids.empty())\n            {\n                GlobalExecutor::executeSelectedMemberOnDereferenced(\n                    &LocalAssemblerIF::initializeActivationPlacementState,\n                    local_assemblers_,\n                    pressure_transition.newly_activated_element_ids);\n            }\n        }\n\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &LocalAssemblerIF::preTimestep, local_assemblers_,\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected HM preTimestep lifecycle anchor")
cpp.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

print("Applied HM-B3 fresh coupled birth-state hook")
