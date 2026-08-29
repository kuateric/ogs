# Phase C C1 — EmbeddedBeam + EmbeddedAnchor authority composition

Canonical OGS remains pinned to `adf770974c7ee0435702fe617634d03d17ab7cb8`.

## Frozen structural authority

EmbeddedBeam mechanics are not invented or modified in staged-construction work. C1 consumes the frozen Engineering OS G2 authority exactly at commit `557ce56b6a6dded188dd9b14525ba2fb45f3938a` (PR #109), whose authoritative `OGS-STR-G2 #9` run `32478978367` passed analytical kernel checks, exact-ref OGS checkout, compile, native axial runtime, native finite-EI runtime, and finite-result validation.

The G2 mechanical contract remains frozen: a 2-D three-reference-point translation-based embedded beam, explicit host-to-beam projection `P`, residual `r_h = P^T(-K u_b)`, and Jacobian `J_h = P^T K P`. C1 does not alter those mechanics.

## Staged-construction support semantics

EmbeddedAnchor uses the already-passed C0 placement lifecycle: at its requested activation phase, `Process::preTimestep()` supplies the carried last-converged bulk configuration; that configuration becomes the stress-free birth reference before Newton assembly. Full physical anchor stiffness is active immediately. Prestress remains explicit via `initial_anchor_stress`.

This follows established construction-stage practice: Abaqus `MODEL CHANGE, ADD=STRAIN FREE` uses the current configuration as the new strain-free reference for installed elements, while FLAC3D and PLAXIS separate support installation from explicit pretension/prestress operations. No stiffness homotopy or residual scaling is introduced.

## C1 purpose

C1 is an integration/compatibility gate, not a new structural-element gate. It proves that, on one exact canonical OGS tree and one executable:

1. the passed Anchor stress-free-birth lifecycle patch applies and compiles;
2. the exact frozen G2 EmbeddedBeam stack applies without modification;
3. the real staged Anchor birth E2E still passes;
4. native EmbeddedBeam axial and bending E2Es still pass;
5. no ACTPLAS or unrelated structural-element source is touched.

A later C2 gate will build the single full excavation construction sequence using both support types. C1 must pass first so any C2 failure can be attributed to construction-sequence integration rather than source-term coexistence.
