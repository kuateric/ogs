# RM-R2 literature basis — stress-free hydraulic/mechanical birth

Canonical OGS target: `adf770974c7ee0435702fe617634d03d17ab7cb8`.

RM-R2 follows established staged-construction semantics rather than introducing a numerical weakening mechanism:

- **Abaqus MODEL CHANGE / strain-free reactivation**: reactivated material is treated from the current configuration as its new strain-free reference, with the physical element stiffness present on reactivation rather than stiffness ramping from an artificial near-zero value.
- **PLAXIS staged construction / Reset displacements and Reset state variables**: a new phase may discard displacement history for the phase while keeping stress semantics explicit; advanced soil state variables can be reset so material behaves as virgin soil. This motivates separate treatment of geometry/reference configuration, stress, and constitutive history.
- **FLAC3D sequential excavation/construction semantics**: null zones are mechanically absent; newly assigned/activated zones are reintroduced with a constitutive model and state appropriate to the new construction stage, then global equilibrium is restored.
- **Stress-free-state staged-construction theory**: the installed element's stress-free configuration is an explicit construction-state variable; equilibrium is solved for the construction-induced disequilibrium.

Chosen RM-R2 contract:

1. `u_birth = u_last_converged` for each newly activated element.
2. Mechanical strain is evaluated relative to `u_birth` during and after birth.
3. Effective birth stress is zero unless an explicit placement stress is supplied.
4. Material state is recreated from the selected constitutive relation via `createMaterialStateVariables()`, then initialized through `initializeInternalStateVariables()` and committed once with `pushBackState()`; no stale MFront/MGIS history may survive a void interval.
5. Richards liquid pressure placement is explicit as `p_L0`; it is not silently inferred from zero. The scalar placement state is imposed consistently on current and previous hydraulic state at birth.
6. The full physical RM pressure/displacement operator is active immediately. Forbidden: stiffness scaling, residual homotopy, material homotopy.
7. Any construction equilibrium continuation holds physical time fixed and solves only the global disequilibrium caused by the topology/material-state change.

Primary references consulted before implementation:

- Abaqus documentation, Model Change / element removal and reactivation semantics.
- Bentley PLAXIS documentation, Reset displacements to zero / Reset state variables and staged construction phases.
- Itasca FLAC3D documentation, null constitutive model and sequential construction modelling.
- Stress-free-state based structural analysis and construction control theory for staged construction bridges, *Advances in Bridge Engineering* (2020), DOI 10.1186/s43251-020-00001-y.

RM-R2A is an architecture/ownership gate only. It must not be reported as the full RM-R2 runtime PASS; RM-R2B will exercise the actual fresh-birth runtime on canonical OGS.
