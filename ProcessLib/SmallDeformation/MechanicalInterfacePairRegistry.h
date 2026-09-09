// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <cstddef>
#include <vector>

namespace ProcessLib::MechanicalInterface
{
struct BoundaryNode
{
    std::size_t id;
    double x;
    double y;
};

struct BoundaryPair
{
    std::size_t side_a_id;
    std::size_t side_b_id;
    double distance;
};

/// Deterministic conforming geometric pairing for two independent interface
/// boundaries. Node ids are intentionally allowed to differ; this is required
/// for two disconnected continuum segments that occupy coincident geometry.
///
/// V1 accepts only a unique one-to-one match within `tolerance`. Ambiguous,
/// missing, duplicate or non-bijective matches are rejected rather than being
/// silently converted into a non-conforming projection.
std::vector<BoundaryPair> buildGeometricPairRegistry(
    std::vector<BoundaryNode> const& side_a,
    std::vector<BoundaryNode> const& side_b,
    double tolerance);
}  // namespace ProcessLib::MechanicalInterface
