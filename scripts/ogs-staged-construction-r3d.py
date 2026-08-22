#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

process_h = root / "ProcessLib/Process.h"
text = process_h.read_text(encoding="utf-8")
if "#include <optional>\n" not in text:
    text = text.replace("#include <string>\n", "#include <optional>\n#include <string>\n", 1)

anchor = '''    void updateDeactivatedSubdomains(double const time, const int process_id);\n\n    virtual bool isMonolithicSchemeUsed() const\n'''
replacement = '''    void updateDeactivatedSubdomains(double const time, const int process_id);\n\n    // Staged-construction continuation hook.  Default processes do not\n    // participate.  A participating process owns its construction transaction;\n    // the TimeLoop only opens/accepts/rejects trials at unchanged physical time.\n    virtual bool hasPendingConstructionSubsteps() const { return false; }\n\n    virtual std::optional<double> beginConstructionSubstepTrial()\n    {\n        return std::nullopt;\n    }\n\n    virtual void commitConstructionSubstepTrial() {}\n    virtual void rollbackConstructionSubstepTrial() {}\n\n    virtual bool isMonolithicSchemeUsed() const\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected Process.h staged-construction API anchor")
text = text.replace(anchor, replacement)
process_h.write_text(text, encoding="utf-8")

sd_h = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.h"
text = sd_h.read_text(encoding="utf-8")
include_anchor = '#include "ProcessLib/StagedConstruction/MechanicalRemovalEventBridge.h"\n'
includes = '''#include "ProcessLib/StagedConstruction/MechanicalRemovalEventBridge.h"\n#include "ProcessLib/StagedConstruction/AdaptiveTransitionController.h"\n#include "ProcessLib/StagedConstruction/AdaptiveRemovalTransaction.h"\n'''
if "AdaptiveRemovalTransaction.h" not in text:
    if text.count(include_anchor) != 1:
        raise RuntimeError("Unexpected SmallDeformation staged-construction include anchor")
    text = text.replace(include_anchor, includes)

method_anchor = '''    bool isLinear() const override;\n    //! @}\n\nprivate:\n'''
method_replacement = '''    bool isLinear() const override;\n    //! @}\n\n    bool hasPendingConstructionSubsteps() const override\n    {\n        return staged_construction_removal_transaction_ &&\n               !staged_construction_removal_transaction_->isComplete();\n    }\n\n    std::optional<double> beginConstructionSubstepTrial() override\n    {\n        if (!hasPendingConstructionSubsteps())\n        {\n            return std::nullopt;\n        }\n        return staged_construction_removal_transaction_->beginTrial();\n    }\n\n    void commitConstructionSubstepTrial() override\n    {\n        if (!staged_construction_removal_transaction_)\n        {\n            OGS_FATAL("No staged-construction trial is available to commit.");\n        }\n        staged_construction_removal_transaction_->commitTrial();\n    }\n\n    void rollbackConstructionSubstepTrial() override\n    {\n        if (!staged_construction_removal_transaction_)\n        {\n            OGS_FATAL("No staged-construction trial is available to roll back.");\n        }\n        staged_construction_removal_transaction_->rejectTrial();\n    }\n\nprivate:\n'''
if text.count(method_anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformation public-method anchor")
text = text.replace(method_anchor, method_replacement)

member_anchor = '''    std::optional<StagedConstruction::MechanicalRemovalTransition>\n        staged_construction_pending_removal_transition_;\n\n    MeshLib::PropertyVector<double>* material_forces_ = nullptr;\n'''
member_replacement = '''    std::optional<StagedConstruction::MechanicalRemovalTransition>\n        staged_construction_pending_removal_transition_;\n\n    // These objects own only the numerical construction coordinate.  They do\n    // not own or commit constitutive state; MFront/MGIS remains committed only\n    // by the existing postTimestep() path after the full construction release.\n    std::unique_ptr<StagedConstruction::AdaptiveTransitionController>\n        staged_construction_transition_controller_;\n    std::unique_ptr<StagedConstruction::AdaptiveRemovalTransaction>\n        staged_construction_removal_transaction_;\n\n    MeshLib::PropertyVector<double>* material_forces_ = nullptr;\n'''
if text.count(member_anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformation R2J member anchor")
text = text.replace(member_anchor, member_replacement)
sd_h.write_text(text, encoding="utf-8")

sd_cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = sd_cpp.read_text(encoding="utf-8")
anchor = '''        staged_construction_pending_removal_transition_ =\n            StagedConstruction::buildMechanicalRemovalFromDomainTransition(\n                domain_transition, removed_element_contributions,\n                remaining_active_element_dofs);\n    }\n\n    GlobalExecutor::executeSelectedMemberOnDereferenced(\n'''
replacement = '''        // Reset the coordinator before replacing the transition it references.\n        staged_construction_removal_transaction_.reset();\n        staged_construction_transition_controller_.reset();\n\n        staged_construction_pending_removal_transition_ =\n            StagedConstruction::buildMechanicalRemovalFromDomainTransition(\n                domain_transition, removed_element_contributions,\n                remaining_active_element_dofs);\n\n        staged_construction_transition_controller_ = std::make_unique<\n            StagedConstruction::AdaptiveTransitionController>(\n            StagedConstruction::AdaptiveTransitionController::Config{});\n        staged_construction_removal_transaction_ = std::make_unique<\n            StagedConstruction::AdaptiveRemovalTransaction>(\n            *staged_construction_transition_controller_,\n            *staged_construction_pending_removal_transition_);\n    }\n\n    GlobalExecutor::executeSelectedMemberOnDereferenced(\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformation R2J transition creation anchor")
text = text.replace(anchor, replacement)
sd_cpp.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction R3D process-level adaptive transaction bridge")
