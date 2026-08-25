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
p.write_text(text, encoding="utf-8")
print("Hardened A4J lifecycle member anchor")
