# G5 mechanical interface — SmallDeformation developer handoff

This branch contains the frozen G5 V1 mechanical structural interface integrated into the OGS `SMALL_DEFORMATION` process.

## Authority

- OGS base commit: `adf770974c7ee0435702fe617634d03d17ab7cb8`
- Frozen G5 Engineering OS RC: `790c22a0938f2c0b3a7e95a0dc7beff3c97683d7`
- Exact-ref acceptance run: `34003035381`
- Exact-ref job: `101405191382`

The production G5 C++ sources under `ProcessLib/SmallDeformation` are the frozen V1 implementation used by that acceptance run. G5 V1 is qualified here for 2D `SMALL_DEFORMATION`; this handoff does not claim equivalent RichardsMechanics qualification.

## Clone and build

```bash
git clone https://github.com/kuateric/ogs.git
cd ogs
git checkout g5-mechanical-interface

cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DOGS_BUILD_TESTING=OFF \
  -DBUILD_TESTING=OFF \
  -DOGS_BUILD_CLI=ON \
  -DOGS_USE_UNITY_BUILDS=OFF \
  -DOGS_BUILD_PROCESSES=SmallDeformation

cmake --build build --target ogs --parallel 1
./build/bin/ogs --version
```

`--parallel 1` is the conservative exact-ref setting. More parallel build jobs may be used when sufficient RAM is available.

## Mechanical-interface project syntax

Inside a 2D `SMALL_DEFORMATION` process:

```xml
<mechanical_interface>
    <material>
        <id>0</id>
        <normal_stiffness>1e8</normal_stiffness>
        <tangential_stiffness>2e7</tangential_stiffness>
        <friction_coefficient>0.5</friction_coefficient>
    </material>
    <pair>
        <side_a_node_id>0</side_a_node_id>
        <side_b_node_id>2</side_b_node_id>
        <normal>1 0</normal>
        <initial_normal_gap>-0.005</initial_normal_gap>
        <interface_material_id>0</interface_material_id>
    </pair>
</mechanical_interface>
```

The two sides must use distinct process nodes. Positive normal gap is opening; negative normal gap is compression. The V1 law supports OPEN, STICK and Coulomb SLIP with committed plastic tangential slip and opening/reclosure.

## Reproduce the frozen native benchmarks

The two-segment benchmark reuses the canonical OGS 2D mechanics project `Tests/Data/Mechanics/Linear/square_1e0.prj`:

```bash
python3 Tests/Data/Mechanics/G5MechanicalInterface/run_two_segment_tubbing_joint_benchmark.py \
  --ogs build/bin/ogs \
  --source-prj Tests/Data/Mechanics/Linear/square_1e0.prj \
  --output-dir build/g5-two-segment
```

Expected frozen result: normal gap `-0.005 m`, tangential slip `0.05 m`, normal traction `-0.5 MPa`, tangential traction `0.25 MPa`, friction utilization `1`, plastic slip `0.0375 m`, with a SLIP event.

The native two-domain benchmark creates two disconnected continuum segments with duplicate coincident interface nodes and couples them only through G5:

```bash
python3 Tests/Data/Mechanics/G5MechanicalInterface/run_g5_a01_native_two_domain.py \
  --ogs build/bin/ogs \
  --output-dir build/g5-a01
```

A successful run prints `G5-A01 native two-domain benchmark: PASS`.

## Scope

The branch is a developer handoff of the frozen G5 V1 SmallDeformation implementation. Do not change the frozen contact-law semantics on this branch. Further process integrations, hydraulic/thermal interfaces, or project-scale model development belong on separate branches.
