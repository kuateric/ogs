#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# HM-B4 — explicit coupled placement state.
# Literature-guided semantics:
# * mechanical birth uses the current deformed configuration as stress-free
#   reference (Abaqus/PLAXIS element activation semantics),
# * liquid pressure remains an absolute primary variable; p_L,0 is captured as
#   the explicit hydraulic placement state rather than subtracted from p.
# B3 must already have installed the fresh constitutive-state hook.

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
