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

old_guard = '''if text.count(old_no_support) != 1:\n    raise RuntimeError("Unexpected A3 no-support activation branch")\ntext = text.replace(old_no_support, new_no_support)\n'''
new_guard = '''if text.count(old_no_support) == 1:\n    text = text.replace(old_no_support, new_no_support)\nelse:\n    branch_anchor = \"    if (std::none_of(\\n            begin(_deactivated_subdomains), end(_deactivated_subdomains),\\n\"\n    branch_start = text.find(branch_anchor)\n    if branch_start < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support branch\")\n\n    transition_call = text.find(\n        \"StagedConstruction::determineDomainTransition\", branch_start)\n    if transition_call < 0:\n        raise RuntimeError(\"A4J no-support branch lacks lifecycle transition call\")\n\n    fill_anchor = \"        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\\n\"\n    fill_pos = text.find(fill_anchor, transition_call)\n    if fill_pos < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support activation fill\")\n\n    direct_start = text.rfind(\"        _last_domain_transition\", branch_start, transition_call + 1)\n    auto_start = text.rfind(\"        auto const target_transition\", branch_start, transition_call + 1)\n    start = max(direct_start, auto_start)\n    if start < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support lifecycle assignment\")\n\n    branch_return = \"        return;\\n\"\n    end = text.find(branch_return, fill_pos + len(fill_anchor))\n    if end < 0:\n        raise RuntimeError(\"A4J could not locate canonical no-support branch return\")\n    end += len(branch_return)\n    text = text[:start] + new_no_support + text[end:]\n'''
if text.count(old_guard) != 1:
    raise RuntimeError("Unexpected A4J no-support guard source layout")
text = text.replace(old_guard, new_guard)

source_insert_anchor = '''# Publish the deferred event only after the inactive physical baseline has\n# converged. Material reassignment is deliberately performed here, immediately\n'''
general_patch_source = r"""# The general lifecycle path can also contain inactive->active transitions.
# Split those from the physical-time solve exactly like the no-support path.
general_anchor = '''    _last_domain_transition = StagedConstruction::determineDomainTransition(
        previous_is_active, current_is_active);
    apply_activation_material_assignments(_last_domain_transition);
    _ids_of_active_elements = _last_domain_transition.active_element_ids;
'''
general_replacement = '''    auto const target_transition =
        StagedConstruction::determineDomainTransition(previous_is_active,
                                                      current_is_active);

    if (!target_transition.newly_activated_element_ids.empty())
    {
        // The physical t_{n+1} baseline must retain the old inactive topology
        // for newborn cells. Newly deactivated cells, if any, remain applied.
        auto baseline_is_active = current_is_active;
        for (auto const element_id :
             target_transition.newly_activated_element_ids)
        {
            baseline_is_active[element_id] = 0u;
        }

        _pending_activation_transition = target_transition;
        _last_domain_transition =
            StagedConstruction::determineDomainTransition(previous_is_active,
                                                          baseline_is_active);
        std::copy(std::begin(baseline_is_active), std::end(baseline_is_active),
                  std::begin(*_is_active));
        _ids_of_active_elements = _last_domain_transition.active_element_ids;
        return;
    }

    _last_domain_transition = target_transition;
    apply_activation_material_assignments(_last_domain_transition);
    _ids_of_active_elements = _last_domain_transition.active_element_ids;
'''
if text.count(general_anchor) != 1:
    raise RuntimeError("Unexpected A3 general activation transition branch")
text = text.replace(general_anchor, general_replacement)

"""
if text.count(source_insert_anchor) != 1:
    raise RuntimeError("Unexpected A4J source insertion anchor")
text = text.replace(source_insert_anchor,
                    general_patch_source + source_insert_anchor)

p.write_text(text, encoding="utf-8")
print("Hardened A4J lifecycle and deferred both no-support and general activation paths")
