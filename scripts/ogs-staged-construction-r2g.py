#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

header = root / "ProcessLib/ProcessVariable.h"
text = header.read_text(encoding="utf-8")

include_anchor = '#include "MaterialLib/MPL/Medium.h"\n'
include_line = '#include "ProcessLib/StagedConstruction/DomainLifecycle.h"\n'
if include_line not in text:
    if text.count(include_anchor) != 1:
        raise RuntimeError("Unexpected ProcessVariable.h include layout")
    text = text.replace(include_anchor, include_anchor + include_line)

getter_anchor = '''    std::vector<std::size_t> const& getActiveElementIDs() const\n    {\n        return _ids_of_active_elements;\n    }\n'''
getter = '''    std::vector<std::size_t> const& getActiveElementIDs() const\n    {\n        return _ids_of_active_elements;\n    }\n\n    StagedConstruction::DomainTransition const& getLastDomainTransition() const\n    {\n        return _last_domain_transition;\n    }\n'''
if getter_anchor not in text:
    raise RuntimeError("Unexpected ProcessVariable.h active-element getter layout")
text = text.replace(getter_anchor, getter)

member_anchor = '''    mutable std::vector<std::size_t> _ids_of_active_elements;\n    MeshLib::PropertyVector<unsigned char>* _is_active = nullptr;\n'''
member = '''    mutable std::vector<std::size_t> _ids_of_active_elements;\n    StagedConstruction::DomainTransition _last_domain_transition;\n    MeshLib::PropertyVector<unsigned char>* _is_active = nullptr;\n'''
if member_anchor not in text:
    raise RuntimeError("Unexpected ProcessVariable.h lifecycle member layout")
text = text.replace(member_anchor, member)
header.write_text(text, encoding="utf-8")

cpp = root / "ProcessLib/ProcessVariable.cpp"
text = cpp.read_text(encoding="utf-8")

old_no_support = '''    if (std::none_of(\n            begin(_deactivated_subdomains), end(_deactivated_subdomains),\n            [&](auto const& ds)\n            { return isTimeInSupportInterval(ds.time_interval, time); }))\n    {\n        // Also mark all of the elements as active.\n        assert(_is_active != nullptr);  // guaranteed by constructor\n        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\n\n        return;\n    }\n'''
new_no_support = '''    if (std::none_of(\n            begin(_deactivated_subdomains), end(_deactivated_subdomains),\n            [&](auto const& ds)\n            { return isTimeInSupportInterval(ds.time_interval, time); }))\n    {\n        // Also mark all of the elements as active while retaining the lifecycle\n        // transition. This is required for future activation/backfill events and\n        // makes the active->inactive/inactive->active history observable by the\n        // process without changing the existing deactivation semantics.\n        assert(_is_active != nullptr);  // guaranteed by constructor\n        auto const previous_is_active = std::vector<unsigned char>(\n            std::begin(*_is_active), std::end(*_is_active));\n        auto const current_is_active =\n            std::vector<unsigned char>(_mesh.getNumberOfElements(), 1u);\n        _last_domain_transition =\n            StagedConstruction::determineDomainTransition(previous_is_active,\n                                                          current_is_active);\n        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);\n\n        return;\n    }\n'''
if text.count(old_no_support) != 1:
    raise RuntimeError("Unexpected ProcessVariable.cpp no-support branch layout")
text = text.replace(old_no_support, new_no_support)

old_transition = '''    auto const transition = StagedConstruction::determineDomainTransition(\n        previous_is_active, current_is_active);\n    _ids_of_active_elements = transition.active_element_ids;\n'''
new_transition = '''    _last_domain_transition = StagedConstruction::determineDomainTransition(\n        previous_is_active, current_is_active);\n    _ids_of_active_elements = _last_domain_transition.active_element_ids;\n'''
if text.count(old_transition) != 1:
    raise RuntimeError("Unexpected ProcessVariable.cpp transition assignment layout")
text = text.replace(old_transition, new_transition)
cpp.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction R2G persistent lifecycle transition plumbing")
