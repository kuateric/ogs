// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <cstdlib>
#include <string_view>
#include <vector>

#include "BaseLib/Logging.h"

namespace ProcessLib
{
/// Emits the framework-owned active-element state for exact staging evidence.
///
/// This diagnostic is deliberately read-only and disabled by default.  It does
/// not own activation state and must never participate in assembly, nonlinear
/// solution, constitutive update, or commit/rollback decisions.
///
/// The Process framework uses an empty active-element vector as the all-active
/// sentinel.  Therefore the emitter reports that state explicitly instead of
/// interpreting an empty vector as zero active elements.
inline void emitNativeStagingState(
    std::string_view const process_name, double const time,
    int const process_id, std::vector<std::size_t> const& active_element_ids,
    std::size_t const number_of_mesh_elements)
{
    auto const* const enabled = std::getenv("OGS_NATIVE_STAGING_EMITTER");
    if (enabled == nullptr || std::string_view{enabled} != "1")
    {
        return;
    }

    bool const all_active = active_element_ids.empty();
    std::size_t const active_count =
        all_active ? number_of_mesh_elements : active_element_ids.size();

    INFO("NATIVE_STAGING process={:s} process_id={} time={:.17g} "
         "all_active={} active_count={} total_elements={}",
         process_name, process_id, time, all_active, active_count,
         number_of_mesh_elements);
}
}  // namespace ProcessLib
