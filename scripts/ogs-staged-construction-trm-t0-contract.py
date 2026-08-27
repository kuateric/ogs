#!/usr/bin/env python3
"""Deterministic TRM staged-construction contract gate.

This gate freezes the process-wide lifecycle semantics for
THERMO_RICHARDS_MECHANICS before any TRM runtime wiring is changed.
It deliberately reuses the validated HM birth semantics and adds the
thermal placement state/operator scope.  It is solver-neutral and does not
modify the canonical OGS source pinned by the companion scope evidence.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TRMPlacementState:
    liquid_pressure: float
    temperature: float
    displacement_reference: tuple[float, ...]
    fresh_constitutive_state: bool = True


@dataclass(frozen=True)
class TRMContributionMask:
    mechanics: bool
    storage: bool
    darcy_flux: bool
    thermal_storage: bool
    heat_conduction: bool
    thm_coupling: bool

    @classmethod
    def active(cls):
        return cls(True, True, True, True, True, True)

    @classmethod
    def inactive(cls):
        return cls(False, False, False, False, False, False)


def activate(placement: TRMPlacementState, physical_time_before: float,
             physical_time_after: float) -> TRMContributionMask:
    assert placement.fresh_constitutive_state
    assert len(placement.displacement_reference) > 0
    assert placement.temperature > 0.0
    # Construction birth is an equilibrium operation, not a physical-time step.
    assert physical_time_before == physical_time_after
    return TRMContributionMask.active()


def deactivate(physical_time_before: float,
               physical_time_after: float) -> TRMContributionMask:
    # A true TRM void removes the whole monolithic T-p-u operator together.
    assert physical_time_before == physical_time_after
    return TRMContributionMask.inactive()


def main() -> None:
    birth = TRMPlacementState(
        liquid_pressure=125_000.0,
        temperature=313.15,
        displacement_reference=(0.0, -2.5e-3),
    )
    mask = activate(birth, 7.0, 7.0)
    assert mask == TRMContributionMask(True, True, True, True, True, True)

    void = deactivate(9.0, 9.0)
    assert void == TRMContributionMask(False, False, False, False, False, False)

    # Backfill may be born with a different hydraulic and thermal placement
    # state; neither value is inherited from the removed host material.
    replacement = TRMPlacementState(
        liquid_pressure=80_000.0,
        temperature=293.15,
        displacement_reference=(1.0e-3, -3.0e-3),
    )
    assert replacement.liquid_pressure != birth.liquid_pressure
    assert replacement.temperature != birth.temperature
    assert replacement.fresh_constitutive_state

    # Construction continuation may repeat without advancing physical time.
    for _ in range(4):
        active = activate(replacement, 10.0, 10.0)
        assert active.darcy_flux
        assert active.heat_conduction
        assert active.thm_coupling

    print("TRM-T0 coupled lifecycle contract PASS")


if __name__ == "__main__":
    main()
