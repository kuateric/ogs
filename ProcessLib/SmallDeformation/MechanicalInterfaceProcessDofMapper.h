// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <array>
#include <cstddef>

namespace NumLib
{
class LocalToGlobalIndexMap;
}

namespace ProcessLib::MechanicalInterface
{
/// Map one geometrically paired Side-A/Side-B node pair onto the authoritative
/// displacement DOFs of the owning OGS process.
///
/// G5 deliberately does not use indices from its stand-alone two-field topology
/// for runtime assembly. In SmallDeformation the independent displacement
/// fields are represented by distinct coincident mesh nodes inside the ordinary
/// process variable, so residual/Jacobian scatter must target that process' DOF
/// table.
std::array<std::size_t, 4> map2DPairToProcessDofs(
    std::size_t mesh_id, std::size_t side_a_node_id,
    std::size_t side_b_node_id,
    NumLib::LocalToGlobalIndexMap const& process_dof_table,
    int displacement_variable_id = 0);
}  // namespace ProcessLib::MechanicalInterface
