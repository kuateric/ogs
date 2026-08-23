#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
header = root / "ProcessLib/StagedConstruction/ActivationPlacementState.h"
header.parent.mkdir(parents=True, exist_ok=True)
header.write_text(r'''// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <cstddef>
#include <stdexcept>
#include <utility>
#include <vector>

namespace ProcessLib::StagedConstruction
{
/// Defines the state that a newly activated material region starts from.
/// Activation must never reuse the constitutive history of a previously
/// deactivated region implicitly.  Process-specific primary variables are
/// supplied separately by the owning process.
class ActivationPlacementState
{
public:
    enum class ConstitutiveStatePolicy
    {
        fresh_material_state
    };

    explicit ActivationPlacementState(
        std::vector<std::size_t> newly_activated_element_ids,
        ConstitutiveStatePolicy const constitutive_state_policy =
            ConstitutiveStatePolicy::fresh_material_state)
        : _newly_activated_element_ids(
              std::move(newly_activated_element_ids)),
          _constitutive_state_policy(constitutive_state_policy)
    {
        if (_newly_activated_element_ids.empty())
        {
            throw std::invalid_argument(
                "Activation placement state requires at least one newly "
                "activated element.");
        }
    }

    std::vector<std::size_t> const& newlyActivatedElementIDs() const
    {
        return _newly_activated_element_ids;
    }

    ConstitutiveStatePolicy constitutiveStatePolicy() const
    {
        return _constitutive_state_policy;
    }

private:
    std::vector<std::size_t> _newly_activated_element_ids;
    ConstitutiveStatePolicy _constitutive_state_policy;
};

inline ActivationPlacementState makeActivationPlacementState(
    DomainTransition const& transition)
{
    if (transition.newly_activated_element_ids.empty())
    {
        throw std::invalid_argument(
            "Domain transition does not contain an activation event.");
    }

    return ActivationPlacementState{
        transition.newly_activated_element_ids,
        ActivationPlacementState::ConstitutiveStatePolicy::fresh_material_state};
}
}  // namespace ProcessLib::StagedConstruction
''', encoding="utf-8")

# Ensure the header is self-contained after the R0 patch creates DomainLifecycle.
text = header.read_text(encoding="utf-8")
needle = '#include <vector>\n'
replacement = '#include <vector>\n\n#include "DomainLifecycle.h"\n'
if text.count(needle) != 1:
    raise RuntimeError("Unexpected ActivationPlacementState include layout")
header.write_text(text.replace(needle, replacement), encoding="utf-8")

print("Applied OGS Staged Construction A0 activation placement-state contract")

# CI-only synchronization marker for A2 full-backfill validation; no mechanics change.
