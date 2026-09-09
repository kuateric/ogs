// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#include "MechanicalInterfaceProcessDofMapper.h"

#include <algorithm>
#include <array>
#include <limits>
#include <stdexcept>

#include "MeshLib/Location.h"
#include "NumLib/DOF/LocalToGlobalIndexMap.h"

namespace ProcessLib::MechanicalInterface
{
namespace
{
std::size_t normalizeProcessGlobalIndex(
    GlobalIndexType const index,
    NumLib::LocalToGlobalIndexMap const& dof_table)
{
    if (index >= 0)
    {
        return static_cast<std::size_t>(index);
    }

    if (index == std::numeric_limits<GlobalIndexType>::min())
    {
        throw std::overflow_error(
            "Mechanical-interface process DOF index cannot be normalized.");
    }

    // OGS PETSc maps ghost DOFs to negative values. Usually the real global
    // index is -index. Global DOF 0 cannot be represented as negative zero,
    // however, so MeshComponentMap encodes that one as -num_global_dof. Do not
    // use abs(index): resolve the encoded value against OGS' authoritative
    // ghost-index table instead.
    auto const encoded_candidate = -index;
    auto const& ghost_indices = dof_table.getGhostIndices();
    if (std::find(ghost_indices.begin(), ghost_indices.end(),
                  encoded_candidate) != ghost_indices.end())
    {
        return static_cast<std::size_t>(encoded_candidate);
    }

    if (std::find(ghost_indices.begin(), ghost_indices.end(), 0) !=
        ghost_indices.end())
    {
        return 0;
    }

    throw std::runtime_error(
        "Mechanical-interface PETSc ghost DOF cannot be resolved through the "
        "owning process ghost-index table.");
}

std::size_t mapOneDof(std::size_t const mesh_id, std::size_t const node_id,
                      int const variable_id, int const component_id,
                      NumLib::LocalToGlobalIndexMap const& dof_table)
{
    MeshLib::Location const location{mesh_id, MeshLib::MeshItemType::Node,
                                     node_id};
    auto const index =
        dof_table.getGlobalIndex(location, variable_id, component_id);
    if (index == NumLib::MeshComponentMap::nop)
    {
        throw std::runtime_error(
            "Mechanical-interface node has no displacement DOF in the owning "
            "process table.");
    }

    return normalizeProcessGlobalIndex(index, dof_table);
}
}  // namespace

std::array<std::size_t, 4> map2DPairToProcessDofs(
    std::size_t const mesh_id, std::size_t const side_a_node_id,
    std::size_t const side_b_node_id,
    NumLib::LocalToGlobalIndexMap const& process_dof_table,
    int const displacement_variable_id)
{
    if (process_dof_table.getNumberOfVariableComponents(
            displacement_variable_id) != 2)
    {
        throw std::invalid_argument(
            "G5 V1 SmallDeformation runtime currently requires a 2D "
            "displacement process variable.");
    }

    return {{mapOneDof(mesh_id, side_a_node_id, displacement_variable_id, 0,
                       process_dof_table),
             mapOneDof(mesh_id, side_a_node_id, displacement_variable_id, 1,
                       process_dof_table),
             mapOneDof(mesh_id, side_b_node_id, displacement_variable_id, 0,
                       process_dof_table),
             mapOneDof(mesh_id, side_b_node_id, displacement_variable_id, 1,
                       process_dof_table)}};
}
}  // namespace ProcessLib::MechanicalInterface
