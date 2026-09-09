// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#include "MechanicalInterfacePairRegistry.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <unordered_set>

namespace ProcessLib::MechanicalInterface
{
std::vector<BoundaryPair> buildGeometricPairRegistry(
    std::vector<BoundaryNode> const& side_a,
    std::vector<BoundaryNode> const& side_b,
    double const tolerance)
{
    if (!(tolerance > 0.0) || !std::isfinite(tolerance))
    {
        throw std::invalid_argument("Mechanical interface pairing requires a finite positive tolerance.");
    }
    if (side_a.empty() || side_b.empty())
    {
        throw std::invalid_argument("Mechanical interface pairing requires non-empty Side A and Side B boundaries.");
    }
    if (side_a.size() != side_b.size())
    {
        throw std::invalid_argument("G5-V1 conforming interface pairing requires equal node counts on Side A and Side B.");
    }

    std::unordered_set<std::size_t> a_ids;
    std::unordered_set<std::size_t> b_ids;
    for (auto const& n : side_a)
    {
        if (!a_ids.insert(n.id).second)
        {
            throw std::invalid_argument("Duplicate Side A node id in mechanical interface boundary.");
        }
    }
    for (auto const& n : side_b)
    {
        if (!b_ids.insert(n.id).second)
        {
            throw std::invalid_argument("Duplicate Side B node id in mechanical interface boundary.");
        }
    }

    std::unordered_set<std::size_t> used_b;
    std::vector<BoundaryPair> pairs;
    pairs.reserve(side_a.size());

    for (auto const& a : side_a)
    {
        double best_distance = std::numeric_limits<double>::infinity();
        std::size_t best_b_id = 0;
        int candidates_at_best = 0;

        for (auto const& b : side_b)
        {
            double const dx = a.x - b.x;
            double const dy = a.y - b.y;
            double const distance = std::hypot(dx, dy);
            if (distance > tolerance)
            {
                continue;
            }

            double const eps = 1e-14 * std::max(1.0, tolerance);
            if (distance + eps < best_distance)
            {
                best_distance = distance;
                best_b_id = b.id;
                candidates_at_best = 1;
            }
            else if (std::abs(distance - best_distance) <= eps)
            {
                ++candidates_at_best;
            }
        }

        if (!std::isfinite(best_distance))
        {
            throw std::runtime_error("No Side B node found within tolerance for a Side A interface node.");
        }
        if (candidates_at_best != 1)
        {
            throw std::runtime_error("Ambiguous Side A/Side B geometric interface pairing.");
        }
        if (!used_b.insert(best_b_id).second)
        {
            throw std::runtime_error("Mechanical interface pairing is not bijective: a Side B node was matched more than once.");
        }

        pairs.push_back({a.id, best_b_id, best_distance});
    }

    if (used_b.size() != side_b.size())
    {
        throw std::runtime_error("Mechanical interface pairing is not bijective: unmatched Side B node remains.");
    }

    std::sort(pairs.begin(), pairs.end(),
              [](BoundaryPair const& lhs, BoundaryPair const& rhs)
              { return lhs.side_a_id < rhs.side_a_id; });
    return pairs;
}
}  // namespace ProcessLib::MechanicalInterface
