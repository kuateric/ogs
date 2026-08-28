# TH2M-T2A — Literature basis for stress-free fresh birth

Canonical OGS authority: `adf770974c7ee0435702fe617634d03d17ab7cb8`.

## Established method followed

The Phase-B TH2M fresh-birth design follows the established **strain-free / stress-free element reactivation** family used in staged-construction FEM, not an ersatz low-stiffness birth/death method.

1. **Abaqus MODEL CHANGE / strain-free reactivation.** Reintroduced elements use the configuration at reactivation as their stress-free reference and return with their physical constitutive response. This motivates capturing the last converged displacement as `u_birth` and evaluating birth-step mechanical strain relative to that reference.
2. **PLAXIS staged construction / reset semantics.** Construction phases may activate/deactivate clusters while constitutive history can be reset so soil behaves as virgin material. This supports treating geometric placement state and constitutive history as separate lifecycle concerns.
3. **Stress-free-state staged-construction theory.** The installed element's stress-free geometry is an explicit state variable; stage equilibrium follows from the physical operator and the change in construction state. This supports solving construction-induced disequilibrium instead of scaling stiffness/residuals toward zero.

## OGS TH2M mapping

The pinned TH2M local assembler already separates:

- `current_states_` and `prev_states_` for coupled TH2M state,
- `material_states_` for solid constitutive history,
- `initializeInternalStateVariables()` for a fresh material-law-neutral constitutive state,
- `pushBackState()` for committing the constitutive baseline,
- current and previous displacement arguments entering the mechanical-strain update.

Therefore T2B must implement fresh birth by using those ownership boundaries:

- capture the last converged displacement at activation as `u_birth`;
- use `u-u_birth` for constitutive kinematics;
- use zero previous mechanical strain in birth-relative coordinates for the first active equilibrium solve;
- initialize a fresh solid material state through the existing constitutive interface, including MFront/MGIS state variables;
- set zero birth effective stress unless an explicit placement stress is supplied;
- preserve explicit placement values for `p_g`, `p_c`, and `T`;
- assemble the full physical TH2M operator from the first active iteration;
- solve only the resulting global construction disequilibrium at constant physical time.

## Explicitly rejected mechanisms

T2B must not introduce stiffness scaling, residual scaling, material-parameter homotopy, constitutive-state reuse from the pre-deactivation material, or implicit zeroing of thermodynamic placement variables.

## Gate sequence

`T2A` freezes the canonical state-ownership contract. `T2B` is the first runtime fresh-birth implementation and must prove a zero-stress/virgin constitutive birth. A subsequent MFront/MGIS gate must demonstrate that state-variable history is genuinely fresh rather than merely zeroing reported stress.
