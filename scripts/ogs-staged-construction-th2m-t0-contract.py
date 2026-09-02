#!/usr/bin/env python3
"""Deterministic TH2M staged-construction lifecycle contract gate.

This gate freezes the process-wide lifecycle semantics for TH2M before any
TH2M runtime wiring is changed. It deliberately reuses the validated A4L/HM/
TRM stress-free-birth semantics and extends them to the monolithic TH2M field
set: gas pressure, capillary pressure, temperature, and displacement.

No stiffness, residual, or material homotopy is introduced here. Construction
birth/death is an equilibrium operation at constant physical time.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TH2MPlacementState:
    gas_pressure: float
    capillary_pressure: float
    temperature: float
    displacement_reference: tuple[float, ...]
    fresh_constitutive_state: bool = True

    @property
    def liquid_pressure(self) -> float:
        # TH2M primary pressures are p_g and p_c; p_l is derived.
        return self.gas_pressure - self.capillary_pressure


@dataclass(frozen=True)
class TH2MContributionMask:
    mechanics: bool
    gas_storage_transport: bool
    liquid_storage_transport: bool
    thermal_storage: bool
    heat_conduction: bool
    thermo_hydro_mechanical_coupling: bool

    @classmethod
    def active(cls):
        return cls(True, True, True, True, True, True)

    @classmethod
    def inactive(cls):
        return cls(False, False, False, False, False, False)


def activate(placement: TH2MPlacementState, physical_time_before: float,
             physical_time_after: float) -> TH2MContributionMask:
    assert placement.fresh_constitutive_state
    assert placement.temperature > 0.0
    assert len(placement.displacement_reference) > 0
    # A construction continuation must not advance physical constitutive time.
    assert physical_time_before == physical_time_after
    return TH2MContributionMask.active()


def deactivate(physical_time_before: float,
               physical_time_after: float) -> TH2MContributionMask:
    # True void means no mechanical, gas, liquid, thermal, or coupled TH2M
    # contribution from the inactive element.
    assert physical_time_before == physical_time_after
    return TH2MContributionMask.inactive()


def main() -> None:
    host = TH2MPlacementState(
        gas_pressure=150_000.0,
        capillary_pressure=25_000.0,
        temperature=313.15,
        displacement_reference=(0.0, -2.5e-3),
    )
    assert host.liquid_pressure == 125_000.0
    assert activate(host, 7.0, 7.0) == TH2MContributionMask.active()
    assert deactivate(8.0, 8.0) == TH2MContributionMask.inactive()

    # Backfill placement state is explicit and independent of the removed host.
    backfill = TH2MPlacementState(
        gas_pressure=110_000.0,
        capillary_pressure=30_000.0,
        temperature=293.15,
        displacement_reference=(1.0e-3, -3.0e-3),
    )
    assert backfill.gas_pressure != host.gas_pressure
    assert backfill.capillary_pressure != host.capillary_pressure
    assert backfill.temperature != host.temperature
    assert backfill.displacement_reference != host.displacement_reference
    assert backfill.fresh_constitutive_state

    # Repeated equilibrium continuation is permitted without fictitious time.
    for _ in range(4):
        mask = activate(backfill, 10.0, 10.0)
        assert mask.mechanics
        assert mask.gas_storage_transport
        assert mask.liquid_storage_transport
        assert mask.thermal_storage
        assert mask.heat_conduction
        assert mask.thermo_hydro_mechanical_coupling

    print("TH2M-T0 coupled lifecycle contract PASS")


if __name__ == "__main__":
    main()
