#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
header = root / "ProcessLib/StagedConstruction/MechanicalRemovalBuilder.h"
header.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <cstddef>
#include <stdexcept>
#include <vector>

#include "MechanicalRemovalForceCapture.h"
#include "MechanicalRemovalInterface.h"

namespace ProcessLib::StagedConstruction
{
/// Process-neutral input for one newly removed mechanical element. The global
/// DOF ids and the already assembled local residual must describe the same
/// element-local vector ordering.
struct MechanicalRemovalElementContribution
{
    std::vector<std::size_t> dof_ids;
    std::vector<double> residual;
};

/// Builds one equilibrium-preserving removal transition from the discrete FE
/// data available immediately before an active->inactive domain change.
///
/// This composes the two R2 primitives deliberately: interface DOFs are derived
/// from removed vs. remaining active element connectivity, and only then are
/// the removed elements' existing residual contributions accumulated on that
/// interface. No stress extrapolation or second traction integration is used.
inline MechanicalRemovalTransition buildMechanicalRemovalTransition(
    std::vector<MechanicalRemovalElementContribution> const& removed_elements,
    std::vector<std::vector<std::size_t>> const&
        remaining_active_element_dofs)
{
    std::vector<std::vector<std::size_t>> removed_element_dofs;
    removed_element_dofs.reserve(removed_elements.size());

    for (auto const& element : removed_elements)
    {
        if (element.dof_ids.size() != element.residual.size())
        {
            throw std::invalid_argument(
                "Mechanical removal element DOF and residual vectors must "
                "have equal size.");
        }
        removed_element_dofs.push_back(element.dof_ids);
    }

    auto interface_dofs = determineMechanicalRemovalInterfaceDOFs(
        removed_element_dofs, remaining_active_element_dofs);
    MechanicalRemovalForceCapture capture(std::move(interface_dofs));

    for (auto const& element : removed_elements)
    {
        capture.addElementResidual(element.dof_ids, element.residual);
    }

    return capture.makeTransition();
}
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

print("Applied OGS Staged Construction R2D mechanical removal builder")
