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
# branch, but later patch composition may add harmless bookkeeping between the
# transition assignment and the branch return.  A4J only needs to replace that
# one lifecycle branch; do not require an exact byte-for-byte A3 body.
old_guard = '''if text.count(old_no_support) != 1:\n    raise RuntimeError("Unexpected A3 no-support activation branch")\ntext = text.replace(old_no_support, new_no_support)\n'''
new_guard = '''if text.count(old_no_support) == 1:\n    text = text.replace(old_no_support, new_no_support)\nelse:\n    # Fall back to structural anchors that are unique to R2G's canonical\n    # no-support/reactivation branch.  Replace from lifecycle-transition\n    # assignment through that branch's return, while tolerating intermediate\n    # A3/A4 bookkeeping.\n    branch_start = \"\"\"        _last_domain_transition =\n            StagedConstruction::determineDomainTransition(previous_is_active,\n                                                          current_is_active);\n\"\"\"\n    branch_return = \"        return;\\n\"\n    start = text.find(branch_start)\n    if start < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support lifecycle transition\")\n    end = text.find(branch_return, start + len(branch_start))\n    if end < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support branch return\")\n    end += len(branch_return)\n    text = text[:start] + new_no_support + text[end:]\n'''
if text.count(old_guard) != 1:
    raise RuntimeError("Unexpected A4J no-support guard source layout")
text = text.replace(old_guard, new_guard)

p.write_text(text, encoding="utf-8")
print("Hardened A4J lifecycle and no-support branch anchors")
