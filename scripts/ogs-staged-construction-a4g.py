#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4G diagnostic gate: A4F showed an activation Newton correction that is
# invariant under lambda cutback. Instrument the local newborn-element residual
# and the domain transition itself so we can distinguish a failed activation
# scaling path from a global active-set / retained-force imbalance.

fem = root / "ProcessLib/SmallDeformation/SmallDeformationFEM.h"
text = fem.read_text(encoding="utf-8")
old = '''        auto const activation_scale = this->activationContributionScale();
        local_b *= activation_scale;
'''
new = '''        auto const activation_scale = this->activationContributionScale();
        auto const activation_unscaled_residual_norm = local_b.norm();
        local_b *= activation_scale;
        if (activation_scale < 1.0)
        {
            INFO("A4G activation assembly element {:d}: lambda={:g}, "
                 "unscaled_local_residual_norm={:g}, "
                 "scaled_local_residual_norm={:g}, tangent_norm={:g}",
                 this->element_.getID(), activation_scale,
                 activation_unscaled_residual_norm, local_b.norm(),
                 local_Jac.norm());
        }
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4E activation residual scaling block")
fem.write_text(text.replace(old, new), encoding="utf-8")

cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = cpp.read_text(encoding="utf-8")
anchor = '''    auto const& domain_transition =
        getProcessVariables(process_id)[0].get().getLastDomainTransition();

'''
insert = '''    auto const& domain_transition =
        getProcessVariables(process_id)[0].get().getLastDomainTransition();

    if (!domain_transition.newly_activated_element_ids.empty() ||
        !domain_transition.newly_deactivated_element_ids.empty())
    {
        INFO("A4G lifecycle transition: newly_activated={:d}, "
             "newly_deactivated={:d}",
             domain_transition.newly_activated_element_ids.size(),
             domain_transition.newly_deactivated_element_ids.size());
    }

'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformation domain-transition anchor")
cpp.write_text(text.replace(anchor, insert), encoding="utf-8")

print("Applied OGS Staged Construction A4G activation residual diagnostics")
