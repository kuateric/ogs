#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4B: controlled placement enters SmallDeformation with zero assembled
# contribution and is ramped to full contribution at unchanged physical time.
# The continuation state itself remains process-neutral (ActivationTransition).

la = root / "ProcessLib/SmallDeformation/LocalAssemblerInterface.h"
text = la.read_text(encoding="utf-8")
anchor = '''    // Commit the already converged constitutive trial state as the baseline for\n'''
method = '''    void setActivationContributionScale(std::size_t const /*element_id*/,\n                                        double const scale)\n    {\n        if (!(scale >= 0.0 && scale <= 1.0))\n        {\n            OGS_FATAL("Activation contribution scale must lie in [0,1].");\n        }\n        activation_contribution_scale_ = scale;\n    }\n\n    double activationContributionScale() const\n    {\n        return activation_contribution_scale_;\n    }\n\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected LocalAssembler commit anchor")
text = text.replace(anchor, method + anchor)

member_anchor = '''protected:\n    NumLib::Fem::Integration::GenericIntegrationMethod const& integration_method_;\n'''
member_replacement = '''protected:\n    double activation_contribution_scale_ = 1.0;\n\n    NumLib::Fem::Integration::GenericIntegrationMethod const& integration_method_;\n'''
if text.count(member_anchor) != 1:
    raise RuntimeError("Unexpected LocalAssembler protected member anchor")
text = text.replace(member_anchor, member_replacement)
la.write_text(text, encoding="utf-8")

fem = root / "ProcessLib/SmallDeformation/SmallDeformationFEM.h"
text = fem.read_text(encoding="utf-8")
anchor = '''            local_Jac.noalias() += B.transpose() * C * B * w;\n        }\n    }\n\n    void postTimestepConcrete'''
replacement = '''            local_Jac.noalias() += B.transpose() * C * B * w;\n        }\n\n        // Newly placed material is introduced through a construction\n        // coordinate at fixed physical time. Residual and consistent tangent\n        // must use the same scale to retain Newton consistency.\n        auto const activation_scale = this->activationContributionScale();\n        local_b *= activation_scale;\n        local_Jac *= activation_scale;\n    }\n\n    void postTimestepConcrete'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformation assembly tail")
fem.write_text(text.replace(anchor, replacement), encoding="utf-8")

sd_h = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.h"
text = sd_h.read_text(encoding="utf-8")
include_anchor = '#include "ProcessLib/StagedConstruction/AdaptiveRemovalTransaction.h"\n'
if '#include "ProcessLib/StagedConstruction/ActivationTransition.h"\n' not in text:
    if text.count(include_anchor) != 1:
        raise RuntimeError("Unexpected SmallDeformation staged construction include anchor")
    text = text.replace(include_anchor, include_anchor + '#include "ProcessLib/StagedConstruction/ActivationTransition.h"\n')

old_methods = '''    bool hasPendingConstructionSubsteps() const override\n    {\n        return staged_construction_removal_transaction_ &&\n               !staged_construction_removal_transaction_->isComplete();\n    }\n\n    std::optional<double> beginConstructionSubstepTrial() override\n    {\n        if (!hasPendingConstructionSubsteps())\n        {\n            return std::nullopt;\n        }\n        return staged_construction_removal_transaction_->beginTrial();\n    }\n\n    void commitConstructionSubstepTrial() override\n    {\n        if (!staged_construction_removal_transaction_)\n        {\n            OGS_FATAL("No staged-construction trial is available to commit.");\n        }\n        staged_construction_removal_transaction_->commitTrial();\n    }\n\n    void rollbackConstructionSubstepTrial() override\n    {\n        if (!staged_construction_removal_transaction_)\n        {\n            OGS_FATAL("No staged-construction trial is available to roll back.");\n        }\n        staged_construction_removal_transaction_->rejectTrial();\n    }\n'''
new_methods = '''    bool hasPendingConstructionSubsteps() const override\n    {\n        bool const removal_pending =\n            staged_construction_removal_transaction_ &&\n            !staged_construction_removal_transaction_->isComplete();\n        bool const activation_pending =\n            staged_construction_activation_transition_ &&\n            !staged_construction_activation_transition_->complete();\n        return removal_pending || activation_pending;\n    }\n\n    std::optional<double> beginConstructionSubstepTrial() override\n    {\n        if (staged_construction_activation_transition_ &&\n            !staged_construction_activation_transition_->complete())\n        {\n            auto const lambda =\n                staged_construction_activation_transition_->beginTrial();\n            GlobalExecutor::executeSelectedMemberOnDereferenced(\n                &LocalAssemblerInterface::setActivationContributionScale,\n                local_assemblers_, staged_construction_activation_element_ids_,\n                lambda);\n            return lambda;\n        }\n        if (staged_construction_removal_transaction_ &&\n            !staged_construction_removal_transaction_->isComplete())\n        {\n            return staged_construction_removal_transaction_->beginTrial();\n        }\n        return std::nullopt;\n    }\n\n    void commitConstructionSubstepTrial() override\n    {\n        if (staged_construction_activation_transition_ &&\n            !staged_construction_activation_transition_->complete())\n        {\n            staged_construction_activation_transition_->acceptTrial();\n            return;\n        }\n        if (!staged_construction_removal_transaction_)\n        {\n            OGS_FATAL("No staged-construction trial is available to commit.");\n        }\n        staged_construction_removal_transaction_->commitTrial();\n    }\n\n    void rollbackConstructionSubstepTrial() override\n    {\n        if (staged_construction_activation_transition_ &&\n            !staged_construction_activation_transition_->complete())\n        {\n            staged_construction_activation_transition_->rejectTrial();\n            auto const lambda =\n                staged_construction_activation_transition_->committedLambda();\n            GlobalExecutor::executeSelectedMemberOnDereferenced(\n                &LocalAssemblerInterface::setActivationContributionScale,\n                local_assemblers_, staged_construction_activation_element_ids_,\n                lambda);\n            return;\n        }\n        if (!staged_construction_removal_transaction_)\n        {\n            OGS_FATAL("No staged-construction trial is available to roll back.");\n        }\n        staged_construction_removal_transaction_->rejectTrial();\n    }\n'''
if text.count(old_methods) != 1:
    raise RuntimeError("Unexpected R3D construction hook block")
text = text.replace(old_methods, new_methods)

member_anchor = '''    std::unique_ptr<StagedConstruction::AdaptiveRemovalTransaction>\n        staged_construction_removal_transaction_;\n\n    MeshLib::PropertyVector<double>* material_forces_ = nullptr;\n'''
member_replacement = '''    std::unique_ptr<StagedConstruction::AdaptiveRemovalTransaction>\n        staged_construction_removal_transaction_;\n\n    std::unique_ptr<StagedConstruction::ActivationTransition>\n        staged_construction_activation_transition_;\n    std::vector<std::size_t> staged_construction_activation_element_ids_;\n\n    MeshLib::PropertyVector<double>* material_forces_ = nullptr;\n'''
if text.count(member_anchor) != 1:
    raise RuntimeError("Unexpected R3D transaction member anchor")
sd_h.write_text(text.replace(member_anchor, member_replacement), encoding="utf-8")

sd_cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = sd_cpp.read_text(encoding="utf-8")
anchor = '''    if (!domain_transition.newly_activated_element_ids.empty())\n    {\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &LocalAssemblerInterface::initializeActivationPlacementState,\n            local_assemblers_, domain_transition.newly_activated_element_ids);\n    }\n\n    if (!domain_transition.newly_deactivated_element_ids.empty())\n'''
replacement = '''    if (!domain_transition.newly_activated_element_ids.empty())\n    {\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &LocalAssemblerInterface::initializeActivationPlacementState,\n            local_assemblers_, domain_transition.newly_activated_element_ids);\n\n        staged_construction_activation_element_ids_ =\n            domain_transition.newly_activated_element_ids;\n        staged_construction_activation_transition_ = std::make_unique<\n            StagedConstruction::ActivationTransition>();\n\n        // Placement begins contribution-free. The existing TimeLoop\n        // construction driver advances this scale at unchanged physical time.\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &LocalAssemblerInterface::setActivationContributionScale,\n            local_assemblers_, staged_construction_activation_element_ids_, 0.0);\n    }\n\n    if (!domain_transition.newly_deactivated_element_ids.empty())\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected A1 activation lifecycle anchor")
sd_cpp.write_text(text.replace(anchor, replacement), encoding="utf-8")

print("Applied OGS Staged Construction A4B controlled activation runtime scaling")
