# RM-R4 literature and architecture basis

Canonical OGS authority: `adf770974c7ee0435702fe617634d03d17ab7cb8`.

## Gate

RM-R4 must demonstrate a real staged material replacement

`RM_A -> void -> RM_B`

for the same mesh region, after RM-R0/R1/R2/R3 have passed. The replacement must use the full RichardsMechanics physical operator immediately on reactivation. No stiffness scaling, residual homotopy, or material homotopy is permitted.

## Established staged-construction semantics

- FLAC3D documents the null constitutive model as the representation of excavated/removed material; stresses in null zones are zero, and a null zone may later be changed to a different material model to simulate backfilling.
- FLAC3D coupled-flow documentation also makes an important coupled-domain distinction: making a zone mechanically null does not automatically make the fluid model null. RM therefore keeps R1's synchronized hydraulic/mechanical domain ownership explicit rather than inferring one field from the other.
- PLAXIS staged construction treats assigned material sets as phase-specific staged-construction state. Bentley's staged-construction documentation explicitly shows a later phase changing a soil-layer assignment from material B to material C.
- Abaqus element removal/reactivation semantics establish the reactivation instant as a new reference for state-dependent quantities; this is consistent with the already-passed RM-R2 fresh-birth contract rather than carrying constitutive history through the void interval.

These references support discrete phase/material replacement, not interpolation between A and B. Therefore R4 must not introduce a material homotopy.

## Canonical OGS constraint discovered before implementation

In canonical RichardsMechanics, `LocalAssemblerInterface` binds
`solid_material_` once in its constructor through
`selectSolidConstitutiveRelation(process_data_.solid_materials,
process_data_.material_ids, e.getID())` and stores it as a const reference.
The same assembler exposes `getMaterialID()` by reading the current mesh
`MaterialIDs` property. Consequently, mutating `MaterialIDs` alone at a
construction phase boundary is **not** authoritative evidence of solid material
reassignment: the local assembler would still integrate stresses with the
constitutive relation selected at assembler construction.

R4 therefore requires an explicit, discrete constitutive-rebind operation at
the `inactive -> active` lifecycle boundary, followed by creation and
initialization of a fresh `RM_B` material state. The rebind must be observable in
runtime evidence and must not depend on destruction/recreation of the entire RM
process or on numerical weakening.

## Implementation contract

1. Preserve the synchronized R1 active-domain lifecycle.
2. At a configured reactivation/material-replacement event, change the staged
   material assignment from `RM_A` to `RM_B` discretely.
3. Rebind the element-local solid constitutive relation to the relation selected
   for `RM_B`.
4. Recreate and initialize the integration-point material state with `RM_B`.
5. Reuse R2's stress-free mechanical birth reference and explicit hydraulic
   placement state `p_L0`.
6. Restore loaded equilibrium through R3's normal Newton solve at the same
   physical target time with the full RM operator.
7. Runtime evidence must identify both pre-void `RM_A` and post-birth `RM_B`
   behaviour and prove that the post-birth tangent/response is that of `RM_B`.

R5, not R4, will extend this discrete replacement contract to genuine
MFront/MGIS cross-behaviour hardening and prove that no incompatible history is
carried across behaviour types.
