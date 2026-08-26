#!/usr/bin/env python3
"""Deterministic HM staged-construction contract gate.

This gate intentionally freezes coupled lifecycle semantics before runtime
wiring.  It is solver-neutral and does not modify the canonical OGS sources.
Runtime integration follows only after this contract passes.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class HMPlacementState:
    liquid_pressure: float
    displacement_reference: tuple[float, ...]
    fresh_constitutive_state: bool = True


@dataclass(frozen=True)
class HMContributionMask:
    mechanics: bool
    storage: bool
    darcy_flux: bool
    biot_coupling: bool

    @classmethod
    def active(cls):
        return cls(True, True, True, True)

    @classmethod
    def inactive(cls):
        return cls(False, False, False, False)


def activate(placement: HMPlacementState, physical_time_before: float,
             physical_time_after: float) -> HMContributionMask:
    assert placement.fresh_constitutive_state
    assert len(placement.displacement_reference) > 0
    # Construction birth is an equilibrium operation, not a physical-time step.
    assert physical_time_before == physical_time_after
    return HMContributionMask.active()


def deactivate(physical_time_before: float,
               physical_time_after: float) -> HMContributionMask:
    # All HM operators leave the active domain together.
    assert physical_time_before == physical_time_after
    return HMContributionMask.inactive()


def main() -> None:
    birth = HMPlacementState(
        liquid_pressure=125_000.0,
        displacement_reference=(0.0, -2.5e-3),
    )
    mask = activate(birth, 7.0, 7.0)
    assert mask == HMContributionMask(True, True, True, True)

    void = deactivate(9.0, 9.0)
    assert void == HMContributionMask(False, False, False, False)

    # Material replacement must not inherit the previous hydraulic placement.
    replacement = HMPlacementState(
        liquid_pressure=80_000.0,
        displacement_reference=(1.0e-3, -3.0e-3),
    )
    assert replacement.liquid_pressure != birth.liquid_pressure
    assert replacement.fresh_constitutive_state

    # Construction substeps may repeat at the same physical time.
    for _ in range(4):
        assert activate(replacement, 10.0, 10.0).darcy_flux

    print("HM-B0 coupled lifecycle contract PASS")


if __name__ == "__main__":
    main()
