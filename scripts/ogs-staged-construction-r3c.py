#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

header = root / "ProcessLib/StagedConstruction/ConstructionSubstepDriver.h"
header.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <cstddef>
#include <stdexcept>
#include <utility>

#include "AdaptiveRemovalTransaction.h"

namespace ProcessLib::StagedConstruction
{
/// Executes a complete adaptive construction transition without advancing
/// physical time.
///
/// The driver is intentionally solver-neutral.  The caller supplies four
/// callbacks:
///   * snapshot_state() captures all process/solution/material trial state,
///   * solve_trial(lambda) performs one nonlinear equilibrium solve at the
///     trial construction coordinate and returns true on convergence,
///   * commit_state() commits the converged process/material state,
///   * rollback_state() restores the snapshot after a rejected trial.
///
/// The retained-force transition and the continuation coordinate are committed
/// or rejected atomically by AdaptiveRemovalTransaction.  No material model is
/// evaluated by this class; MFront/MGIS state remains owned by the process.
class ConstructionSubstepDriver
{
public:
    struct Result
    {
        std::size_t accepted_trials = 0;
        std::size_t rejected_trials = 0;
    };

    explicit ConstructionSubstepDriver(AdaptiveRemovalTransaction& transaction)
        : _transaction(transaction)
    {
    }

    template <typename SnapshotState, typename SolveTrial,
              typename CommitState, typename RollbackState>
    Result runToCompletion(SnapshotState&& snapshot_state,
                           SolveTrial&& solve_trial,
                           CommitState&& commit_state,
                           RollbackState&& rollback_state)
    {
        Result result;

        while (!_transaction.isComplete())
        {
            std::forward<SnapshotState>(snapshot_state)();
            double const lambda = _transaction.beginTrial();

            bool converged = false;
            try
            {
                converged = std::forward<SolveTrial>(solve_trial)(lambda);
            }
            catch (...)
            {
                // A solver exception is a rejected construction trial.  First
                // restore process/material state, then restore/cut back the
                // construction transaction, and finally propagate the original
                // exception to the caller.
                std::forward<RollbackState>(rollback_state)();
                _transaction.rejectTrial();
                throw;
            }

            if (converged)
            {
                // Commit the process/material state before publishing the new
                // construction coordinate.  If committing process state throws,
                // rollback and reject the construction trial as one unit.
                try
                {
                    std::forward<CommitState>(commit_state)();
                    _transaction.commitTrial();
                }
                catch (...)
                {
                    std::forward<RollbackState>(rollback_state)();
                    if (_transaction.hasActiveTrial())
                    {
                        _transaction.rejectTrial();
                    }
                    throw;
                }
                ++result.accepted_trials;
            }
            else
            {
                std::forward<RollbackState>(rollback_state)();
                _transaction.rejectTrial();
                ++result.rejected_trials;
            }
        }

        return result;
    }

private:
    AdaptiveRemovalTransaction& _transaction;
};
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

print("Applied OGS Staged Construction R3C adaptive construction substep driver")
