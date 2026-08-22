#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
header = root / "ProcessLib/StagedConstruction/MechanicalRemovalForceCapture.h"
header.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <algorithm>
#include <cstddef>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

#include "MechanicalRemovalTransition.h"

namespace ProcessLib::StagedConstruction
{
/// Accumulates the already assembled local mechanical residual contributions
/// of elements that are about to be removed, restricted to DOFs shared with
/// the remaining active domain. Re-applying this contribution immediately
/// after removal preserves the pre-removal discrete equilibrium.
///
/// The capture consumes the same local residual vector that OGS assembly
/// computes. It therefore does not reconstruct stresses or tractions through
/// an independent projection/integration path.
class MechanicalRemovalForceCapture
{
public:
    explicit MechanicalRemovalForceCapture(
        std::vector<std::size_t> interface_dof_ids)
        : _interface_dof_ids(std::move(interface_dof_ids)),
          _retained_force(_interface_dof_ids.size(), 0.0)
    {
        std::sort(_interface_dof_ids.begin(), _interface_dof_ids.end());
        if (std::adjacent_find(_interface_dof_ids.begin(),
                               _interface_dof_ids.end()) !=
            _interface_dof_ids.end())
        {
            throw std::invalid_argument(
                "Mechanical removal interface DOFs must be unique.");
        }

        _index.reserve(_interface_dof_ids.size());
        for (std::size_t i = 0; i < _interface_dof_ids.size(); ++i)
        {
            _index.emplace(_interface_dof_ids[i], i);
        }
    }

    void addElementResidual(std::vector<std::size_t> const& local_dof_ids,
                            std::vector<double> const& local_residual)
    {
        if (local_dof_ids.size() != local_residual.size())
        {
            throw std::invalid_argument(
                "Mechanical removal local DOF and residual vectors must have "
                "equal size.");
        }

        for (std::size_t i = 0; i < local_dof_ids.size(); ++i)
        {
            auto const it = _index.find(local_dof_ids[i]);
            if (it != _index.end())
            {
                _retained_force[it->second] += local_residual[i];
            }
        }
    }

    MechanicalRemovalTransition makeTransition() const
    {
        return MechanicalRemovalTransition(_interface_dof_ids,
                                           _retained_force);
    }

private:
    std::vector<std::size_t> _interface_dof_ids;
    std::vector<double> _retained_force;
    std::unordered_map<std::size_t, std::size_t> _index;
};
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

print("Applied OGS Staged Construction R2B mechanical force-capture primitive")
