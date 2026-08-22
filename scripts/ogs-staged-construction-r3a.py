#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

controller = root / "ProcessLib/StagedConstruction/AdaptiveTransitionController.h"
controller.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <algorithm>
#include <stdexcept>

namespace ProcessLib::StagedConstruction
{
/// Adaptive continuation controller for a construction coordinate lambda in
/// [0,1].  Trial advancement is transactional: rejection leaves the committed
/// coordinate untouched and cuts back the next increment.
class AdaptiveTransitionController
{
public:
    struct Config
    {
        double initial_increment = 0.25;
        double minimum_increment = 1e-3;
        double maximum_increment = 0.5;
        double growth_factor = 1.5;
        double cutback_factor = 0.5;
    };

    explicit AdaptiveTransitionController(Config const config) : _config(config)
    {
        if (!(0.0 < _config.minimum_increment &&
              _config.minimum_increment <= _config.initial_increment &&
              _config.initial_increment <= _config.maximum_increment &&
              _config.maximum_increment <= 1.0))
        {
            throw std::invalid_argument("Invalid adaptive construction increments.");
        }
        if (_config.growth_factor < 1.0 || !(_config.cutback_factor > 0.0 &&
                                             _config.cutback_factor < 1.0))
        {
            throw std::invalid_argument("Invalid adaptive construction factors.");
        }
        _increment = _config.initial_increment;
    }

    double beginTrial()
    {
        if (_trial_active)
        {
            throw std::logic_error("Construction trial already active.");
        }
        if (isComplete())
        {
            throw std::logic_error("Construction transition already complete.");
        }
        _trial_coordinate = std::min(1.0, _committed_coordinate + _increment);
        _trial_active = true;
        return _trial_coordinate;
    }

    void acceptTrial()
    {
        requireTrial();
        _committed_coordinate = _trial_coordinate;
        _trial_active = false;
        _increment = std::min(_config.maximum_increment,
                              _increment * _config.growth_factor);
    }

    void rejectTrial()
    {
        requireTrial();
        _trial_coordinate = _committed_coordinate;
        _trial_active = false;
        double const cutback = _increment * _config.cutback_factor;
        if (cutback < _config.minimum_increment)
        {
            throw std::runtime_error(
                "Adaptive construction increment fell below minimum.");
        }
        _increment = cutback;
    }

    double committedCoordinate() const { return _committed_coordinate; }
    double trialCoordinate() const
    {
        if (!_trial_active)
        {
            throw std::logic_error("No active construction trial.");
        }
        return _trial_coordinate;
    }
    double increment() const { return _increment; }
    bool hasActiveTrial() const { return _trial_active; }
    bool isComplete() const { return _committed_coordinate == 1.0; }

private:
    void requireTrial() const
    {
        if (!_trial_active)
        {
            throw std::logic_error("No active construction trial.");
        }
    }

    Config _config;
    double _committed_coordinate = 0.0;
    double _trial_coordinate = 0.0;
    double _increment = 0.0;
    bool _trial_active = false;
};
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

header = root / "ProcessLib/StagedConstruction/MechanicalRemovalTransition.h"
text = header.read_text(encoding="utf-8")
if '#include <optional>\n' not in text:
    text = text.replace('#include <cstddef>\n', '#include <cstddef>\n#include <optional>\n', 1)

old = '''    void setReleaseCoordinate(double const lambda)
    {
        if (lambda < _release_coordinate || lambda > 1.0)
        {
            throw std::out_of_range(
                "Mechanical removal release coordinate must advance monotonically in [0, 1].");
        }
        _release_coordinate = lambda;
    }

    double releaseCoordinate() const { return _release_coordinate; }

    std::vector<double> currentForce() const
    {
        return forceAt(_release_coordinate);
    }

    bool isFullyReleased() const { return _release_coordinate == 1.0; }
'''
new = '''    void setReleaseCoordinate(double const lambda)
    {
        if (_trial_release_coordinate)
        {
            throw std::logic_error(
                "Cannot directly set release coordinate during an active trial.");
        }
        if (lambda < _release_coordinate || lambda > 1.0)
        {
            throw std::out_of_range(
                "Mechanical removal release coordinate must advance monotonically in [0, 1].");
        }
        _release_coordinate = lambda;
    }

    /// Begin a trial release without changing the committed release state.
    void beginTrialRelease(double const lambda)
    {
        if (_trial_release_coordinate)
        {
            throw std::logic_error("Mechanical removal trial already active.");
        }
        if (lambda < _release_coordinate || lambda > 1.0)
        {
            throw std::out_of_range(
                "Mechanical removal trial coordinate must be in [committed, 1].");
        }
        _trial_release_coordinate = lambda;
    }

    void commitTrialRelease()
    {
        if (!_trial_release_coordinate)
        {
            throw std::logic_error("No mechanical removal trial to commit.");
        }
        _release_coordinate = *_trial_release_coordinate;
        _trial_release_coordinate.reset();
    }

    void rollbackTrialRelease()
    {
        if (!_trial_release_coordinate)
        {
            throw std::logic_error("No mechanical removal trial to roll back.");
        }
        _trial_release_coordinate.reset();
    }

    double releaseCoordinate() const { return _release_coordinate; }
    double currentReleaseCoordinate() const
    {
        return _trial_release_coordinate.value_or(_release_coordinate);
    }
    bool hasActiveTrialRelease() const
    {
        return _trial_release_coordinate.has_value();
    }

    std::vector<double> currentForce() const
    {
        return forceAt(currentReleaseCoordinate());
    }

    bool isFullyReleased() const
    {
        return !_trial_release_coordinate && _release_coordinate == 1.0;
    }
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected R2L MechanicalRemovalTransition transaction layout")
text = text.replace(old, new)

old_private = '''    double _release_coordinate = 0.0;
'''
new_private = '''    double _release_coordinate = 0.0;
    std::optional<double> _trial_release_coordinate;
'''
if text.count(old_private) != 1:
    raise RuntimeError("Unexpected R2L release coordinate storage")
header.write_text(text.replace(old_private, new_private), encoding="utf-8")

print("Applied OGS Staged Construction R3A adaptive transactional controller")