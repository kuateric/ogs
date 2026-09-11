#pragma once

// Project-scale integration helper for frozen G5 mechanics.
// This file does not modify the frozen MechanicalInterface constitutive law.
namespace ProcessLib::SmallDeformation::G5ProjectScale
{
/// Fail-closed assembly admission: inactive elements must return before any
/// constitutive/history evaluation or residual/Jacobian accumulation.
/// Kept as a tiny pure helper so the call-site patch can be audited separately.
constexpr bool assembleElement(bool const active) noexcept
{
    return active;
}
}  // namespace ProcessLib::SmallDeformation::G5ProjectScale
