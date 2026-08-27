# OGS Staged Construction HM-B0 — Literature-backed lifecycle semantics

Canonical OGS authority remains pinned to:

`adf770974c7ee0435702fe617634d03d17ab7cb8`

## Frozen HM-B0 rules

1. Activation/placement is a construction operation at unchanged physical time.
2. A newly activated HM domain owns an explicit placement state containing at least the displacement birth/reference configuration and liquid pressure.
3. Constitutive state is fresh on material replacement; stale pre-excavation MFront/MGIS history is forbidden.
4. An active HM element contributes the coupled mechanical operator, hydraulic storage, Darcy flux and Biot coupling together.
5. A deactivated/void HM element contributes none of those operators.
6. Runtime implementation must preserve A4L mechanics semantics: stress-free birth in the current converged configuration with the full physical material operator; do not introduce stiffness scaling toward zero.

## External precedent used

- PLAXIS staged construction treats groundwater/pore-pressure conditions as phase-owned state and staged excavation/dewatering as a coupled phase change. This supports explicit hydraulic placement/phase state rather than inherited hidden history.
- FLAC3D 9.1 documents that zone null status applies to mechanical, thermal and fluid processes; process-specific inactive/null fluid/thermal models are required only when deliberately decoupling those processes. This supports an all-HM-contributions-off default for excavation voids.
- Abaqus coupled pore-pressure elements carry displacement and pore-pressure degrees of freedom in one porous-medium formulation. This supports treating activation as a coupled-domain birth rather than activating mechanics while silently retaining hydraulic storage/flux.

These references guide the architecture only. HM runtime PASS requires an executed deterministic OGS E2E; this B0 gate is a contract gate and must not be reported as runtime completion.
