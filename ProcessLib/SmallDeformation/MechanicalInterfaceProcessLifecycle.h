// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include "MechanicalInterfaceStateManager.h"

namespace ProcessLib::MechanicalInterface
{
/// Process-facing lifecycle adapter for the G5 mechanical interface.
///
/// Newton/Jacobian assembly must only create trial responses via the G5 trial
/// assembly path. Constitutive history is accepted only after the owning OGS
/// process has accepted the nonlinear time step.
///
/// Canonical OGS SHA adf770974c7ee0435702fe617634d03d17ab7cb8 exposes an
/// accepted post-timestep hook but no process-specific callback for every
/// abandoned Newton/time-step attempt. Therefore beginTrialAssembly() restores
/// the trial view from committed history before each fresh residual/Jacobian
/// evaluation. A rejected solve can never leak trial plastic slip into the next
/// evaluation even when no explicit reject callback is available. An explicit
/// rejectTimeStep() remains available for solvers/processes that can signal it.
///
/// The adapter intentionally contains no SmallDeformation-specific mechanics;
/// the same contract can later be reused by RichardsMechanics.
class MechanicalInterfaceProcessLifecycle final
{
public:
    explicit MechanicalInterfaceProcessLifecycle(
        MechanicalInterfaceStateManager& state_manager)
        : state_manager_(state_manager)
    {
    }

    /// Call immediately before a fresh nonlinear residual/Jacobian evaluation.
    /// This makes trial evaluation idempotent with respect to rejected attempts:
    /// every evaluation starts from the last converged constitutive history.
    void beginTrialAssembly() { state_manager_.rollbackTimeStep(); }

    /// Call from the owning process' accepted post-timestep path.
    void acceptTimeStep() { state_manager_.commitTimeStep(); }

    /// Optional explicit rejection hook where the owning solver exposes one.
    void rejectTimeStep() { state_manager_.rollbackTimeStep(); }

private:
    MechanicalInterfaceStateManager& state_manager_;
};
}  // namespace ProcessLib::MechanicalInterface
