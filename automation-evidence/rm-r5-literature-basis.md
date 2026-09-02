# RM-R5 — MFront/MGIS cross-behaviour hardening basis

Authority pin: `adf770974c7ee0435702fe617634d03d17ab7cb8`.

## Contract

RM-R5 is not inherited from HM/TRM and is not satisfied by changing only parameters of one MFront behaviour. The authoritative runtime must cross an actual MFront/MGIS behaviour boundary during `RM_A -> void -> RM_B`.

The test pair is deliberately schema-distinct and already present in the pinned OGS MFront behaviour library:

- `RM_A`: `StandardElasticityBrick` (standard elasticity behaviour),
- `RM_B`: `MohrCoulombAbboSloan`, which declares the additional state variable `lam` with glossary name `EquivalentPlasticStrain`.

MGIS owns material state according to the loaded behaviour; therefore a constitutive rebind must be followed by allocation/initialization of state for the new behaviour. Reusing the old behaviour's state across this boundary is not admissible.

The already-authoritative RM-R2/R4 ordering is retained:

1. lifecycle transition `inactive -> active`,
2. material id reassignment,
3. constitutive relation rebind to `RM_B`,
4. fresh material-state allocation/initialization for `RM_B`,
5. stress-free mechanical birth and explicit hydraulic placement state `p_L0`,
6. full RichardsMechanics equilibrium at the physical target time.

No stiffness scaling, residual homotopy, material homotopy, or construction pseudo-time is permitted.

## Runtime evidence required for PASS

- exact canonical OGS SHA,
- both distinct MFront behaviour names in the executed project,
- static pinned-source evidence that the behaviours are distinct and that `RM_B` declares `EquivalentPlasticStrain`,
- actual `material 1 -> material 0` activation and constitutive rebind,
- fresh RM material state after the rebind,
- stress-free birth plus explicit `p_L0`,
- successful MFront/MGIS integration after the cross-behaviour birth,
- full physical RM solve with the established four-step A2 schedule and zero rejected steps,
- no homotopy/scaling mechanism.

This gate is intentionally stronger than HM-B7, whose authoritative case uses `MohrCoulombAbboSloan` on both sides with different parameters.