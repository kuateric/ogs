// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <cstddef>
#include <vector>

#include "MechanicalInterfaceLaw.h"

namespace ProcessLib::MechanicalInterface
{
/// Per-pair state storage with explicit Newton trial/commit/rollback semantics.
///
/// Constitutive history is never committed during a Newton iteration. Each
/// trial evaluation starts from the last converged history. A successful time
/// step commits the accepted trial response; a rejected step discards it.
class MechanicalInterfaceStateManager final
{
public:
    explicit MechanicalInterfaceStateManager(std::size_t number_of_pairs);

    std::size_t size() const { return committed_history_.size(); }

    History const& committedHistory(std::size_t pair_id) const;
    Response const& trialResponse(std::size_t pair_id) const;

    void setTrialResponse(std::size_t pair_id, Response response);

    /// Accept all current trial responses after nonlinear convergence.
    void commitTimeStep();

    /// Restore trial outputs/history view to the last converged state.
    void rollbackTimeStep();

private:
    void checkPairId(std::size_t pair_id) const;

    std::vector<History> committed_history_;
    std::vector<Response> trial_response_;
};
}  // namespace ProcessLib::MechanicalInterface
