#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
header = root / "ProcessLib/StagedConstruction/MechanicalRemovalEventBridge.h"
header.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <cstddef>
#include <stdexcept>
#include <unordered_map>
#include <vector>

#include "DomainLifecycle.h"
#include "MechanicalRemovalBuilder.h"

namespace ProcessLib::StagedConstruction
{
/// Bridges one domain lifecycle transition to one mechanical removal
/// transition. Only elements reported as newly deactivated are consumed.
/// Remaining active element DOFs are supplied by the owning process/DOF table.
inline MechanicalRemovalTransition buildMechanicalRemovalFromDomainTransition(
    DomainTransition const& domain_transition,
    std::unordered_map<std::size_t, MechanicalRemovalElementContribution> const&
        element_contributions,
    std::vector<std::vector<std::size_t>> const&
        remaining_active_element_dofs)
{
    std::vector<MechanicalRemovalElementContribution> removed_elements;
    removed_elements.reserve(
        domain_transition.newly_deactivated_element_ids.size());

    for (auto const element_id :
         domain_transition.newly_deactivated_element_ids)
    {
        auto const it = element_contributions.find(element_id);
        if (it == element_contributions.end())
        {
            throw std::invalid_argument(
                "Missing pre-removal mechanical contribution for newly "
                "deactivated element.");
        }
        removed_elements.push_back(it->second);
    }

    return buildMechanicalRemovalTransition(removed_elements,
                                            remaining_active_element_dofs);
}
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

print("Applied OGS Staged Construction R2E lifecycle-to-removal event bridge")
