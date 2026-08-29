# Phase C Anchor C0 — literature and established-code basis

Canonical OGS authority remains pinned to `adf770974c7ee0435702fe617634d03d17ab7cb8`.

## Established staged-construction semantics

### Abaqus/Standard

`*MODEL CHANGE, ADD=STRAIN FREE` reactivates stress/displacement elements in the configuration at the start of the reactivation step as their new initial configuration. The reactivated element is in a virgin state (zero stress/strain/plastic strain unless a non-virgin state is explicitly supplied) and is fully active immediately. Abaqus explicitly identifies tunnel-liner installation in an already-deformed excavation as a canonical use case.

Phase C therefore treats structural-support installation as a birth/reference-state operation, not as a stiffness homotopy.

### FLAC3D

FLAC3D structural support creation and cable pretensioning are distinct operations. This supports keeping OGS `initial_anchor_stress` as the explicit placement/prestress state rather than deriving prestress from pre-installation excavation displacement.

## OGS mapping

Pinned OGS already contains `EmbeddedAnchor` as a displacement source term. Its pre-C0 strain uses the original anchor geometry plus total interpolated bulk displacement, so an anchor introduced after excavation deformation would inherit pre-installation deformation unless a placement reference is introduced.

C0 adds an optional per-anchor cell property `activation_time`:

- absent: existing EmbeddedAnchor behaviour is unchanged;
- before activation: the anchor contributes no residual or tangent;
- first assembly at/after activation: current interpolated bulk displacement is captured as the stress-free birth reference;
- after birth: strain uses only displacement increments relative to that reference;
- full physical `anchor_stiffness` is active immediately;
- `initial_anchor_stress` remains the explicit placement/prestress state.

No material-law scaling, residual scaling, or stiffness homotopy is introduced.

## EmbeddedBeam authority finding

The pinned canonical OGS tree contains `EmbeddedAnchor` but no `EmbeddedBeam` source/process implementation. The `kuateric/ogs` GitHub branch list likewise contains no EmbeddedBeam branch. Therefore this staged-construction branch does not invent or duplicate EmbeddedBeam mechanics. Phase C proceeds on the existing Anchor authority while keeping combined EmbeddedBeam+Anchor excavation integration gated on the separate structural-element implementation authority.
