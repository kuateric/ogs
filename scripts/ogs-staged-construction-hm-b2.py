#!/usr/bin/env python3
from pathlib import Path

p = Path("ProcessLib/Process.cpp")
text = p.read_text(encoding="utf-8")
old = r'''    auto active_elements_ids = ranges::views::transform(
        [](auto const& variable)
        { return variable.get().getActiveElementIDs(); });

    // Early return if there's any process variable with all elements active.
    if (ranges::any_of(variables_per_process | active_elements_ids,
                       [](auto const& vector) { return vector.empty(); }))
    {
        return;
    }

    // Some process variable has deactivated elements. Create union of active
    // ids.

    _ids_of_active_elements =  // there is at least one process variable.
        variables_per_process[0].get().getActiveElementIDs();

    for (auto const& pv_active_element_ids :
         variables_per_process | ranges::views::drop(1) | active_elements_ids)
    {
        std::vector<std::size_t> new_active_elements;
        new_active_elements.reserve(_ids_of_active_elements.size() +
                                    pv_active_element_ids.size());
        ranges::set_union(_ids_of_active_elements, pv_active_element_ids,
                          std::back_inserter(new_active_elements));

        _ids_of_active_elements = std::move(new_active_elements);
    }
'''
new = r'''    // HM-B2 coupled lifecycle semantics: an element contributes to a
    // monolithic coupled operator only if it is active for every variable that
    // owns a staged-construction restriction. An empty active-id vector means
    // that the variable has no active restriction at the current time and acts
    // as the identity set; it must not re-enable the entire coupled domain.
    bool have_restricted_variable = false;
    for (auto const& variable : variables_per_process)
    {
        auto const& pv_active_element_ids =
            variable.get().getActiveElementIDs();
        if (pv_active_element_ids.empty())
        {
            continue;
        }

        if (!have_restricted_variable)
        {
            _ids_of_active_elements = pv_active_element_ids;
            have_restricted_variable = true;
            continue;
        }

        std::vector<std::size_t> new_active_elements;
        new_active_elements.reserve(std::min(_ids_of_active_elements.size(),
                                             pv_active_element_ids.size()));
        ranges::set_intersection(_ids_of_active_elements,
                                 pv_active_element_ids,
                                 std::back_inserter(new_active_elements));
        _ids_of_active_elements = std::move(new_active_elements);
    }

    // No process variable currently restricts the domain. Empty means all
    // elements active, preserving the established Process contract.
    if (!have_restricted_variable)
    {
        return;
    }
'''
if text.count(old) != 1:
    raise RuntimeError("unexpected Process::updateDeactivatedSubdomains active-set block")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
