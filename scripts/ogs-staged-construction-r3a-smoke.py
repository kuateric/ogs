#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
source = root / "staged-r3a-smoke.cpp"
source.write_text(r'''#include <cmath>
#include <stdexcept>
#include <vector>

#include "ProcessLib/StagedConstruction/AdaptiveTransitionController.h"
#include "ProcessLib/StagedConstruction/MechanicalRemovalTransition.h"

int main()
{
    using ProcessLib::StagedConstruction::AdaptiveTransitionController;
    using ProcessLib::StagedConstruction::MechanicalRemovalTransition;

    AdaptiveTransitionController::Config cfg;
    cfg.initial_increment = 0.25;
    cfg.minimum_increment = 0.0625;
    cfg.maximum_increment = 0.5;
    cfg.growth_factor = 2.0;
    cfg.cutback_factor = 0.5;
    AdaptiveTransitionController c(cfg);
    MechanicalRemovalTransition t({2}, {8.0});

    double trial = c.beginTrial();
    if (std::abs(trial - 0.25) > 1e-14) return 1;
    t.beginTrialRelease(trial);
    if (std::abs(t.currentForce()[0] - 6.0) > 1e-14) return 2;

    // Simulate nonlinear failure: neither controller nor removal transition may
    // advance their committed state.
    t.rollbackTrialRelease();
    c.rejectTrial();
    if (std::abs(c.committedCoordinate()) > 1e-14) return 3;
    if (std::abs(t.releaseCoordinate()) > 1e-14) return 4;
    if (std::abs(c.increment() - 0.125) > 1e-14) return 5;
    if (std::abs(t.currentForce()[0] - 8.0) > 1e-14) return 6;

    trial = c.beginTrial();
    t.beginTrialRelease(trial);
    if (std::abs(trial - 0.125) > 1e-14) return 7;
    t.commitTrialRelease();
    c.acceptTrial();
    if (std::abs(c.committedCoordinate() - 0.125) > 1e-14) return 8;
    if (std::abs(t.releaseCoordinate() - 0.125) > 1e-14) return 9;
    if (std::abs(t.currentForce()[0] - 7.0) > 1e-14) return 10;
    if (std::abs(c.increment() - 0.25) > 1e-14) return 11;

    trial = c.beginTrial();
    t.beginTrialRelease(trial);
    t.commitTrialRelease();
    c.acceptTrial();
    if (std::abs(c.committedCoordinate() - 0.375) > 1e-14) return 12;

    bool double_trial_rejected = false;
    trial = c.beginTrial();
    t.beginTrialRelease(trial);
    try { t.beginTrialRelease(trial); }
    catch (std::logic_error const&) { double_trial_rejected = true; }
    if (!double_trial_rejected) return 13;
    t.rollbackTrialRelease();
    c.rejectTrial();

    return 0;
}
''', encoding="utf-8")
print(source)