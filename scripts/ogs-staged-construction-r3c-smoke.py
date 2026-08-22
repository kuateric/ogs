#!/usr/bin/env python3
from pathlib import Path

Path("staged-r3c-smoke.cpp").write_text(r'''#include <cassert>
#include <cmath>
#include <vector>

#include "ProcessLib/StagedConstruction/AdaptiveRemovalTransaction.h"
#include "ProcessLib/StagedConstruction/ConstructionSubstepDriver.h"

using namespace ProcessLib::StagedConstruction;

int main()
{
    MechanicalRemovalTransition transition({7}, {8.0});
    AdaptiveTransitionController controller({0.5, 0.125, 0.5, 1.5, 0.5});
    AdaptiveRemovalTransaction transaction(controller, transition);
    ConstructionSubstepDriver driver(transaction);

    int snapshots = 0;
    int commits = 0;
    int rollbacks = 0;
    std::vector<double> attempted;
    bool reject_first = true;

    auto result = driver.runToCompletion(
        [&] { ++snapshots; },
        [&](double const lambda)
        {
            attempted.push_back(lambda);
            // The trial force must follow the trial construction coordinate.
            auto const force = transition.currentForce();
            assert(force.size() == 1);
            assert(std::abs(force[0] - (1.0 - lambda) * 8.0) < 1e-12);
            if (reject_first)
            {
                reject_first = false;
                return false;
            }
            return true;
        },
        [&] { ++commits; },
        [&] { ++rollbacks; });

    // First 0.5 trial fails, is cut back to 0.25, then accepted trials progress
    // to 0.625 and finally 1.0 without advancing any physical-time variable.
    assert(attempted.size() == 4);
    assert(std::abs(attempted[0] - 0.5) < 1e-12);
    assert(std::abs(attempted[1] - 0.25) < 1e-12);
    assert(std::abs(attempted[2] - 0.625) < 1e-12);
    assert(std::abs(attempted[3] - 1.0) < 1e-12);
    assert(result.rejected_trials == 1);
    assert(result.accepted_trials == 3);
    assert(snapshots == 4);
    assert(rollbacks == 1);
    assert(commits == 3);
    assert(transaction.isComplete());
    assert(transition.isFullyReleased());
    assert(transition.currentForce()[0] == 0.0);

    return 0;
}
''', encoding="utf-8")

print("Generated OGS Staged Construction R3C smoke test")
