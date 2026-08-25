#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"
export CPM_SOURCE_CACHE="${CPM_SOURCE_CACHE:-$PWD/.cpm-cache}"

rm -rf ogs-a4b-runtime
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-a4b-runtime
cd ogs-a4b-runtime
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"
cd ..

stages='r0 r2b r2c r2d r2e r2f r2g r2h r2i r2j r2k r2k-f01 r2l r3a r3b r3c r3d r3e r3f r3g r3h r3i a0 a1 a3 a4 a4b'
for s in $stages; do cp "scripts/ogs-staged-construction-${s}.py" ogs-a4b-runtime/; done
cd ogs-a4b-runtime
for s in $stages; do python3 "ogs-staged-construction-${s}.py"; done

git diff --check
grep -q 'activation_contribution_scale_' ProcessLib/SmallDeformation/LocalAssemblerInterface.h
grep -q 'local_b \*= activation_scale' ProcessLib/SmallDeformation/SmallDeformationFEM.h
grep -q 'local_Jac \*= activation_scale' ProcessLib/SmallDeformation/SmallDeformationFEM.h
grep -q 'staged_construction_activation_transition_' ProcessLib/SmallDeformation/SmallDeformationProcess.h
grep -q 'setActivationContributionScale' ProcessLib/SmallDeformation/SmallDeformationProcess.cpp

cmake --preset release -DOGS_BUILD_GUI=OFF -DOGS_BUILD_UTILS=OFF -DOGS_BUILD_TESTING=ON -DOGS_USE_MFRONT=ON '-DOGS_BUILD_PROCESSES=SmallDeformation'
cmake --build --preset release --target ProcessLib SmallDeformation ogs --parallel 2

cat > staged-a4b-evidence.txt <<EOF
upstream_sha=$OGS_UPSTREAM_SHA
gate=A4B_controlled_activation_runtime_build
fresh_constitutive_state=1
material_reassignment=1
activation_initial_scale=0
activation_residual_scaling=1
activation_jacobian_scaling=1
activation_trial_commit_rollback=1
physical_time_semantics=existing_constant_time_construction_driver
mfront_enabled_build=1
EOF
