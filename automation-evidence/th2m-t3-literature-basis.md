# TH2M-T3 — Loaded construction-equilibrium restoration

Canonical OGS authority: `adf770974c7ee0435702fe617634d03d17ab7cb8`

## Established staged-construction semantics

- Abaqus/Standard model change supports element deactivation/reactivation; stress-free reactivation treats the current deformed configuration as the reference for newly added elements. The documented tunnel-liner/gravity-dam use case is the direct construction analogue.
- Abaqus verification distinguishes strain-free reactivation from reactivation-with-strain and then applies ordinary physical loading to the reactivated body.
- FLAC3D null zones are absent from the active calculation and can later be un-nulled/reassigned. Nulling sets stress to zero. Current FLAC3D documentation states that null status applies to mechanical, thermal, and fluid processes together.
- FLAC3D also offers a separate relaxation mechanism that deliberately scales stiffness/stress/density. TH2M-T3 does **not** adopt that mechanism; the Engineering OS staged-construction contract requires the full physical operator immediately after birth.

## TH2M-T3 contract

T2A–T2D already establish synchronized p_g / p_c / T / displacement lifecycle and fresh stress-free constitutive/MFront-MGIS birth. T3 adds only the loaded construction-equilibrium requirement:

1. At `inactive -> active`, capture the already-proven fresh placement state: last-converged displacement reference, explicit gas-pressure placement state, explicit capillary-pressure placement state, explicit temperature placement state, and fresh constitutive state.
2. Restore equilibrium with the normal monolithic TH2M residual/Jacobian: mechanics, gas transport/storage, liquid transport/storage, thermal storage/conduction, and all THM couplings remain active.
3. Construction restoration occurs at the same physical target time. Newton iterations are nonlinear equilibrium iterations, not additional physical timesteps.
4. No stiffness scaling, residual scaling/homotopy, material interpolation/homotopy, or artificial construction pseudo-time is permitted.
5. PASS requires authoritative runtime evidence showing a reactivation event followed by a non-zero equilibrium correction and convergence of the unmodified full physical operator.

This gate is intentionally independent of HM/TRM PASS status. Those branches are architectural precedent only; TH2M requires its own runtime evidence.
