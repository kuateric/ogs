#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# TH2M-T2B — literature-guided fresh-birth runtime implementation.
# Newly reactivated elements are born in the last converged displacement
# configuration, receive a fresh constitutive state, and use the full physical
# TH2M operator immediately. No stiffness/residual/material homotopy is used.

iface = root / "ProcessLib/TH2M/LocalAssemblerInterface.h"
text = iface.read_text(encoding="utf-8")
anchor = '''    virtual std::size_t setIPDataInitialConditions(
        std::string_view name, double const* values,
        int const integration_order) = 0;
'''
insert = '''    virtual std::size_t setIPDataInitialConditions(
        std::string_view name, double const* values,
        int const integration_order) = 0;

    void initializeActivationPlacementState(std::size_t const element_id,
                                            double const t)
    {
        if (element_id != element_.getID())
        {
            OGS_FATAL("TH2M activation element id does not match local assembler.");
        }
        initializeActivationPlacementStateConcrete(t);
    }

    virtual void initializeActivationPlacementStateConcrete(double const t) = 0;
'''
if text.count(anchor) != 1:
    raise RuntimeError("TH2M-T2B local-interface anchor changed")
iface.write_text(text.replace(anchor, insert, 1), encoding="utf-8")

header = root / "ProcessLib/TH2M/TH2MFEM.h"
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
        // Fresh constitutive birth: discard trial/committed material history.
        for (auto& material_state : this->material_states_)
        {
            material_state = ConstitutiveRelations::MaterialStateData<
                DisplacementDim>{
                this->solid_material_.createMaterialStateVariables()};
        }

        // Reuse canonical TH2M initialization for material-internal variables
        // and medium-dependent state, then impose stress-free birth unless a
        // future explicit placement-stress contract overrides it.
        initializeConcrete();
        for (unsigned ip = 0;
             ip < this->integration_method_.getNumberOfPoints(); ++ip)
        {
            this->current_states_[ip].eff_stress_data.sigma_eff.setZero();
            this->prev_states_[ip] = this->current_states_[ip];
            this->material_states_[ip].pushBackState();
        }

        activation_reference_pending_ = true;
        activation_reference_displacement_.resize(0);
        INFO("TH2M fresh-birth state initialized for element {:d} at t={:g}",
             this->element_.getID(), t);
    }
'''
if text.count(anchor) != 1:
    raise RuntimeError("TH2M-T2B TH2MFEM declaration anchor changed")
text = text.replace(anchor, insert, 1)
member_anchor = '''    std::vector<IpData> _ip_data;

    SecondaryData<
'''
member_insert = '''    std::vector<IpData> _ip_data;

    bool activation_reference_pending_ = false;
    Eigen::VectorXd activation_reference_displacement_;

    SecondaryData<
'''
if text.count(member_anchor) != 1:
    raise RuntimeError("TH2M-T2B TH2MFEM member anchor changed")
header.write_text(text.replace(member_anchor, member_insert, 1), encoding="utf-8")

impl = root / "ProcessLib/TH2M/TH2MFEM-impl.h"
text = impl.read_text(encoding="utf-8")
anchor = '''    auto const displacement_prev =
        local_x_prev.template segment<displacement_size>(displacement_index);

    auto const& medium =
'''
insert = '''    auto const displacement_prev =
        local_x_prev.template segment<displacement_size>(displacement_index);

    // The last converged configuration is the birth/reference configuration.
    // Capture local_x_prev, never the current Newton trial, exactly once.
    if (activation_reference_pending_)
    {
        activation_reference_displacement_ = displacement_prev;
        activation_reference_pending_ = false;
        INFO("TH2M stress-free birth reference captured for element {:d}",
             this->element_.getID());
    }
    auto const displacement_constitutive =
        activation_reference_displacement_.size() == 0
            ? Eigen::VectorXd(displacement)
            : Eigen::VectorXd(displacement - activation_reference_displacement_);
    auto const displacement_prev_constitutive =
        activation_reference_displacement_.size() == 0
            ? Eigen::VectorXd(displacement_prev)
            : Eigen::VectorXd(displacement_prev - activation_reference_displacement_);

    auto const& medium =
'''
if text.count(anchor) != 1:
    raise RuntimeError("TH2M-T2B displacement extraction anchor changed")
text = text.replace(anchor, insert, 1)
text = text.replace('ip_out.eps_data.eps.noalias() = Bu * displacement;',
                    'ip_out.eps_data.eps.noalias() = Bu * displacement_constitutive;', 1)
text = text.replace('Bu * displacement_prev, prev_state.mechanical_strain_data,',
                    'Bu * displacement_prev_constitutive, prev_state.mechanical_strain_data,', 1)
text = text.replace('ip_cv.beta_p_SR, ip_out.eps_data,\n            Bu * displacement_prev, prev_state.porosity_data,',
                    'ip_cv.beta_p_SR, ip_out.eps_data,\n            Bu * displacement_prev_constitutive, prev_state.porosity_data,', 1)
impl.write_text(text, encoding="utf-8")

process = root / "ProcessLib/TH2M/TH2MProcess.cpp"
text = process.read_text(encoding="utf-8")
include_anchor = '#include <cassert>\n'
if text.count(include_anchor) != 1:
    raise RuntimeError("TH2M-T2B include anchor changed")
text = text.replace(include_anchor, '#include <algorithm>\n#include <cassert>\n#include <vector>\n', 1)
anchor = '''    AssemblyMixin<TH2MProcess<DisplacementDim>>::updateActiveElements();
}
'''
insert = '''    auto const active_before = getActiveElementIDs();
    AssemblyMixin<TH2MProcess<DisplacementDim>>::updateActiveElements();
    auto const& active_after = getActiveElementIDs();

    std::vector<std::size_t> newly_activated;
    std::set_difference(active_after.begin(), active_after.end(),
                        active_before.begin(), active_before.end(),
                        std::back_inserter(newly_activated));
    if (!newly_activated.empty())
    {
        GlobalExecutor::executeSelectedMemberOnDereferenced(
            &LocalAssemblerInterface<DisplacementDim>::
                initializeActivationPlacementState,
            local_assemblers_, newly_activated, t);
        INFO("TH2M fresh-birth event published for {:d} element(s) at t={:g}",
             newly_activated.size(), t);
    }
}
'''
if text.count(anchor) != 1:
    raise RuntimeError("TH2M-T2B active-set update anchor changed")
process.write_text(text.replace(anchor, insert, 1), encoding="utf-8")

# Hard safety gates: T2B must not introduce any numerical weakening mechanism.
joined = '\n'.join(p.read_text(encoding='utf-8') for p in (iface, header, impl, process))
for forbidden in ('activation_contribution_scale', 'stiffness scaling', 'residual homotopy', 'material homotopy'):
    # comments may contain the literature wording for the last three; only code
    # identifier activation_contribution_scale is an unconditional hard fail.
    if forbidden == 'activation_contribution_scale' and forbidden in joined:
        raise RuntimeError('TH2M-T2B forbidden activation scaling mechanism detected')

print('TH2M-T2B patch applied: fresh state + last-converged u_birth + full operator')
print('canonical_ogs_sha=adf770974c7ee0435702fe617634d03d17ab7cb8')
