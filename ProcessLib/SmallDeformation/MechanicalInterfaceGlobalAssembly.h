// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <array>
#include <cstddef>

#include "MathLib/LinAlg/GlobalMatrixVectorTypes.h"
#include "MechanicalInterfacePairAssembler.h"

namespace ProcessLib::MechanicalInterface
{
struct GlobalPairContribution
{
    PairResponse pair;
    std::array<std::size_t, 4> global_indices{};  // [A_x,A_y,B_x,B_y]
};

/// Scatter one already-evaluated two-sided mechanical interface contribution
/// into the native OGS global residual/Jacobian after ordinary
/// SmallDeformation bulk assembly.
///
/// This is intentionally process-neutral with respect to contact semantics:
/// pair kinematics/law evaluation happens in assemblePair(); this primitive
/// only performs the symmetric Side-A/Side-B global scatter.
void scatterPairContribution(GlobalPairContribution const& contribution,
                             GlobalVector& residual,
                             GlobalMatrix& jacobian);
}  // namespace ProcessLib::MechanicalInterface
