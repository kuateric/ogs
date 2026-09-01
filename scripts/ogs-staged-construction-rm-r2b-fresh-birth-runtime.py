#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# RM-R2B — stress-free hydraulic-mechanical fresh birth.
# Policy: newly activated elements use the last converged displacement and
# liquid-pressure fields as explicit placement references, receive a fresh
# constitutive state, zero effective birth stress unless a future explicit
# placement-stress contract overrides it, and use the full physical RM operator
# immediately. No stiffness/residual/material homotopy is introduced.

iface = root / "ProcessLib/RichardsMechanics/LocalAssemblerInterface.h"
text = iface.read_text(encoding="utf-8")
anchor = '''    std::size_t setIPDataInitialConditions(std::string_view name,
                                           double const* values,
                                           int const integration_order)
    {
'''
insert = '''    void initializeActivationPlacementState(std::size_t const element_id,
                                            double const t)
    {
        if (element_id != element_.getID())
        {
            OGS_FATAL("RM activation element id does not match local assembler.");
        }
        initializeActivationPlacementStateConcrete(t);
    }

    virtual void initializeActivationPlacementStateConcrete(double const t) = 0;

    std::size_t setIPDataInitialConditions(std::string_view name,
                                           double const* values,
                                           int const integration_order)
    {
'''
if text.count(anchor) != 1:
    raise RuntimeError("RM-R2B local-interface anchor changed")
iface.write_text(text.replace(anchor, insert, 1), encoding="utf-8")

header = root / "ProcessLib/RichardsMechanics/RichardsMechanicsFEM.h"
text = header.read_text(encoding="utf-8")
anchor = '''    void setInitialConditionsConcrete(Eigen::VectorXd const local_x,
                                      double const t,
                                      int const process_id) override;
'''
insert = '''    void setInitialConditionsConcrete(Eigen::VectorXd const local_x,
                                      double const t,
                                      int const process_id) override;

    void initializeActivationPlacementStateConcrete(double const t) override
    {
        // Fresh constitutive birth: discard trial and committed material history.
        for (auto& material_state : this->material_states_)
        {
            material_state = ProcessLib::ThermoRichardsMechanics::
                MaterialStateData<DisplacementDim>{
                    this->solid_material_.createMaterialStateVariables()};
        }

        // Canonical initialization establishes material-internal variables and
        // medium state. Placement birth itself is stress free unless explicitly
        // overridden by a later placement-stress contract.
        initializeConcrete();
        for (unsigned ip = 0;
             ip < this->integration_method_.getNumberOfPoints(); ++ip)
        {
            std::get<ProcessLib::ConstitutiveRelations::EffectiveStressData<
                DisplacementDim>>(this->current_states_[ip]).sigma_eff.setZero();
            std::get<StrainData<DisplacementDim>>(
                this->current_states_[ip]).eps.setZero();
            this->prev_states_[ip] = this->current_states_[ip];
            this->material_states_[ip].pushBackState();
        }

        activation_reference_pending_ = true;
        activation_reference_displacement_.resize(0);
        activation_reference_pressure_.resize(0);
        INFO("RM fresh-birth state initialized for element {:d} at t={:g}",
             this->element_.getID(), t);
    }
'''
if text.count(anchor) != 1:
    raise RuntimeError("RM-R2B FEM declaration anchor changed")
text = text.replace(anchor, insert, 1)
member_anchor = '''    std::vector<IpData, Eigen::aligned_allocator<IpData>> ip_data_;

    SecondaryData<
'''
member_insert = '''    std::vector<IpData, Eigen::aligned_allocator<IpData>> ip_data_;

    bool activation_reference_pending_ = false;
    Eigen::VectorXd activation_reference_displacement_;
    Eigen::VectorXd activation_reference_pressure_;

    SecondaryData<
'''
if text.count(member_anchor) != 1:
    raise RuntimeError("RM-R2B FEM member anchor changed")
header.write_text(text.replace(member_anchor, member_insert, 1), encoding="utf-8")

impl = root / "ProcessLib/RichardsMechanics/RichardsMechanicsFEM-impl.h"
text = impl.read_text(encoding="utf-8")
# Both full and Jacobian assembly paths expose the same localDOF extraction.
anchor = '''    auto const [p_L, u] = localDOF(local_x);
    auto const [p_L_prev, u_prev] = localDOF(local_x_prev);
'''
insert = '''    auto const [p_L, u] = localDOF(local_x);
    auto const [p_L_prev, u_prev] = localDOF(local_x_prev);

    // Capture the last converged state, never the current Newton trial, exactly
    // once when an element is born. This is the installation/reference state.
    if (activation_reference_pending_)
    {
        activation_reference_displacement_ = u_prev;
        activation_reference_pressure_ = p_L_prev;
        activation_reference_pending_ = false;
        INFO("RM birth reference captured for element {:d}: u_birth from last converged state, p_L0 from last converged hydraulic state",
             this->element_.getID());
    }
    auto const u_constitutive =
        activation_reference_displacement_.size() == 0
            ? Eigen::VectorXd(u)
            : Eigen::VectorXd(u - activation_reference_displacement_);
'''
count = text.count(anchor)
if count < 1:
    raise RuntimeError("RM-R2B localDOF anchor changed")
text = text.replace(anchor, insert)
# Mechanical constitutive strain must be relative to the birth configuration in
# every assembled RM path; initialization remains canonical and untouched.
assembled_token = 'eps.eps.noalias() = B * u;'
if text.count(assembled_token) < 1:
    raise RuntimeError("RM-R2B assembled strain anchor changed")
text = text.replace(assembled_token, 'eps.eps.noalias() = B * u_constitutive;')

# At first active assembly explicitly seed current+previous micro hydraulic state
# from p_L0 (= last converged nodal pressure at birth). This keeps the hydraulic
# constitutive baseline synchronized with the mechanical birth reference.
pressure_anchor = '''        double p_cap_prev_ip;
        NumLib::shapeFunctionInterpolate(-p_L_prev, N_p, p_cap_prev_ip);
'''
pressure_insert = '''        double p_cap_prev_ip;
        NumLib::shapeFunctionInterpolate(-p_L_prev, N_p, p_cap_prev_ip);

        if (activation_reference_pressure_.size() != 0)
        {
            double p_L0_ip;
            NumLib::shapeFunctionInterpolate(activation_reference_pressure_,
                                             N_p, p_L0_ip);
            auto& p_L_m = std::get<MicroPressure>(this->current_states_[ip]);
            auto& p_L_m_prev =
                std::get<PrevState<MicroPressure>>(this->prev_states_[ip]);
            *p_L_m = p_L0_ip;
            **p_L_m_prev = p_L0_ip;
        }
'''
if text.count(pressure_anchor) < 1:
    raise RuntimeError("RM-R2B hydraulic placement anchor changed")
text = text.replace(pressure_anchor, pressure_insert)
impl.write_text(text, encoding="utf-8")

process_header = root / "ProcessLib/RichardsMechanics/RichardsMechanicsProcess.h"
text = process_header.read_text(encoding="utf-8")
anchor = '''    std::vector<std::unique_ptr<LocalAssemblerIF>> local_assemblers_;

    std::unique_ptr<NumLib::LocalToGlobalIndexMap>
'''
insert = '''    std::vector<std::unique_ptr<LocalAssemblerIF>> local_assemblers_;

    std::vector<std::size_t> previous_construction_active_element_ids_;
    bool previous_construction_active_element_ids_initialized_ = false;

    std::unique_ptr<NumLib::LocalToGlobalIndexMap>
'''
if text.count(anchor) != 1:
    raise RuntimeError("RM-R2B process member anchor changed")
process_header.write_text(text.replace(anchor, insert, 1), encoding="utf-8")

process = root / "ProcessLib/RichardsMechanics/RichardsMechanicsProcess.cpp"
text = process.read_text(encoding="utf-8")
include_anchor = '#include <cassert>\n'
if text.count(include_anchor) != 1:
    raise RuntimeError("RM-R2B include anchor changed")
text = text.replace(include_anchor, '#include <algorithm>\n#include <cassert>\n#include <iterator>\n#include <vector>\n', 1)
anchor = '''    AssemblyMixin<
        RichardsMechanicsProcess<DisplacementDim>>::updateActiveElements();
}
'''
insert = '''    AssemblyMixin<
        RichardsMechanicsProcess<DisplacementDim>>::updateActiveElements();

    auto current_active = getActiveElementIDs();
    if (current_active.empty())
    {
        current_active.reserve(this->getMesh().getElements().size());
        for (auto const* element : this->getMesh().getElements())
        {
            current_active.push_back(element->getID());
        }
    }
    std::sort(current_active.begin(), current_active.end());

    if (previous_construction_active_element_ids_initialized_)
    {
        std::vector<std::size_t> newly_activated;
        std::set_difference(
            current_active.begin(), current_active.end(),
            previous_construction_active_element_ids_.begin(),
            previous_construction_active_element_ids_.end(),
            std::back_inserter(newly_activated));
        if (!newly_activated.empty())
        {
            GlobalExecutor::executeSelectedMemberOnDereferenced(
                &LocalAssemblerIF::initializeActivationPlacementState,
                local_assemblers_, newly_activated, t);
            INFO("RM fresh-birth event published for {:d} element(s) at t={:g}",
                 newly_activated.size(), t);
        }
    }

    previous_construction_active_element_ids_ = std::move(current_active);
    previous_construction_active_element_ids_initialized_ = true;
}
'''
if text.count(anchor) != 1:
    raise RuntimeError("RM-R2B active-set update anchor changed")
process.write_text(text.replace(anchor, insert, 1), encoding="utf-8")

joined = '\n'.join(p.read_text(encoding='utf-8') for p in
                   (iface, header, impl, process_header, process))
for forbidden in ('activation_contribution_scale', 'stiffness_scale',
                  'residual_homotopy', 'material_homotopy'):
    if forbidden in joined:
        raise RuntimeError(f'RM-R2B forbidden numerical weakening mechanism detected: {forbidden}')

print('RM-R2B patch applied: fresh constitutive state + zero birth stress + last-converged u_birth + explicit p_L0 + full physical RM operator')
print('canonical_ogs_sha=adf770974c7ee0435702fe617634d03d17ab7cb8')
