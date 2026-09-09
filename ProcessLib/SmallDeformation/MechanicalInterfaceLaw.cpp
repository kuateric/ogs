// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#include "MechanicalInterfaceLaw.h"

#include <cmath>
#include <limits>
#include <stdexcept>

namespace ProcessLib::MechanicalInterface
{
namespace
{
void validate(Parameters const& p)
{
    if (!std::isfinite(p.k_n) || !std::isfinite(p.k_t) ||
        !std::isfinite(p.mu) || p.k_n <= 0.0 || p.k_t <= 0.0 ||
        p.mu < 0.0)
    {
        throw std::invalid_argument(
            "G5-V1 interface parameters require finite k_n>0, k_t>0, mu>=0.");
    }
}

double signNonZero(double const value)
{
    return value < 0.0 ? -1.0 : 1.0;
}
}  // namespace

Response evaluate(double const normal_gap,
                  double const tangential_slip,
                  Parameters const& p,
                  History const& history)
{
    validate(p);
    if (!std::isfinite(normal_gap) || !std::isfinite(tangential_slip) ||
        !std::isfinite(history.plastic_slip))
    {
        throw std::invalid_argument("G5-V1 interface state must be finite.");
    }

    Response r;
    r.normal_gap = normal_gap;
    r.tangential_slip = tangential_slip;
    r.updated_history = history;

    // Compression-only unilateral contact. Opening carries no tensile normal
    // traction and, in V1, no tangential traction either.
    if (normal_gap >= 0.0)
    {
        r.state = ContactState::OPEN;
        return r;
    }

    r.normal_traction = p.k_n * normal_gap;  // < 0 in compression
    double const elastic_slip = tangential_slip - history.plastic_slip;
    double const trial_t = p.k_t * elastic_slip;
    double const friction_limit = p.mu * (-r.normal_traction);

    if (std::abs(trial_t) <= friction_limit)
    {
        r.state = ContactState::STICK;
        r.tangential_traction = trial_t;
        r.tangent = {{p.k_n, 0.0, 0.0, p.k_t}};
        return r;
    }

    // Return to Coulomb surface. This is the semismooth branch tangent for a
    // fixed slip direction. At the exact switching point the generalized
    // derivative is non-unique; either adjacent branch is admissible.
    r.state = ContactState::SLIP;
    double const direction = signNonZero(trial_t);
    r.tangential_traction = direction * friction_limit;
    r.updated_history.plastic_slip =
        tangential_slip - r.tangential_traction / p.k_t;
    r.tangent = {{p.k_n, 0.0, -direction * p.mu * p.k_n, 0.0}};
    return r;
}

char const* toString(ContactState const state)
{
    switch (state)
    {
        case ContactState::OPEN:
            return "OPEN";
        case ContactState::STICK:
            return "STICK";
        case ContactState::SLIP:
            return "SLIP";
    }
    return "UNKNOWN";
}
}  // namespace ProcessLib::MechanicalInterface
