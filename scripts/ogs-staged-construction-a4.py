#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
header = root / "ProcessLib/StagedConstruction/ActivationPlacementState.h"
text = header.read_text(encoding="utf-8")

old_includes = '''#include <cstddef>\n#include <stdexcept>\n#include <utility>\n#include <vector>\n'''
new_includes = '''#include <cstddef>\n#include <optional>\n#include <stdexcept>\n#include <utility>\n#include <vector>\n'''
if text.count(old_includes) != 1:
    raise RuntimeError("Unexpected ActivationPlacementState include layout")
text = text.replace(old_includes, new_includes)

old_enum = '''    enum class ConstitutiveStatePolicy\n    {\n        fresh_material_state\n    };\n\n'''
new_enum = '''    enum class ConstitutiveStatePolicy\n    {\n        fresh_material_state\n    };\n\n    /// Controls how a newly placed region enters the assembled equations.\n    /// `adaptive_continuation` means the region is introduced through a\n    /// construction coordinate at unchanged physical time instead of as one\n    /// instantaneous full-load jump.\n    enum class ActivationLoadingPolicy\n    {\n        instantaneous,\n        adaptive_continuation\n    };\n\n    /// Solver-neutral placement values.  Individual processes consume only\n    /// the fields they own.  This keeps staged construction independent from\n    /// SmallDeformation/HM/TRM/TH2M while still making the initial placement\n    /// state explicit and auditable.\n    struct PlacementFields\n    {\n        std::optional<double> liquid_pressure;\n        std::optional<double> gas_pressure;\n        std::optional<double> temperature;\n        std::optional<double> liquid_saturation;\n        std::optional<double> porosity;\n    };\n\n'''
if text.count(old_enum) != 1:
    raise RuntimeError("Unexpected ActivationPlacementState enum layout")
text = text.replace(old_enum, new_enum)

old_ctor = '''    explicit ActivationPlacementState(\n        std::vector<std::size_t> newly_activated_element_ids,\n        ConstitutiveStatePolicy const constitutive_state_policy =\n            ConstitutiveStatePolicy::fresh_material_state)\n        : _newly_activated_element_ids(\n              std::move(newly_activated_element_ids)),\n          _constitutive_state_policy(constitutive_state_policy)\n'''
new_ctor = '''    explicit ActivationPlacementState(\n        std::vector<std::size_t> newly_activated_element_ids,\n        ConstitutiveStatePolicy const constitutive_state_policy =\n            ConstitutiveStatePolicy::fresh_material_state,\n        ActivationLoadingPolicy const activation_loading_policy =\n            ActivationLoadingPolicy::adaptive_continuation,\n        PlacementFields placement_fields = {})\n        : _newly_activated_element_ids(\n              std::move(newly_activated_element_ids)),\n          _constitutive_state_policy(constitutive_state_policy),\n          _activation_loading_policy(activation_loading_policy),\n          _placement_fields(std::move(placement_fields))\n'''
if text.count(old_ctor) != 1:
    raise RuntimeError("Unexpected ActivationPlacementState constructor layout")
text = text.replace(old_ctor, new_ctor)

old_access = '''    ConstitutiveStatePolicy constitutiveStatePolicy() const\n    {\n        return _constitutive_state_policy;\n    }\n\nprivate:\n'''
new_access = '''    ConstitutiveStatePolicy constitutiveStatePolicy() const\n    {\n        return _constitutive_state_policy;\n    }\n\n    ActivationLoadingPolicy activationLoadingPolicy() const\n    {\n        return _activation_loading_policy;\n    }\n\n    PlacementFields const& placementFields() const\n    {\n        return _placement_fields;\n    }\n\nprivate:\n'''
if text.count(old_access) != 1:
    raise RuntimeError("Unexpected ActivationPlacementState accessor layout")
text = text.replace(old_access, new_access)

old_members = '''    std::vector<std::size_t> _newly_activated_element_ids;\n    ConstitutiveStatePolicy _constitutive_state_policy;\n};\n'''
new_members = '''    std::vector<std::size_t> _newly_activated_element_ids;\n    ConstitutiveStatePolicy _constitutive_state_policy;\n    ActivationLoadingPolicy _activation_loading_policy;\n    PlacementFields _placement_fields;\n};\n'''
if text.count(old_members) != 1:
    raise RuntimeError("Unexpected ActivationPlacementState member layout")
text = text.replace(old_members, new_members)

old_factory = '''    return ActivationPlacementState{\n        transition.newly_activated_element_ids,\n        ActivationPlacementState::ConstitutiveStatePolicy::fresh_material_state};\n'''
new_factory = '''    return ActivationPlacementState{\n        transition.newly_activated_element_ids,\n        ActivationPlacementState::ConstitutiveStatePolicy::fresh_material_state,\n        ActivationPlacementState::ActivationLoadingPolicy::adaptive_continuation};\n'''
if text.count(old_factory) != 1:
    raise RuntimeError("Unexpected ActivationPlacementState factory layout")
text = text.replace(old_factory, new_factory)
header.write_text(text, encoding="utf-8")

# Add a small process-neutral activation continuation primitive.  Runtime
# process coupling will consume this in the next A4 gate; this first patch
# freezes monotonicity/cutback semantics independently from any one process.
cont = root / "ProcessLib/StagedConstruction/ActivationTransition.h"
cont.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <algorithm>
#include <stdexcept>

namespace ProcessLib::StagedConstruction
{
class ActivationTransition
{
public:
    explicit ActivationTransition(double initial_step = 0.25,
                                  double minimum_step = 1e-4,
                                  double growth = 1.5,
                                  double cutback = 0.5)
        : _step(initial_step),
          _minimum_step(minimum_step),
          _growth(growth),
          _cutback(cutback)
    {
        if (!(initial_step > 0.0 && initial_step <= 1.0) ||
            !(minimum_step > 0.0 && minimum_step <= initial_step) ||
            !(growth >= 1.0) || !(cutback > 0.0 && cutback < 1.0))
        {
            throw std::invalid_argument("Invalid activation continuation parameters.");
        }
    }

    bool complete() const { return _lambda >= 1.0; }
    double committedLambda() const { return _lambda; }

    double beginTrial()
    {
        if (_trial_open || complete())
        {
            throw std::logic_error("Invalid activation trial state.");
        }
        _trial_lambda = std::min(1.0, _lambda + _step);
        _trial_open = true;
        return _trial_lambda;
    }

    void acceptTrial()
    {
        if (!_trial_open)
        {
            throw std::logic_error("No activation trial is open.");
        }
        _lambda = _trial_lambda;
        _trial_open = false;
        _step = std::min(1.0 - _lambda, _step * _growth);
    }

    void rejectTrial()
    {
        if (!_trial_open)
        {
            throw std::logic_error("No activation trial is open.");
        }
        _trial_open = false;
        _step *= _cutback;
        if (_step < _minimum_step)
        {
            throw std::runtime_error("Activation continuation exhausted minimum step size.");
        }
    }

private:
    double _lambda = 0.0;
    double _trial_lambda = 0.0;
    double _step;
    double _minimum_step;
    double _growth;
    double _cutback;
    bool _trial_open = false;
};
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

print("Applied OGS Staged Construction A4 explicit placement-state and controlled activation contract")
