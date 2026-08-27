#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# HM-B4 — explicit coupled placement state.
# Literature-guided semantics:
# * mechanical birth uses the current deformed configuration as stress-free
#   reference (Abaqus/PLAXIS element activation semantics),
# * liquid pressure is an absolute primary variable. Newly activated pressure
#   DOFs are initialized from the pressure ProcessVariable initial-condition
#   parameter before the first coupled assembly; p_L is never converted into a
#   relative/reference-pressure variable.
# B3 must already have installed the fresh constitutive-state hook.

# First publish the explicit hydraulic placement state into the newborn global
# pressure DOFs. This must happen before the local assemblers capture their
# placement state, otherwise they merely sample the old solved field.
cpp = root / "ProcessLib/HydroMechanics/HydroMechanicsProcess.cpp"
text = cpp.read_text(encoding="utf-8")
old = '''            if (!pressure_transition.newly_activated_element_ids.empty())\n            {\n                GlobalExecutor::executeSelectedMemberOnDereferenced(\n                    &LocalAssemblerIF::initializeActivationPlacementState,\n                    local_assemblers_,\n                    pressure_transition.newly_activated_element_ids);\n            }\n'''
new = '''            if (!pressure_transition.newly_activated_element_ids.empty())\n            {\n                // HM-B4: p_L is an absolute placement state. Publish the\n                // configured pressure initial condition to the newborn\n                // pressure DOFs before the first coupled assembly. Repeated\n                // writes at shared newborn nodes are deterministic because the\n                // same ProcessVariable placement parameter is evaluated.\n                auto const& pressure_initial_condition =\n                    variables[0].get().getInitialCondition();\n                auto& mesh = getMesh();\n                auto& solution = *x[process_id];\n\n                for (auto const element_id :\n                     pressure_transition.newly_activated_element_ids)\n                {\n                    auto const* element = mesh.getElement(element_id);\n                    auto const number_of_pressure_nodes =\n                        element->getNumberOfBaseNodes();\n                    for (unsigned node_id = 0;\n                         node_id < number_of_pressure_nodes; ++node_id)\n                    {\n                        auto const* node = element->getNode(node_id);\n                        ParameterLib::SpatialPosition const position{\n                            node->getID(), element_id, *node};\n                        auto const values = pressure_initial_condition(t, position);\n                        if (values.size() != 1)\n                        {\n                            OGS_FATAL(\n                                "HM-B4 pressure placement state must be scalar.");\n                        }\n\n                        auto const global_index =\n                            _local_to_global_index_map->getGlobalIndex(\n                                MeshLib::Location{\n                                    mesh.getID(), MeshLib::MeshItemType::Node,\n                                    node->getID()},\n                                0, 0);\n                        if (global_index >= 0)\n                        {\n                            solution.set(global_index, values[0]);\n                        }\n                    }\n                }\n\n                INFO(\n                    "HM-B4 explicit pressure placement state published for "\n                    "{:d} newly activated elements",\n                    pressure_transition.newly_activated_element_ids.size());\n\n                GlobalExecutor::executeSelectedMemberOnDereferenced(\n                    &LocalAssemblerIF::initializeActivationPlacementState,\n                    local_assemblers_,\n                    pressure_transition.newly_activated_element_ids);\n            }\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected HM-B3 activation publication body")
cpp.write_text(text.replace(old, new, 1), encoding="utf-8")

fem = root / "ProcessLib/HydroMechanics/HydroMechanicsFEM.h"
text = fem.read_text(encoding="utf-8")

old = '''            ip_data.strain_rate_variable = 0.0;\n        }\n\n        INFO("HM-B3 fresh coupled birth state initialized for element {:d}",\n             element_id);\n'''
new = '''            ip_data.strain_rate_variable = 0.0;\n        }\n\n        activation_reference_pending_ = true;\n        activation_reference_displacement_.resize(0);\n        activation_reference_pressure_.resize(0);\n\n        INFO("HM-B3 fresh coupled birth state initialized for element {:d}",\n             element_id);\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected HM-B3 placement-state body")
text = text.replace(old, new, 1)

anchor = '''    std::vector<IpData, Eigen::aligned_allocator<IpData>> _ip_data;\n\n    NumLib::GenericIntegrationMethod const& _integration_method;\n'''
replacement = '''    std::vector<IpData, Eigen::aligned_allocator<IpData>> _ip_data;\n\n    bool activation_reference_pending_ = false;\n    Eigen::VectorXd activation_reference_displacement_;\n    Eigen::VectorXd activation_reference_pressure_;\n\n    NumLib::GenericIntegrationMethod const& _integration_method;\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected HM member anchor")
text = text.replace(anchor, replacement, 1)
fem.write_text(text, encoding="utf-8")

impl = root / "ProcessLib/HydroMechanics/HydroMechanicsFEM-impl.h"
text = impl.read_text(encoding="utf-8")
anchor = '''    auto u_prev =\n        Eigen::Map<typename ShapeMatricesTypeDisplacement::template VectorType<\n            displacement_size> const>(local_x_prev.data() + displacement_index,\n                                      displacement_size);\n\n    auto local_Jac = MathLib::createZeroedMatrix<\n'''
insert = '''    auto u_prev =\n        Eigen::Map<typename ShapeMatricesTypeDisplacement::template VectorType<\n            displacement_size> const>(local_x_prev.data() + displacement_index,\n                                      displacement_size);\n\n    if (activation_reference_pending_)\n    {\n        activation_reference_displacement_ = u;\n        activation_reference_pressure_ = p;\n        activation_reference_pending_ = false;\n        INFO("HM-B4 placement state captured for element {:d}: p_L0={:.17g}",\n             _element.getID(), activation_reference_pressure_.mean());\n    }\n\n    Eigen::VectorXd const u_constitutive =\n        activation_reference_displacement_.size() == 0\n            ? Eigen::VectorXd(u)\n            : Eigen::VectorXd(u - activation_reference_displacement_);\n\n    auto local_Jac = MathLib::createZeroedMatrix<\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected HM monolithic local-x anchor")
text = text.replace(anchor, insert, 1)

old = '''        auto& eps = _ip_data[ip].eps;\n        eps.noalias() = B * u;\n        auto const& sigma_eff = _ip_data[ip].sigma_eff;\n'''
new = '''        auto& eps = _ip_data[ip].eps;\n        eps.noalias() = B * u_constitutive;\n        auto const& sigma_eff = _ip_data[ip].sigma_eff;\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected HM monolithic strain anchor")
text = text.replace(old, new, 1)

impl.write_text(text, encoding="utf-8")
print("Applied HM-B4 explicit coupled placement-state semantics")
