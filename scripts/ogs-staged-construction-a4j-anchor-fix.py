#!/usr/bin/env python3
from pathlib import Path

p = Path("ogs-staged-construction-a4j.py")
text = p.read_text(encoding="utf-8")

old_anchor = '''member_anchor = \'\'\'    StagedConstruction::DomainTransition _last_domain_transition;\n    MeshLib::PropertyVector<unsigned char>* _is_active = nullptr;\n\'\'\'\n'''
new_anchor = '''member_anchor = \'\'\'    StagedConstruction::DomainTransition _last_domain_transition;\n\'\'\'\n'''
old_replacement = '''member_replacement = \'\'\'    StagedConstruction::DomainTransition _last_domain_transition;\n    StagedConstruction::DomainTransition _pending_activation_transition;\n    MeshLib::PropertyVector<unsigned char>* _is_active = nullptr;\n\'\'\'\n'''
new_replacement = '''member_replacement = \'\'\'    StagedConstruction::DomainTransition _last_domain_transition;\n    StagedConstruction::DomainTransition _pending_activation_transition;\n\'\'\'\n'''

if text.count(old_anchor) != 1 or text.count(old_replacement) != 1:
    raise RuntimeError("Unexpected A4J script lifecycle-anchor source layout")
text = text.replace(old_anchor, new_anchor).replace(old_replacement, new_replacement)

# A3 is the authority for material reassignment in the canonical no-support
# branch, but later patch composition may add bookkeeping or reformat the
# transition assignment. A4J only needs to replace that one lifecycle branch;
# do not require a byte-for-byte A3 body.
old_guard = '''if text.count(old_no_support) != 1:\n    raise RuntimeError("Unexpected A3 no-support activation branch")\ntext = text.replace(old_no_support, new_no_support)\n'''
new_guard = '''if text.count(old_no_support) == 1:\n    text = text.replace(old_no_support, new_no_support)\nelse:\n    # Locate the canonical no-support/reactivation branch by its stable\n    # semantic landmarks instead of exact line wrapping.  The branch ends by\n    # marking every element active, and immediately before that it records the\n    # domain transition.\n    fill_anchor = \"        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\\n\"\n    fill_pos = text.find(fill_anchor)\n    if fill_pos < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support activation fill\")\n\n    # Find the closest lifecycle assignment preceding that fill.  This is\n    # robust to A3/A4 bookkeeping and to line-wrap changes in the\n    # determineDomainTransition call.\n    start = text.rfind(\"        _last_domain_transition\", 0, fill_pos)\n    if start < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support lifecycle assignment\")\n\n    transition_call = text.find(\"StagedConstruction::determineDomainTransition\", start, fill_pos)\n    if transition_call < 0:\n        raise RuntimeError(\"A4J no-support branch lacks lifecycle transition call\")\n\n    branch_return = \"        return;\\n\"\n    end = text.find(branch_return, fill_pos + len(fill_anchor))\n    if end < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support branch return\")\n    end += len(branch_return)\n    text = text[:start] + new_no_support + text[end:]\n'''
if text.count(old_guard) != 1:
    raise RuntimeError("Unexpected A4J no-support guard source layout")
text = text.replace(old_guard, new_guard)

p.write_text(text, encoding="utf-8")
print("Hardened A4J lifecycle and no-support branch anchors")
