// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <array>
#include <cstdint>

namespace ProcessLib::MechanicalInterface
{
enum class ContactState : std::uint8_t
{
    OPEN = 0,
    STICK = 1,
    SLIP = 2
};

struct Parameters
{
    double k_n;
    double k_t;
    double mu;
};

struct History
{
    double plastic_slip = 0.0;
};

struct Response
{
    double normal_gap = 0.0;          // positive = opening, negative = compression
    double tangential_slip = 0.0;     // total relative tangential displacement
    double normal_traction = 0.0;      // negative = compression
    double tangential_traction = 0.0;
    ContactState state = ContactState::OPEN;
    History updated_history{};

    // Algorithmic tangent d[t_n,t_t]/d[g_n,s_t].
    // Row-major: [dtn/dgn, dtn/dst, dtt/dgn, dtt/dst].
    std::array<double, 4> tangent{{0.0, 0.0, 0.0, 0.0}};
};

/// Small-rotation, two-sided mechanical interface reference law for G5-V1.
///
/// The local normal/tangential basis and two-field kinematics are owned by the
/// interface assembler. This constitutive kernel deliberately receives only
/// local relative kinematics (g_n, s_t) so that it can be reused for arbitrary
/// side A / side B structural pairs and later replaced by an MFront law without
/// moving contact kinematics or assembly out of OGS.
Response evaluate(double normal_gap,
                  double tangential_slip,
                  Parameters const& parameters,
                  History const& history);

char const* toString(ContactState state);
}  // namespace ProcessLib::MechanicalInterface
