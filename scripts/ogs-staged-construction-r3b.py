#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

header = root / "ProcessLib/StagedConstruction/AdaptiveRemovalTransaction.h"
header.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <stdexcept>

#include "AdaptiveTransitionController.h"
#include "MechanicalRemovalTransition.h"

namespace ProcessLib::StagedConstruction
{
/// Coordinates one adaptive construction trial atomically across the
/// continuation controller and the mechanical retained-force transition.
///
/// This class deliberately contains no nonlinear-solver logic.  A process or
/// time-loop integration starts a trial, solves with the corresponding retained
/// force, and then either commits or rejects the trial according to the solver
/// outcome.  Rejection restores the committed removal coordinate and cuts back
/// the next continuation increment.
class AdaptiveRemovalTransaction
{
public:
    AdaptiveRemovalTransaction(AdaptiveTransitionController& controller,
                               MechanicalRemovalTransition& transition)
        : _controller(controller), _transition(transition)
    {
        if (_controller.committedCoordinate() !=
            _transition.releaseCoordinate())
        {
            throw std::invalid_argument(
                "Adaptive removal controller and transition must start at the same committed coordinate.");
        }
    }

    double beginTrial()
    {
        if (_trial_active)
        {
            throw std::logic_error("Adaptive removal transaction already active.");
        }

        double const lambda = _controller.beginTrial();
        try
        {
            _transition.beginTrialRelease(lambda);
        }
        catch (...)
        {
            // Restore the controller if opening the paired transition fails.
            _controller.rejectTrial();
            throw;
        }

        _trial_active = true;
        return lambda;
    }

    void commitTrial()
    {
        requireTrial();

        // Commit the retained-force state first.  acceptTrial() cannot fail for
        // a valid active trial, so both committed coordinates advance together.
        _transition.commitTrialRelease();
        _controller.acceptTrial();
        _trial_active = false;
        verifyCommittedCoordinates();
    }

    void rejectTrial()
    {
        requireTrial();

        _transition.rollbackTrialRelease();
        _controller.rejectTrial();
        _trial_active = false;
        verifyCommittedCoordinates();
    }

    bool hasActiveTrial() const { return _trial_active; }

    double committedCoordinate() const
    {
        verifyCommittedCoordinates();
        return _controller.committedCoordinate();
    }

    double currentCoordinate() const
    {
        if (_trial_active)
        {
            return _controller.trialCoordinate();
        }
        return committedCoordinate();
    }

    bool isComplete() const
    {
        verifyCommittedCoordinates();
        return _controller.isComplete() && _transition.isFullyReleased();
    }

private:
    void requireTrial() const
    {
        if (!_trial_active || !_controller.hasActiveTrial() ||
            !_transition.hasActiveTrialRelease())
        {
            throw std::logic_error("No complete adaptive removal trial is active.");
        }
    }

    void verifyCommittedCoordinates() const
    {
        if (_controller.committedCoordinate() !=
            _transition.releaseCoordinate())
        {
            throw std::logic_error(
                "Adaptive removal committed coordinates are inconsistent.");
        }
    }

    AdaptiveTransitionController& _controller;
    MechanicalRemovalTransition& _transition;
    bool _trial_active = false;
};
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

print("Applied OGS Staged Construction R3B adaptive removal transaction coordinator")
