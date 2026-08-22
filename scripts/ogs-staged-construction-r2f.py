#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
header = root / "ProcessLib/StagedConstruction/MechanicalRemovalDofTableAdapter.h"
header.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <cstddef>
#include <stdexcept>
#include <vector>

#include "NumLib/DOF/DOFTableUtil.h"

namespace ProcessLib::StagedConstruction
{
/// Returns the owned global DOFs of one bulk element in the exact local ordering
/// used by OGS' element assembly. This is the bridge from the generic staged-
/// construction removal contracts to the real LocalToGlobalIndexMap.
///
/// The R2 implementation intentionally rejects ghost indices for now. Retained
/// force assembly across MPI partitions needs an ownership-aware reduction and
/// must not silently reinterpret OGS' negative ghost-index encoding as size_t.
inline std::vector<std::size_t> getOwnedElementDofIDs(
    std::size_t const element_id,
    NumLib::LocalToGlobalIndexMap const& dof_table)
{
    auto const indices = NumLib::getIndices(element_id, dof_table);
    std::vector<std::size_t> result;
    result.reserve(indices.size());

    for (auto const index : indices)
    {
        if (index == NumLib::MeshComponentMap::nop)
        {
            throw std::runtime_error(
                "Mechanical removal encountered an undefined element DOF.");
        }
        if (index < 0)
        {
            throw std::runtime_error(
                "Mechanical removal R2 does not yet support ghost DOFs; an "
                "ownership-aware MPI force reduction is required.");
        }
        result.push_back(static_cast<std::size_t>(index));
    }

    return result;
}

inline std::vector<std::vector<std::size_t>> getOwnedElementDofIDs(
    std::vector<std::size_t> const& element_ids,
    NumLib::LocalToGlobalIndexMap const& dof_table)
{
    std::vector<std::vector<std::size_t>> result;
    result.reserve(element_ids.size());
    for (auto const element_id : element_ids)
    {
        result.push_back(getOwnedElementDofIDs(element_id, dof_table));
    }
    return result;
}
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

print("Applied OGS Staged Construction R2F LocalToGlobalIndexMap adapter")
