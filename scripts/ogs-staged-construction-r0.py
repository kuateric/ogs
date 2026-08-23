#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
header = root / "ProcessLib/StagedConstruction/DomainLifecycle.h"
header.parent.mkdir(parents=True, exist_ok=True)
header.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace ProcessLib::StagedConstruction
{
enum class DomainState : std::uint8_t
{
    inactive = 0,
    active = 1
};

struct DomainTransition
{
    std::vector<std::size_t> active_element_ids;
    std::vector<std::size_t> newly_activated_element_ids;
    std::vector<std::size_t> newly_deactivated_element_ids;
};

inline DomainTransition determineDomainTransition(
    std::vector<unsigned char> const& previous_is_active,
    std::vector<unsigned char> const& current_is_active)
{
    if (previous_is_active.size() != current_is_active.size())
    {
        throw std::invalid_argument(
            "Domain lifecycle state vectors must have equal size.");
    }

    DomainTransition transition;
    transition.active_element_ids.reserve(current_is_active.size());

    for (std::size_t id = 0; id < current_is_active.size(); ++id)
    {
        bool const was_active = previous_is_active[id] != 0;
        bool const is_active = current_is_active[id] != 0;

        if (is_active)
        {
            transition.active_element_ids.push_back(id);
        }
        if (!was_active && is_active)
        {
            transition.newly_activated_element_ids.push_back(id);
        }
        if (was_active && !is_active)
        {
            transition.newly_deactivated_element_ids.push_back(id);
        }
    }

    return transition;
}
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

removal_header = root / "ProcessLib/StagedConstruction/MechanicalRemovalTransition.h"
removal_header.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <cstddef>
#include <stdexcept>
#include <utility>
#include <vector>

namespace ProcessLib::StagedConstruction
{
/// Stores the mechanical nodal action that disappeared when elements were
/// removed from the active assembly.  lambda is a construction continuation
/// coordinate, not physical time: lambda=0 retains the full pre-removal action,
/// lambda=1 releases it completely.
class MechanicalRemovalTransition
{
public:
    MechanicalRemovalTransition(std::vector<std::size_t> dof_ids,
                                std::vector<double> retained_force)
        : _dof_ids(std::move(dof_ids)),
          _retained_force(std::move(retained_force))
    {
        if (_dof_ids.size() != _retained_force.size())
        {
            throw std::invalid_argument(
                "Mechanical removal DOF and force vectors must have equal size.");
        }
    }

    std::vector<std::size_t> const& dofIDs() const { return _dof_ids; }
    std::vector<double> const& retainedForce() const { return _retained_force; }

    std::vector<double> forceAt(double const lambda) const
    {
        if (lambda < 0.0 || lambda > 1.0)
        {
            throw std::out_of_range(
                "Mechanical removal release coordinate must be in [0, 1].");
        }

        double const scale = 1.0 - lambda;
        auto force = _retained_force;
        for (double& value : force)
        {
            value *= scale;
        }
        return force;
    }

private:
    std::vector<std::size_t> _dof_ids;
    std::vector<double> _retained_force;
};
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

cmake = root / "ProcessLib/CMakeLists.txt"
text = cmake.read_text(encoding="utf-8")
needle = "    Reflection\n    Graph\n)"
replacement = "    Reflection\n    Graph\n    StagedConstruction\n)"
if text.count(needle) != 1:
    raise RuntimeError("Unexpected ProcessLib/CMakeLists.txt layout")
cmake.write_text(text.replace(needle, replacement), encoding="utf-8")

process_variable = root / "ProcessLib/ProcessVariable.cpp"
pv = process_variable.read_text(encoding="utf-8")
include_line = '#include "ProcessLib/StagedConstruction/DomainLifecycle.h"\n'
if include_line not in pv:
    include_anchor = '#include "ProcessLib/DeactivatedSubdomain.h"\n'
    if pv.count(include_anchor) != 1:
        raise RuntimeError("Unexpected ProcessVariable.cpp include layout")
    pv = pv.replace(include_anchor, include_anchor + include_line)

old_tail = '''    auto const number_of_elements = _mesh.getNumberOfElements();
    for (std::size_t element_id = 0; element_id < number_of_elements;
         element_id++)
    {
        if (is_active_in_all_subdomains(element_id))
        {
            _ids_of_active_elements.push_back(element_id);
        }
    }

    // all elements are deactivated
    std::fill(std::begin(*_is_active), std::end(*_is_active), 0u);

    for (auto const id : _ids_of_active_elements)
    {
        (*_is_active)[id] = 1u;
    }
'''
new_tail = '''    auto const previous_is_active = std::vector<unsigned char>(
        std::begin(*_is_active), std::end(*_is_active));
    auto current_is_active =
        std::vector<unsigned char>(_mesh.getNumberOfElements(), 0u);

    auto const number_of_elements = _mesh.getNumberOfElements();
    for (std::size_t element_id = 0; element_id < number_of_elements;
         element_id++)
    {
        if (is_active_in_all_subdomains(element_id))
        {
            current_is_active[element_id] = 1u;
        }
    }

    auto const transition = StagedConstruction::determineDomainTransition(
        previous_is_active, current_is_active);
    _ids_of_active_elements = transition.active_element_ids;
    std::copy(current_is_active.begin(), current_is_active.end(),
              std::begin(*_is_active));
'''
if pv.count(old_tail) != 1:
    raise RuntimeError("Unexpected updateDeactivatedSubdomains tail layout")
pv = pv.replace(old_tail, new_tail)
process_variable.write_text(pv, encoding="utf-8")

print("Applied OGS Staged Construction R2A lifecycle and mechanical release contract patch")
