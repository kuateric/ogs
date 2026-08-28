#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
pv = root / "ProcessLib/ProcessVariable.cpp"
text = pv.read_text(encoding="utf-8")

# TRM-T5-F01 — make activation material reassignment idempotent across the
# synchronized T/p/u ProcessVariable declarations.
#
# MaterialID is a shared mesh/element property, not a field-specific state.
# TRM declares the same staged-construction subdomain on temperature, pressure,
# and displacement, so ProcessVariable::updateDeactivatedSubdomains() is called
# three times for the same physical transition. The first call owns the actual
# MaterialID mutation; subsequent synchronized calls must observe the already
# assigned target and leave the shared element property untouched.
#
# This follows the established staged-construction model used by PLAXIS, where
# material assignment is a property of the soil object in a construction phase,
# not a separate assignment per primary field. It also preserves the HM-B6
# material-law-neutral contract: staged construction carries only a MaterialID,
# while the local assembler later resolves and fresh-initializes the selected
# constitutive law.

old = '''            if (target_material_id)\n            {\n                (*material_ids)[element_id] = *target_material_id;\n                INFO("TRM-T5 activation material reassigned for element {:d}: material_id={:d}",\n                     element_id, *target_material_id);\n            }\n'''
new = '''            if (target_material_id)\n            {\n                // MaterialIDs belong to the shared mesh. In monolithic TRM the\n                // synchronized T/p/u variables each report the same domain\n                // transition, so only the first caller performs the physical\n                // element-property mutation. The remaining callers observe the\n                // already assigned target and do nothing.\n                if ((*material_ids)[element_id] == *target_material_id)\n                {\n                    continue;\n                }\n\n                (*material_ids)[element_id] = *target_material_id;\n                INFO("TRM-T5 activation material reassigned for element {:d}: material_id={:d}",\n                     element_id, *target_material_id);\n            }\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected TRM-T5 assignment anchor")
pv.write_text(text.replace(old, new, 1), encoding="utf-8")

print("Applied TRM-T5-F01 process-wide idempotent material reassignment")
