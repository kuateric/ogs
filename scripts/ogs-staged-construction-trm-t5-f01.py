#!/usr/bin/env python3
from pathlib import Path

# TRM-T5-F01 — process-wide ownership fix for material reassignment.
#
# TRM repeats the same staged-construction declaration on temperature, pressure,
# and displacement. MaterialID, however, is one shared mesh/element property.
# Therefore the physical MaterialID mutation must happen once per element even
# though the synchronized ProcessVariables all report the same transition.
#
# This follows established staged-construction semantics: PLAXIS stores a soil
# object's material assignment per construction phase, rather than separately
# per primary field. The fix remains constitutive-law neutral and keeps the
# existing T5 rule that the local assembler re-resolves the selected MaterialID
# and creates a fresh state from that material at birth.

p = Path("scripts/ogs-staged-construction-trm-t5.py")
text = p.read_text(encoding="utf-8")

old = '''            if (target_material_id)\\n            {\\n                (*material_ids)[element_id] = *target_material_id;\\n                INFO("TRM-T5 activation material reassigned for element {:d}: material_id={:d}",\\n                     element_id, *target_material_id);\\n            }\\n'''
new = '''            if (target_material_id)\\n            {\\n                // MaterialIDs are shared mesh/element state. Synchronized\\n                // T/p/u transitions may reach this hook repeatedly; only the\\n                // first caller performs the physical reassignment.\\n                if ((*material_ids)[element_id] == *target_material_id)\\n                {\\n                    continue;\\n                }\\n\\n                (*material_ids)[element_id] = *target_material_id;\\n                INFO("TRM-T5 activation material reassigned for element {:d}: material_id={:d}",\\n                     element_id, *target_material_id);\\n            }\\n'''

if text.count(old) != 1:
    raise RuntimeError("unexpected TRM-T5 source assignment anchor")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("Applied TRM-T5-F01 shared MaterialID ownership fix")
