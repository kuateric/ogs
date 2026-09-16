#!/usr/bin/env python3
"""Apply only the RM-G5 creator configuration bridge; fail closed on drift."""
from pathlib import Path
import sys

p = Path(sys.argv[1] if len(sys.argv) > 1 else "ProcessLib/RichardsMechanics/CreateRichardsMechanicsProcess.cpp")
s = p.read_text()
if 'getConfigSubtreeOptional("mechanical_interface")' in s:
    raise SystemExit("FAIL: mechanical_interface parser already present")

def once(old, new, label):
    global s
    if s.count(old) != 1:
        raise SystemExit(f"FAIL: {label} anchor count={s.count(old)}")
    s = s.replace(old, new, 1)

once("#include <cassert>\n", "#include <cassert>\n#include <cmath>\n", "include")
parser = r'''
    std::vector<ProcessLib::MechanicalInterface::SmallDeformationPendingPair>
        mechanical_interface_pending_pairs;
    std::vector<ProcessLib::MechanicalInterface::SmallDeformationInterfaceMaterial>
        mechanical_interface_materials;
    if (auto mechanical_interface_config =
            config.getConfigSubtreeOptional("mechanical_interface"))
    {
        if constexpr (DisplacementDim != 2)
            OGS_FATAL("G5 <mechanical_interface> V1 is available only for 2D RICHARDS_MECHANICS.");
        for (auto const& c : mechanical_interface_config->getConfigSubtreeList("material"))
        {
            auto const id = c.getConfigParameter<std::size_t>("id");
            auto const kn = c.getConfigParameter<double>("normal_stiffness");
            auto const kt = c.getConfigParameter<double>("tangential_stiffness");
            auto const mu = c.getConfigParameter<double>("friction_coefficient");
            if (!(kn > 0.0) || !(kt > 0.0) || mu < 0.0)
                OGS_FATAL("G5 interface material {:d}: invalid parameters.", id);
            mechanical_interface_materials.push_back({id, {kn, kt, mu}});
        }
        if (mechanical_interface_materials.empty())
            OGS_FATAL("G5 <mechanical_interface> requires at least one <material>.");
        std::size_t pair_id = 0;
        for (auto const& c : mechanical_interface_config->getConfigSubtreeList("pair"))
        {
            auto normal = c.getConfigParameter<std::vector<double>>("normal");
            if (normal.size() != 2)
                OGS_FATAL("G5 pair {:d}: normal must have two components.", pair_id);
            auto const n = std::hypot(normal[0], normal[1]);
            if (!(n > 0.0)) OGS_FATAL("G5 pair {:d}: normal must be non-zero.", pair_id);
            mechanical_interface_pending_pairs.push_back(
                {pair_id,
                 c.getConfigParameter<std::size_t>("side_a_node_id"),
                 c.getConfigParameter<std::size_t>("side_b_node_id"),
                 {normal[0] / n, normal[1] / n},
                 c.getConfigParameter<double>("initial_normal_gap", 0.0),
                 c.getConfigParameter<std::size_t>("interface_material_id")});
            ++pair_id;
        }
        if (mechanical_interface_pending_pairs.empty())
            OGS_FATAL("G5 <mechanical_interface> requires at least one <pair>.");
    }
'''
once("    RichardsMechanicsProcessData<DisplacementDim> process_data{", parser + "\n    RichardsMechanicsProcessData<DisplacementDim> process_data{", "process_data")
old = '''    return std::make_unique<RichardsMechanicsProcess<DisplacementDim>>(
        std::move(name), mesh, std::move(jacobian_assembler), parameters,
        integration_order, std::move(process_variables),
        std::move(process_data), std::move(secondary_variables),
        use_monolithic_scheme, is_linear);'''
new = '''    auto process = std::make_unique<RichardsMechanicsProcess<DisplacementDim>>(
        std::move(name), mesh, std::move(jacobian_assembler), parameters,
        integration_order, std::move(process_variables),
        std::move(process_data), std::move(secondary_variables),
        use_monolithic_scheme, is_linear);
    process->setMechanicalInterfaceConfiguration(
        std::move(mechanical_interface_pending_pairs),
        std::move(mechanical_interface_materials));
    return process;'''
once(old, new, "process construction")
p.write_text(s)
print("RM-G5 creator bridge applied")
