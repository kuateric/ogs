// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <array>
#include <cstddef>

#include "MechanicalInterfaceGlobalAssembly.h"
#include "MechanicalInterfaceStateManager.h"

namespace ProcessLib::MechanicalInterface
{
/// Evaluate one Side-A/Side-B interface pair against the last converged
/// constitutive history and store only the resulting Newton trial response.
///
/// This is the stateful bridge between process-owned kinematics/assembly and
/// the local reference law. It deliberately does not commit constitutive
/// history: commitTimeStep() is called only by the owning process after
/// nonlinear convergence; rollbackTimeStep() discards rejected trial history.
inline PairResponse assembleTrialPair(
    std::size_t const pair_id,
    std::array<double, 2> const& u_a,
    std::array<double, 2> const& u_b,
    std::array<double, 2> const& normal,
    double const initial_normal_gap,
    Parameters const& parameters,
    MechanicalInterfaceStateManager& state_manager)
{
    auto response = assemblePair(u_a, u_b, normal, initial_normal_gap,
                                 parameters,
                                 state_manager.committedHistory(pair_id));
    state_manager.setTrialResponse(pair_id, response.local);
    return response;
}

/// Build a global-scatter contribution from a Newton trial pair evaluation.
/// The returned residual/Jacobian retains the exact equal-and-opposite block
/// structure produced by assemblePair(); this helper adds no contact semantics.
inline GlobalPairContribution assembleTrialGlobalPair(
    std::size_t const pair_id,
    std::array<double, 2> const& u_a,
    std::array<double, 2> const& u_b,
    std::array<double, 2> const& normal,
    double const initial_normal_gap,
    Parameters const& parameters,
    std::array<std::size_t, 4> const& global_indices,
    MechanicalInterfaceStateManager& state_manager)
{
    GlobalPairContribution contribution;
    contribution.pair = assembleTrialPair(pair_id, u_a, u_b, normal,
                                          initial_normal_gap, parameters,
                                          state_manager);
    contribution.global_indices = global_indices;
    return contribution;
}
}  // namespace ProcessLib::MechanicalInterface
