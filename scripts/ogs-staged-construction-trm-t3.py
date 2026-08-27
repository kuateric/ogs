#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# TRM-T3 — explicit coupled placement state.
# Literature-guided semantics inherited from A4L and HM-B4:
# * displacement is measured from the current deformed birth configuration,
#   which is stress-free unless an explicit placement stress says otherwise;
# * liquid pressure p_L and temperature T are absolute primary variables and
#   are published from their ProcessVariable initial-condition parameters into
#   newborn DOFs before the first coupled assembly;
# * no stiffness/residual/material homotopy is introduced.
# T2 must already have installed the fresh constitutive-state hook.

cpp = root / "ProcessLib/ThermoRichardsMechanics/ThermoRichardsMechanicsProcess.cpp"
text = cpp.read_text(encoding="utf-8")

sig_old = '''    preTimestepConcreteProcess(std::vector<GlobalVector*> const& /*x*/,\n                               const double t,\n                               const double /*dt*/,\n                               const int /*process_id*/)\n'''
sig_new = '''    preTimestepConcreteProcess(std::vector<GlobalVector*> const& x,\n                               const double t,\n                               const double /*dt*/,\n                               const int process_id)\n'''
if text.count(sig_old) != 1:
    raise RuntimeError("unexpected TRM-T2 preTimestep signature")
text = text.replace(sig_old, sig_new, 1)

old = '''    if (!temperature_transition.newly_activated_element_ids.empty())\n    {\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &LocalAssemblerIF::initializeActivationPlacementState,\n            local_assemblers_,\n            temperature_transition.newly_activated_element_ids, t);\n    }\n'''
new = '''    if (!temperature_transition.newly_activated_element_ids.empty())\n    {\n        // TRM-T3: T and p_L are absolute placement states. Publish the\n        // configured initial conditions into the newborn scalar DOFs before\n        // the first coupled assembly. Mechanical displacement is intentionally\n        // not reset; the local assembler captures the current deformed\n        // configuration as its stress-free birth reference.\n        auto const& temperature_initial_condition =\n            variables[0].get().getInitialCondition();\n        auto const& pressure_initial_condition =\n            variables[1].get().getInitialCondition();\n        auto& mesh = getMesh();\n        auto& solution = *x[process_id];\n\n        auto publish_scalar_placement =\n            [&](auto const& initial_condition, int const variable_id,\n                char const* const field_name)\n        {\n            for (auto const element_id :\n                 temperature_transition.newly_activated_element_ids)\n            {\n                auto const* element = mesh.getElement(element_id);\n                auto const number_of_nodes = element->getNumberOfBaseNodes();\n                for (unsigned local_node_id = 0;\n                     local_node_id < number_of_nodes; ++local_node_id)\n                {\n                    auto const* node = element->getNode(local_node_id);\n                    ParameterLib::SpatialPosition const position{\n                        node->getID(), element_id, *node};\n                    auto const values = initial_condition(t, position);\n                    if (values.size() != 1)\n                    {\n                        OGS_FATAL(\n                            "TRM-T3 {} placement state must be scalar.",\n                            field_name);\n                    }\n\n                    auto const global_index =\n                        _local_to_global_index_map->getGlobalIndex(\n                            MeshLib::Location{\n                                mesh.getID(), MeshLib::MeshItemType::Node,\n                                node->getID()},\n                            variable_id, 0);\n                    if (global_index >= 0)\n                    {\n                        solution.set(global_index, values[0]);\n                    }\n                }\n            }\n        };\n\n        publish_scalar_placement(temperature_initial_condition, 0,\n                                 "temperature");\n        publish_scalar_placement(pressure_initial_condition, 1, "pressure");\n\n        INFO(\n            "TRM-T3 explicit T/p_L placement state published for {:d} newly "\n            "activated elements",\n            temperature_transition.newly_activated_element_ids.size());\n\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &LocalAssemblerIF::initializeActivationPlacementState,\n            local_assemblers_,\n            temperature_transition.newly_activated_element_ids, t);\n    }\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected TRM-T2 activation publication body")
cpp.write_text(text.replace(old, new, 1), encoding="utf-8")

fem = root / "ProcessLib/ThermoRichardsMechanics/ThermoRichardsMechanicsFEM.h"
text = fem.read_text(encoding="utf-8")

old = '''        INFO("TRM-T2 fresh coupled birth state initialized for element {:d}",\n             element_id);\n    }\n\n    void initializeConcrete() override\n'''
new = '''        activation_reference_pending_ = true;\n        activation_reference_displacement_.resize(0);\n        activation_reference_pressure_.resize(0);\n        activation_reference_temperature_.resize(0);\n\n        INFO("TRM-T2 fresh coupled birth state initialized for element {:d}",\n             element_id);\n    }\n\n    void initializeConcrete() override\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected TRM-T2 fresh-state method tail")
text = text.replace(old, new, 1)

anchor = '''private:\n    std::vector<IpData> ip_data_;\n\n    static constexpr auto localDOF(std::vector<double> const& x)\n'''
replacement = '''private:\n    std::vector<IpData> ip_data_;\n\n    bool activation_reference_pending_ = false;\n    Eigen::VectorXd activation_reference_displacement_;\n    Eigen::VectorXd activation_reference_pressure_;\n    Eigen::VectorXd activation_reference_temperature_;\n\n    static constexpr auto localDOF(std::vector<double> const& x)\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected TRM local-assembler member anchor")
text = text.replace(anchor, replacement, 1)
fem.write_text(text, encoding="utf-8")

impl = root / "ProcessLib/ThermoRichardsMechanics/ThermoRichardsMechanicsFEM-impl.h"
text = impl.read_text(encoding="utf-8")

anchor = '''    typename ConstitutiveTraits::ConstitutiveSetting constitutive_setting;\n\n    for (unsigned ip = 0; ip < this->integration_method_.getNumberOfPoints();\n'''
insert = '''    typename ConstitutiveTraits::ConstitutiveSetting constitutive_setting;\n\n    if (activation_reference_pending_)\n    {\n        auto const [T, p_L, u] = localDOF(local_x);\n        activation_reference_temperature_ = T;\n        activation_reference_pressure_ = p_L;\n        activation_reference_displacement_ = u;\n        activation_reference_pending_ = false;\n\n        INFO(\n            "TRM-T3 placement state captured for element {:d}: "\n            "T0={:.17g}, p_L0={:.17g}",\n            this->element_.getID(), activation_reference_temperature_.mean(),\n            activation_reference_pressure_.mean());\n    }\n\n    for (unsigned ip = 0; ip < this->integration_method_.getNumberOfPoints();\n'''
if text.count(anchor) != 1:
    raise RuntimeError("unexpected TRM assembleWithJacobian anchor")
text = text.replace(anchor, insert, 1)

old = '''    auto const [T, p_L, u] = localDOF(local_x);\n    auto const [T_prev, p_L_prev, u_prev] = localDOF(local_x_prev);\n\n    {\n'''
new = '''    auto const [T, p_L, u] = localDOF(local_x);\n    auto const [T_prev, p_L_prev, u_prev] = localDOF(local_x_prev);\n\n    Eigen::VectorXd const u_constitutive =\n        activation_reference_displacement_.size() == 0\n            ? Eigen::VectorXd(u)\n            : Eigen::VectorXd(u - activation_reference_displacement_);\n\n    {\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected TRM local DOF anchor")
text = text.replace(old, new, 1)

old = '''        KelvinVectorType eps = B * u;\n'''
new = '''        KelvinVectorType eps = B * u_constitutive;\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected TRM constitutive strain anchor")
text = text.replace(old, new, 1)
impl.write_text(text, encoding="utf-8")

print("Applied TRM-T3 explicit coupled placement-state semantics")
