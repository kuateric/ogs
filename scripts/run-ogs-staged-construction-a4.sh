#!/usr/bin/env bash
set -euo pipefail

OGS_UPSTREAM_URL="${OGS_UPSTREAM_URL:-https://github.com/Helmholtz-UFZ/ogs.git}"
OGS_UPSTREAM_SHA="${OGS_UPSTREAM_SHA:-adf770974c7ee0435702fe617634d03d17ab7cb8}"

rm -rf ogs-a4-contract
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-a4-contract
cd ogs-a4-contract
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"
cd ..

for s in r0 a0 a4; do cp "scripts/ogs-staged-construction-${s}.py" ogs-a4-contract/; done
cd ogs-a4-contract
for s in r0 a0 a4; do python3 "ogs-staged-construction-${s}.py"; done
git diff --check

cat > /tmp/a4_contract_smoke.cpp <<'CPP'
#include <cassert>
#include <cmath>
#include <vector>
#include "ProcessLib/StagedConstruction/ActivationPlacementState.h"
#include "ProcessLib/StagedConstruction/ActivationTransition.h"

int main()
{
    using namespace ProcessLib::StagedConstruction;

    DomainTransition tr;
    tr.newly_activated_element_ids = {3, 7};
    auto placement = makeActivationPlacementState(tr);
    assert(placement.newlyActivatedElementIDs().size() == 2);
    assert(placement.constitutiveStatePolicy() ==
           ActivationPlacementState::ConstitutiveStatePolicy::fresh_material_state);
    assert(placement.activationLoadingPolicy() ==
           ActivationPlacementState::ActivationLoadingPolicy::adaptive_continuation);

    ActivationPlacementState::PlacementFields fields;
    fields.liquid_pressure = 1.2e5;
    fields.gas_pressure = 1.0e5;
    fields.temperature = 298.15;
    fields.liquid_saturation = 0.55;
    fields.porosity = 0.42;
    ActivationPlacementState explicit_state{
        {9}, ActivationPlacementState::ConstitutiveStatePolicy::fresh_material_state,
        ActivationPlacementState::ActivationLoadingPolicy::adaptive_continuation,
        fields};
    assert(std::abs(*explicit_state.placementFields().temperature - 298.15) < 1e-12);
    assert(std::abs(*explicit_state.placementFields().liquid_saturation - 0.55) < 1e-12);

    ActivationTransition continuation{0.25, 1e-4, 1.5, 0.5};
    double previous = 0.0;
    int accepted = 0;
    while (!continuation.complete())
    {
        double const trial = continuation.beginTrial();
        assert(trial > previous && trial <= 1.0);
        continuation.acceptTrial();
        previous = continuation.committedLambda();
        ++accepted;
        assert(accepted < 20);
    }
    assert(std::abs(continuation.committedLambda() - 1.0) < 1e-12);

    ActivationTransition cutback{0.5, 1e-4, 1.5, 0.5};
    double const first = cutback.beginTrial();
    assert(std::abs(first - 0.5) < 1e-12);
    cutback.rejectTrial();
    double const retry = cutback.beginTrial();
    assert(std::abs(retry - 0.25) < 1e-12);
    cutback.acceptTrial();
    assert(std::abs(cutback.committedLambda() - 0.25) < 1e-12);
}
CPP

g++ -std=c++23 -I. /tmp/a4_contract_smoke.cpp -o /tmp/a4_contract_smoke
/tmp/a4_contract_smoke

cat > staged-a4-evidence.txt <<EOF
upstream_sha=$OGS_UPSTREAM_SHA
gate=A4A_explicit_placement_state_contract
fresh_constitutive_state=1
adaptive_activation_loading_policy=1
liquid_pressure_field=1
gas_pressure_field=1
temperature_field=1
liquid_saturation_field=1
porosity_field=1
activation_monotonicity=1
activation_cutback=1
physical_time_semantics=construction_coordinate_only
EOF

# CI synchronization marker: A4J deferred activation baseline/operator-split validation.
