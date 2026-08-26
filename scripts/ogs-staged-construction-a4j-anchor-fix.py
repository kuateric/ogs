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
new_guard = '''if text.count(old_no_support) == 1:\n    text = text.replace(old_no_support, new_no_support)\nelse:\n    # Restrict fallback discovery to the canonical no-support/reactivation\n    # branch. ProcessVariable.cpp contains other std::fill(_is_active, ...)\n    # sites, so a file-global first-fill search can select the wrong branch.\n    branch_anchor = \"    if (std::none_of(\\n            begin(_deactivated_subdomains), end(_deactivated_subdomains),\\n\"\n    branch_start = text.find(branch_anchor)\n    if branch_start < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support branch\")\n\n    transition_call = text.find(\n        \"StagedConstruction::determineDomainTransition\", branch_start)\n    if transition_call < 0:\n        raise RuntimeError(\"A4J no-support branch lacks lifecycle transition call\")\n\n    # The lifecycle assignment begins immediately before the transition call.\n    # Accept either the A3 form (_last_domain_transition =) or later temporary\n    # target-transition bookkeeping, but never reach outside this branch.\n    fill_anchor = \"        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\\n\"\n    fill_pos = text.find(fill_anchor, transition_call)\n    if fill_pos < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support activation fill\")\n\n    direct_start = text.rfind(\"        _last_domain_transition\", branch_start, transition_call + 1)\n    auto_start = text.rfind(\"        auto const target_transition\", branch_start, transition_call + 1)\n    start = max(direct_start, auto_start)\n    if start < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support lifecycle assignment\")\n\n    branch_return = \"        return;\\n\"\n    end = text.find(branch_return, fill_pos + len(fill_anchor))\n    if end < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support branch return\")\n    end += len(branch_return)\n    text = text[:start] + new_no_support + text[end:]\n'''
if text.count(old_guard) != 1:
    raise RuntimeError("Unexpected A4J no-support guard source layout")
text = text.replace(old_guard, new_guard)

p.write_text(text, encoding="utf-8")
print("Hardened A4J lifecycle and no-support branch anchors")
