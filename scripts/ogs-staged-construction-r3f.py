#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
out = root / "ProcessLib/StagedConstruction/ConstructionTimeLoopDriver.h"
out.write_text(r'''#pragma once

#include <cstddef>
#include <functional>

#include "BaseLib/Error.h"
#include "ProcessLib/StagedConstruction/ConstructionSubstepDriver.h"

namespace ProcessLib::StagedConstruction
{
// TimeLoop-facing orchestration contract for adaptive construction solves.
// Physical time and dt are deliberately absent from this class. The caller
// supplies solution and process-state snapshot/commit/rollback callbacks so
// rejected construction trials cannot contaminate either the primary solution
// vector or the constitutive MFront/MGIS baseline.
class ConstructionTimeLoopDriver
{
public:
    struct Callbacks
    {
        std::function<void()> snapshot_solution;
        std::function<void()> restore_solution;
        std::function<bool(double)> solve_nonlinear_trial;
        std::function<void()> commit_process_state;
        std::function<void()> rollback_process_state;
    };

    ConstructionTimeLoopDriver(AdaptiveRemovalTransaction& transaction,
                               Callbacks callbacks)
        : driver_(transaction), callbacks_(std::move(callbacks))
    {
        if (!callbacks_.snapshot_solution || !callbacks_.restore_solution ||
            !callbacks_.solve_nonlinear_trial ||
            !callbacks_.commit_process_state ||
            !callbacks_.rollback_process_state)
        {
            OGS_FATAL("Incomplete staged-construction TimeLoop callbacks.");
        }
    }

    std::size_t run()
    {
        std::size_t accepted = 0;
        while (!driver_.isComplete())
        {
            callbacks_.snapshot_solution();
            auto const lambda = driver_.beginTrial();
            if (!lambda)
            {
                break;
            }

            if (callbacks_.solve_nonlinear_trial(*lambda))
            {
                // Constitutive state is committed only after a converged trial.
                callbacks_.commit_process_state();
                driver_.acceptTrial();
                ++accepted;
            }
            else
            {
                // Restore both state domains before the controller cuts back.
                callbacks_.restore_solution();
                callbacks_.rollback_process_state();
                driver_.rejectTrial();
            }
        }
        return accepted;
    }

private:
    ConstructionSubstepDriver driver_;
    Callbacks callbacks_;
};
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

print("Applied OGS Staged Construction R3F TimeLoop-ready transaction driver")
