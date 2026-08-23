#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
source = root / "staged-r3b-smoke.cpp"
source.write_text(r'''#include <cmath>
#include <stdexcept>

#include "ProcessLib/StagedConstruction/AdaptiveRemovalTransaction.h"

int main()
{
    using namespace ProcessLib::StagedConstruction;

    AdaptiveTransitionController::Config cfg;
    cfg.initial_increment = 0.25;
    cfg.minimum_increment = 0.0625;
    cfg.maximum_increment = 0.5;
    cfg.growth_factor = 2.0;
    cfg.cutback_factor = 0.5;

    AdaptiveTransitionController controller(cfg);
    MechanicalRemovalTransition transition({4}, {16.0});
    AdaptiveRemovalTransaction transaction(controller, transition);

    // First nonlinear trial fails: committed state and retained force must be
    // exactly restored while the continuation increment is cut back.
    double lambda = transaction.beginTrial();
    if (std::abs(lambda - 0.25) > 1e-14) return 1;
    if (std::abs(transition.currentForce()[0] - 12.0) > 1e-14) return 2;
    transaction.rejectTrial();
    if (std::abs(transaction.committedCoordinate()) > 1e-14) return 3;
    if (std::abs(transition.currentForce()[0] - 16.0) > 1e-14) return 4;
    if (std::abs(controller.increment() - 0.125) > 1e-14) return 5;

    // Retry succeeds and advances both committed coordinates atomically.
    lambda = transaction.beginTrial();
    if (std::abs(lambda - 0.125) > 1e-14) return 6;
    transaction.commitTrial();
    if (std::abs(transaction.committedCoordinate() - 0.125) > 1e-14) return 7;
    if (std::abs(transition.releaseCoordinate() - 0.125) > 1e-14) return 8;
    if (std::abs(transition.currentForce()[0] - 14.0) > 1e-14) return 9;

    // Continue with successful trials until full release.
    while (!transaction.isComplete())
    {
        transaction.beginTrial();
        transaction.commitTrial();
    }
    if (std::abs(transaction.committedCoordinate() - 1.0) > 1e-14) return 10;
    if (!transition.isFullyReleased()) return 11;
    if (std::abs(transition.currentForce()[0]) > 1e-14) return 12;

    bool completed_rejected = false;
    try { transaction.beginTrial(); }
    catch (std::logic_error const&) { completed_rejected = true; }
    if (!completed_rejected) return 13;

    return 0;
}
''', encoding="utf-8")
print(source)
