#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
header = root / "ProcessLib/StagedConstruction/MechanicalRemovalInterface.h"
header.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <algorithm>
#include <cstddef>
#include <vector>

namespace ProcessLib::StagedConstruction
{
/// Determines the mechanical DOFs shared by newly removed elements and the
/// remaining active domain. These are the only DOFs on which a retained
/// pre-removal action may be re-applied after element removal.
///
/// Inputs are element-local global DOF id lists. The function is intentionally
/// independent of a concrete process and DOF-table implementation; ProcessLib
/// adapters can gather those lists from the existing LocalToGlobalIndexMap.
inline std::vector<std::size_t> determineMechanicalRemovalInterfaceDOFs(
    std::vector<std::vector<std::size_t>> const& removed_element_dofs,
    std::vector<std::vector<std::size_t>> const& remaining_active_element_dofs)
{
    std::vector<std::size_t> removed;
    for (auto const& dofs : removed_element_dofs)
    {
        removed.insert(removed.end(), dofs.begin(), dofs.end());
    }
    std::sort(removed.begin(), removed.end());
    removed.erase(std::unique(removed.begin(), removed.end()), removed.end());

    std::vector<std::size_t> remaining;
    for (auto const& dofs : remaining_active_element_dofs)
    {
        remaining.insert(remaining.end(), dofs.begin(), dofs.end());
    }
    std::sort(remaining.begin(), remaining.end());
    remaining.erase(std::unique(remaining.begin(), remaining.end()),
                    remaining.end());

    std::vector<std::size_t> interface_dofs;
    std::set_intersection(removed.begin(), removed.end(), remaining.begin(),
                          remaining.end(),
                          std::back_inserter(interface_dofs));
    return interface_dofs;
}
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

print("Applied OGS Staged Construction R2C mechanical interface-DOF primitive")
