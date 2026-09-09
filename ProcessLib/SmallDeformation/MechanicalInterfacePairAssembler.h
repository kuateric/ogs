// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <array>

#include "MechanicalInterfaceLaw.h"

namespace ProcessLib::MechanicalInterface
{
struct PairResponse
{
    Response local;
    std::array<double, 2> unit_normal{};
    std::array<double, 2> unit_tangent{};
    std::array<double, 4> residual{};   // [A_x,A_y,B_x,B_y]
    std::array<double, 16> jacobian{};  // row-major 4x4
};

/// Generic small-rotation two-sided pair assembly.
/// Side A and side B are symmetric independent fields; no host/member or
/// tubbing-specific semantics are embedded here.
PairResponse assemblePair(std::array<double, 2> const& u_a,
                          std::array<double, 2> const& u_b,
                          std::array<double, 2> const& normal,
                          double initial_normal_gap,
                          Parameters const& parameters,
                          History const& history);
}  // namespace ProcessLib::MechanicalInterface
