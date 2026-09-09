// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#include "MechanicalInterfacePairAssembler.h"

#include <cmath>
#include <stdexcept>

namespace ProcessLib::MechanicalInterface
{
PairResponse assemblePair(std::array<double, 2> const& u_a,
                          std::array<double, 2> const& u_b,
                          std::array<double, 2> const& normal,
                          double const initial_normal_gap,
                          Parameters const& parameters,
                          History const& history)
{
    double const norm = std::hypot(normal[0], normal[1]);
    if (!std::isfinite(norm) || norm <= 0.0 ||
        !std::isfinite(initial_normal_gap))
    {
        throw std::invalid_argument("G5-V1 pair requires a finite non-zero normal and finite initial gap.");
    }

    PairResponse out;
    out.unit_normal = {{normal[0] / norm, normal[1] / norm}};
    out.unit_tangent = {{-out.unit_normal[1], out.unit_normal[0]}};

    std::array<double, 2> const du{{u_b[0] - u_a[0], u_b[1] - u_a[1]}};
    double const gn = initial_normal_gap + du[0] * out.unit_normal[0] +
                      du[1] * out.unit_normal[1];
    double const st = du[0] * out.unit_tangent[0] +
                      du[1] * out.unit_tangent[1];

    out.local = evaluate(gn, st, parameters, history);

    double const B[2][4] = {
        {-out.unit_normal[0], -out.unit_normal[1], out.unit_normal[0], out.unit_normal[1]},
        {-out.unit_tangent[0], -out.unit_tangent[1], out.unit_tangent[0], out.unit_tangent[1]}};
    double const traction[2] = {out.local.normal_traction,
                                out.local.tangential_traction};
    double const D[2][2] = {{out.local.tangent[0], out.local.tangent[1]},
                            {out.local.tangent[2], out.local.tangent[3]}};

    for (int i = 0; i < 4; ++i)
    {
        out.residual[i] = B[0][i] * traction[0] + B[1][i] * traction[1];
        for (int j = 0; j < 4; ++j)
        {
            double kij = 0.0;
            for (int a = 0; a < 2; ++a)
                for (int b = 0; b < 2; ++b)
                    kij += B[a][i] * D[a][b] * B[b][j];
            out.jacobian[4 * i + j] = kij;
        }
    }

    return out;
}
}  // namespace ProcessLib::MechanicalInterface
