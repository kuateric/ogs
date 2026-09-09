# Frozen G5 V1 source manifest

Authority RC: `790c22a0938f2c0b3a7e95a0dc7beff3c97683d7`

The following production files under `ProcessLib/SmallDeformation` must retain the listed Git blob SHA. These are content-addressed checks against the frozen Engineering OS RC.

| File | Frozen blob SHA |
|---|---|
| MechanicalInterfaceDofTopology.cpp | `4f44eca9023eb72a0ab8d78b045c3bd6591c807c` |
| MechanicalInterfaceDofTopology.h | `5ddbc97edaf569cdce1ba0ba26b9daa339c57a9e` |
| MechanicalInterfaceGlobalAssembly.cpp | `8e265ac54da93eb84910117204e811e91f4fd9a0` |
| MechanicalInterfaceGlobalAssembly.h | `19335ed2b20bf30c64cfd833ae51f08d204903a4` |
| MechanicalInterfaceLaw.cpp | `e0605abe055ffbe6eedf9ba8b058def894971bc9` |
| MechanicalInterfaceLaw.h | `4bda28e53d7703b1e4b6675135a37846fcc31e8e` |
| MechanicalInterfacePairAssembler.cpp | `75f0eff8bbfce14f05c05cd296c7fe447079202b` |
| MechanicalInterfacePairAssembler.h | `70ad429f5ea14858170bf0bc5e2c970358773235` |
| MechanicalInterfacePairRegistry.cpp | `d2ad8100c31c9b224a1b486e6e6b2135a2a36019` |
| MechanicalInterfacePairRegistry.h | `1ec6a2200b8dab80852b4a155a349d51dabedee1` |
| MechanicalInterfaceProcessDofMapper.cpp | `78882264d1ba82fe824f32113c20398035701856` |
| MechanicalInterfaceProcessDofMapper.h | `d16a9643ed6d9b95200d5b0dcaaec753ab185432` |
| MechanicalInterfaceProcessLifecycle.h | `92bd7f689f37724cb9ff6917e650716eb3ec6a39` |
| MechanicalInterfaceSmallDeformationRuntime.cpp | `4ff6b68814f4ae4a058049bea91ebb0518874dba` |
| MechanicalInterfaceSmallDeformationRuntime.h | `e807f285d789bb4a9cea46979394b5bf3f02b17d` |
| MechanicalInterfaceStateManager.cpp | `0099f5d3c1bd4b0da9980acec23e4e904ae0b07f` |
| MechanicalInterfaceStateManager.h | `5930ea0800685d342bcf00b233fb361af27f9c14` |
| MechanicalInterfaceStatefulPairAssembly.h | `006830ef91fe9a1c15b6af1307574a552cda50fc` |

Benchmark authorities:

- `run_two_segment_tubbing_joint_benchmark.py`: `4257ada5153fb4c413c7b4c9ebdbc67eb60e8efd`
- `run_g5_a01_native_two_domain.py`: `e9a021a72307c04f73e7ae7a9b2a35c063b998bc`

The three canonical OGS hook files (`SmallDeformationProcess.h`, `SmallDeformationProcess.cpp`, and `CreateSmallDeformationProcess.cpp`) are additive integration edits on OGS base `adf770974c7ee0435702fe617634d03d17ab7cb8`; they are not frozen standalone source blobs because their content includes the canonical upstream OGS source plus the G5 hook.
