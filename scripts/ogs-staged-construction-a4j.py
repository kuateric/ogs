#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4J: activation is a construction event, not part of the physical time-step
# advance.  At the activation time first solve the ordinary physical step with
# the region still inactive and its artificial inactive-domain Dirichlet
# support intact.  Only after that baseline converges publish the activation,
# initialize the fresh placed material at the converged host configuration and
# execute the existing adaptive activation continuation at the same physical t.
#
# This keeps the physical-time coordinate and construction coordinate
# orthogonal:
#   t_n -> t_{n+1}, inactive baseline solve
#   publish activation at t_{n+1}
#   lambda_act: 0 -> 1, no further physical time advance.

# ---------------------------------------------------------------------------
# 1. ProcessVariable: defer the canonical no-support reactivation event.
# ---------------------------------------------------------------------------
pv_h = root / "ProcessLib/ProcessVariable.h"
text = pv_h.read_text(encoding="utf-8")
getter_anchor = '''    StagedConstruction::DomainTransition const& getLastDomainTransition() const
    {
        return _last_domain_transition;
    }
'''
getter_replacement = getter_anchor + '''
    bool hasPendingActivationPublication() const
    {
        return !_pending_activation_transition.newly_activated_element_ids.empty();
    }

    StagedConstruction::DomainTransition publishPendingActivation();
'''
if text.count(getter_anchor) != 1:
    raise RuntimeError("Unexpected R2G lifecycle getter layout")
text = text.replace(getter_anchor, getter_replacement)

member_anchor = '''    StagedConstruction::DomainTransition _last_domain_transition;
    MeshLib::PropertyVector<unsigned char>* _is_active = nullptr;
'''
member_replacement = '''    StagedConstruction::DomainTransition _last_domain_transition;
    StagedConstruction::DomainTransition _pending_activation_transition;
    MeshLib::PropertyVector<unsigned char>* _is_active = nullptr;
'''
if text.count(member_anchor) != 1:
    raise RuntimeError("Unexpected R2G lifecycle member layout")
pv_h.write_text(text.replace(member_anchor, member_replacement), encoding="utf-8")

pv_cpp = root / "ProcessLib/ProcessVariable.cpp"
text = pv_cpp.read_text(encoding="utf-8")

old_no_support = '''        _last_domain_transition =
            StagedConstruction::determineDomainTransition(previous_is_active,
                                                          current_is_active);
        apply_activation_material_assignments(_last_domain_transition);
        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);

        return;
'''
new_no_support = '''        auto const target_transition =
            StagedConstruction::determineDomainTransition(previous_is_active,
                                                          current_is_active);

        if (!target_transition.newly_activated_element_ids.empty())
        {
            // Do not publish activation into the physical t_{n+1} solve. Keep
            // the previously inactive topology and material identity until the
            // ordinary physical step has converged. TimeLoop publishes this
            // stored transition afterwards at the same physical time.
            _pending_activation_transition = target_transition;
            _last_domain_transition = {};
            _ids_of_active_elements.clear();
            for (std::size_t element_id = 0;
                 element_id < previous_is_active.size(); ++element_id)
            {
                if (previous_is_active[element_id] != 0u)
                {
                    _ids_of_active_elements.push_back(element_id);
                }
            }
            return;
        }

        _last_domain_transition = target_transition;
        std::fill(std::begin(*_is_active), std::end(*_is_active), 1u);
        _ids_of_active_elements.clear();
        return;
'''
if text.count(old_no_support) != 1:
    raise RuntimeError("Unexpected A3 no-support activation branch")
text = text.replace(old_no_support, new_no_support)

# Publish the deferred event only after the inactive physical baseline has
# converged. Material reassignment is deliberately performed here, immediately
# before the owning process creates a fresh constitutive state.
insert_anchor = '''std::vector<std::unique_ptr<SourceTermBase>> ProcessVariable::createSourceTerms(
'''
publish_method = r'''StagedConstruction::DomainTransition
ProcessVariable::publishPendingActivation()
{
    if (!hasPendingActivationPublication())
    {
        return {};
    }

    auto transition = _pending_activation_transition;

    auto* const material_ids = materialIDs(_mesh);
    if (material_ids == nullptr)
    {
        OGS_FATAL("Activation material reassignment requires mesh MaterialIDs.");
    }

    for (auto const element_id : transition.newly_activated_element_ids)
    {
        std::optional<int> target_material_id;
        for (auto const& ds : _deactivated_subdomains)
        {
            if (!ds.activation_material_id ||
                !ds.deactivated_subdomain_mesh.bulk_element_ids.contains(
                    element_id))
            {
                continue;
            }
            if (target_material_id &&
                *target_material_id != *ds.activation_material_id)
            {
                OGS_FATAL(
                    "Conflicting activation material IDs for element {:d}.",
                    element_id);
            }
            target_material_id = ds.activation_material_id;
        }

        if (target_material_id)
        {
            (*material_ids)[element_id] = *target_material_id;
        }
        (*_is_active)[element_id] = 1u;
    }

    _last_domain_transition = transition;
    _pending_activation_transition = {};

    // The canonical no-support/backfill transition targets the fully active
    // domain. An empty active-ID vector is OGS' existing convention for that
    // case and avoids unnecessary selected-element assembly overhead.
    _ids_of_active_elements.clear();

    return transition;
}

'''
if text.count(insert_anchor) != 1:
    raise RuntimeError("Unexpected ProcessVariable source-term anchor")
text = text.replace(insert_anchor, publish_method + insert_anchor)
pv_cpp.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# 2. Inactive artificial BCs follow actual lifecycle state, not merely the
#    deactivation curve's nominal support. This is essential during the deferred
#    t_{n+1} baseline: the domain is intentionally still inactive although the
#    curve support has just ended.
# ---------------------------------------------------------------------------
bc = root / "ProcessLib/BoundaryConditionAndSourceTerm/DeactivatedSubdomainDirichlet.cpp"
text = bc.read_text(encoding="utf-8")
old = '''    if (isTimeInSupportInterval(_time_interval, t))
    {
        getEssentialBCValuesLocal(
            _parameter, _subdomain.mesh, inactive_nodes_in_bc_mesh,
            *_dof_table_boundary, _variable_id, _component_id, t, x, bc_values);
        return;
    }

    bc_values.ids.clear();
    bc_values.values.clear();
'''
new = '''    // The actual active/inactive cell state is authoritative. During deferred
    // staged-construction activation the nominal deactivation-curve support can
    // already have ended while the region intentionally remains inactive for
    // the physical baseline solve. Keep its artificial support until the
    // activation event is explicitly published.
    if (!inactive_nodes_in_bc_mesh.empty())
    {
        getEssentialBCValuesLocal(
            _parameter, _subdomain.mesh, inactive_nodes_in_bc_mesh,
            *_dof_table_boundary, _variable_id, _component_id, t, x, bc_values);
        return;
    }

    bc_values.ids.clear();
    bc_values.values.clear();
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected deactivated-subdomain Dirichlet tail")
bc.write_text(text.replace(old, new), encoding="utf-8")

# ---------------------------------------------------------------------------
# 3. Process API: generic publication hook and active-element refresh helper.
# ---------------------------------------------------------------------------
process_h = root / "ProcessLib/Process.h"
text = process_h.read_text(encoding="utf-8")
anchor = '''    virtual bool hasPendingPreSolveConstructionSubsteps() const { return false; }

    virtual std::optional<double> beginConstructionSubstepTrial()
'''
replacement = '''    virtual bool hasPendingPreSolveConstructionSubsteps() const { return false; }

    // Some construction events (placement/backfill) must be published only
    // after the physical t_{n+1} baseline converges. Default processes do not
    // participate.
    virtual bool hasPendingActivationPublication(int const /*process_id*/) const
    {
        return false;
    }

    virtual void publishPendingActivation(
        std::vector<GlobalVector*> const& /*x*/, double const /*t*/,
        double const /*dt*/, int const /*process_id*/)
    {
    }

    virtual std::optional<double> beginConstructionSubstepTrial()
'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected A4D Process construction API layout")
text = text.replace(anchor, replacement)

protected_anchor = '''protected:
    /** This function is for general cases, in which all equations of the
'''
protected_replacement = '''protected:
    // Recompute the process-wide active-element union after a deferred domain
    // transition has been explicitly published between physical and
    // construction solves.
    void refreshActiveElementIDs(int const process_id);

    /** This function is for general cases, in which all equations of the
'''
if text.count(protected_anchor) != 1:
    raise RuntimeError("Unexpected Process protected-section anchor")
process_h.write_text(text.replace(protected_anchor, protected_replacement), encoding="utf-8")

process_cpp = root / "ProcessLib/Process.cpp"
text = process_cpp.read_text(encoding="utf-8")
insert_anchor = '''void Process::preAssemble(const double t, double const dt,
'''
refresh_method = r'''void Process::refreshActiveElementIDs(int const process_id)
{
    auto const& variables_per_process = getProcessVariables(process_id);
    _ids_of_active_elements.clear();

    auto active_elements_ids = ranges::views::transform(
        [](auto const& variable)
        { return variable.get().getActiveElementIDs(); });

    if (ranges::any_of(variables_per_process | active_elements_ids,
                       [](auto const& vector) { return vector.empty(); }))
    {
        return;
    }

    _ids_of_active_elements =
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
}

'''
if text.count(insert_anchor) != 1:
    raise RuntimeError("Unexpected Process preAssemble anchor")
process_cpp.write_text(text.replace(insert_anchor, refresh_method + insert_anchor), encoding="utf-8")

# ---------------------------------------------------------------------------
# 4. SmallDeformation owns placement publication: rebind/fresh-state init,
#    activation transaction creation, newborn preTimestep, and active assembly
#    refresh all happen only after the inactive physical baseline has converged.
# ---------------------------------------------------------------------------
sd_h = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.h"
text = sd_h.read_text(encoding="utf-8")
anchor = '''    bool hasPendingPreSolveConstructionSubsteps() const override
    {
        return staged_construction_activation_transition_ &&
               !staged_construction_activation_transition_->complete();
    }

    std::optional<double> beginConstructionSubstepTrial() override
'''
replacement = '''    bool hasPendingPreSolveConstructionSubsteps() const override
    {
        return staged_construction_activation_transition_ &&
               !staged_construction_activation_transition_->complete();
    }

    bool hasPendingActivationPublication(int const process_id) const override
    {
        return getProcessVariables(process_id)[0]
            .get()
            .hasPendingActivationPublication();
    }

    void publishPendingActivation(std::vector<GlobalVector*> const& x,
                                  double const t, double const dt,
                                  int const process_id) override;

    std::optional<double> beginConstructionSubstepTrial() override
'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected A4D SmallDeformation pre-solve hook layout")
sd_h.write_text(text.replace(anchor, replacement), encoding="utf-8")

sd_cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = sd_cpp.read_text(encoding="utf-8")
insert_anchor = '''template <int DisplacementDim>
void SmallDeformationProcess<DisplacementDim>::preTimestepConcreteProcess(
'''
publish_impl = r'''template <int DisplacementDim>
void SmallDeformationProcess<DisplacementDim>::publishPendingActivation(
    std::vector<GlobalVector*> const& x, double const t, double const dt,
    int const process_id)
{
    auto& variable = getProcessVariables(process_id)[0].get();
    auto const transition = variable.publishPendingActivation();
    if (transition.newly_activated_element_ids.empty())
    {
        return;
    }

    refreshActiveElementIDs(process_id);

    // MaterialIDs have just been published. Rebind each newborn local
    // assembler to that target material and create an entirely fresh state.
    GlobalExecutor::executeSelectedMemberOnDereferenced(
        &LocalAssemblerInterface::initializeActivationPlacementState,
        local_assemblers_, transition.newly_activated_element_ids);

    staged_construction_activation_element_ids_ =
        transition.newly_activated_element_ids;
    staged_construction_activation_transition_ =
        std::make_unique<StagedConstruction::ActivationTransition>();

    GlobalExecutor::executeSelectedMemberOnDereferenced(
        &LocalAssemblerInterface::setActivationContributionScale,
        local_assemblers_, staged_construction_activation_element_ids_, 0.0);

    // These elements did not participate in the physical baseline preTimestep.
    // Give only the newborn set its ordinary local preTimestep initialization at
    // the already-converged placement configuration before construction solves.
    GlobalExecutor::executeSelectedMemberOnDereferenced(
        &LocalAssemblerInterface::preTimestep, local_assemblers_,
        staged_construction_activation_element_ids_,
        *_local_to_global_index_map, *x[process_id], t, dt);

    AssemblyMixin<SmallDeformationProcess<DisplacementDim>>::updateActiveElements();

    INFO(
        "Staged construction activation published for process #{:d}: {:d} "
        "element(s) at physical time t = {:g} after inactive baseline solve.",
        process_id, staged_construction_activation_element_ids_.size(), t);
}

'''
if text.count(insert_anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformation preTimestep definition anchor")
sd_cpp.write_text(text.replace(insert_anchor, publish_impl + insert_anchor), encoding="utf-8")

# ---------------------------------------------------------------------------
# 5. TimeLoop: after a successful physical solve publish deferred activation,
#    then let the already proven R3I construction-only driver advance lambda at
#    unchanged t/dt. The A4D pre-solve path remains available for any legacy
#    immediate activation transition, but deferred A4J events never enter it.
# ---------------------------------------------------------------------------
time_loop = root / "ProcessLib/TimeLoop.cpp"
text = time_loop.read_text(encoding="utf-8")
anchor = '''        bool const has_pending_construction = std::ranges::any_of(
            _per_process_data, [](auto const& process_data)
            { return process_data->process.hasPendingConstructionSubsteps(); });
'''
replacement = '''        // Placement/backfill is operator-split from physical time advancement.
        // First the t_{n+1} physical solve has converged with the domain still
        // inactive. Publish the placement now, then use construction-only solves
        // below at this same physical t/dt.
        for (auto& process_data : _per_process_data)
        {
            auto& process = process_data->process;
            int const process_id = process_data->process_id;
            if (!process.hasPendingActivationPublication(process_id))
            {
                continue;
            }

            INFO(
                "Staged construction inactive baseline completed for process "
                "#{:d} at physical time t = {:g}; publishing activation.",
                process_id, t());
            process.publishPendingActivation(_process_solutions, t(), dt,
                                             process_id);
        }

        bool const has_pending_construction = std::ranges::any_of(
            _per_process_data, [](auto const& process_data)
            { return process_data->process.hasPendingConstructionSubsteps(); });
'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected R3I pending-construction runtime anchor")
time_loop.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")

print("Applied OGS Staged Construction A4J deferred activation baseline split")
