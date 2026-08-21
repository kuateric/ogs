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

cmake = root / "ProcessLib/CMakeLists.txt"
text = cmake.read_text(encoding="utf-8")
needle = "    Reflection\n    Graph\n)"
replacement = "    Reflection\n    Graph\n    StagedConstruction\n)"
if text.count(needle) != 1:
    raise RuntimeError("Unexpected ProcessLib/CMakeLists.txt layout")
cmake.write_text(text.replace(needle, replacement), encoding="utf-8")

print("Applied OGS Staged Construction R0 lifecycle core patch")
