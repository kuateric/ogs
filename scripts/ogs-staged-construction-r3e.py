#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# R3E introduces an explicit construction-state transaction hook before the
# TimeLoop starts driving repeated nonlinear solves.  A successful construction
# substep must advance the constitutive baseline without advancing physical
# time.  A rejected trial must NOT call pushBackState(); the next assembly then
# re-evaluates s1/current state from the last committed s0/prev state.

process_h = root / "ProcessLib/Process.h"
text = process_h.read_text(encoding="utf-8")
anchor = '''    virtual void commitConstructionSubstepTrial() {}\n    virtual void rollbackConstructionSubstepTrial() {}\n\n    virtual bool isMonolithicSchemeUsed() const\n'''
replacement = '''    virtual void commitConstructionSubstepTrial() {}\n    virtual void rollbackConstructionSubstepTrial() {}\n\n    // Process/material-state transaction hooks for an accepted/rejected\n    // construction continuation trial.  These hooks do not advance physical\n    // time.  Default processes do not own constitutive construction state.\n    virtual void commitConstructionSubstepState() {}\n    virtual void rollbackConstructionSubstepState() {}\n\n    virtual bool isMonolithicSchemeUsed() const\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected Process.h R3D construction hook anchor")
text = text.replace(anchor, replacement)
process_h.write_text(text, encoding="utf-8")

la_h = root / "ProcessLib/SmallDeformation/LocalAssemblerInterface.h"
text = la_h.read_text(encoding="utf-8")
anchor = '''    static auto getReflectionDataForOutput()\n    {\n        using Self = SmallDeformationLocalAssemblerInterface<DisplacementDim>;\n\n        return ProcessLib::Reflection::reflectWithoutName(\n            &Self::current_states_, &Self::output_data_);\n    }\n\nprotected:\n'''
replacement = '''    static auto getReflectionDataForOutput()\n    {\n        using Self = SmallDeformationLocalAssemblerInterface<DisplacementDim>;\n\n        return ProcessLib::Reflection::reflectWithoutName(\n            &Self::current_states_, &Self::output_data_);\n    }\n\n    // Commit the already converged constitutive trial state as the baseline for\n    // the next construction continuation substep, without evaluating the\n    // material model again and without advancing physical time.  For MFront\n    // this calls MaterialStateVariablesMFront::pushBackState(), i.e.\n    // mgis::behaviour::update(s0 <- s1).\n    void commitConstructionSubstepState()\n    {\n        for (auto& material_state : material_states_)\n        {\n            material_state.pushBackState();\n        }\n        prev_states_ = current_states_;\n    }\n\n    // Rejected nonlinear trials are intentionally not pushed back.  The\n    // committed material s0 and prev_states_ therefore remain unchanged; the\n    // next assembly overwrites the uncommitted s1/current state from that\n    // committed baseline.\n    void rollbackConstructionSubstepState() {}\n\nprotected:\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformation local-assembler reflection anchor")
text = text.replace(anchor, replacement)
la_h.write_text(text, encoding="utf-8")

sd_h = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.h"
text = sd_h.read_text(encoding="utf-8")
anchor = '''    void rollbackConstructionSubstepTrial() override\n    {\n        if (!staged_construction_removal_transaction_)\n        {\n            OGS_FATAL("No staged-construction trial is available to roll back.");\n        }\n        staged_construction_removal_transaction_->rejectTrial();\n    }\n\nprivate:\n'''
replacement = '''    void rollbackConstructionSubstepTrial() override\n    {\n        if (!staged_construction_removal_transaction_)\n        {\n            OGS_FATAL("No staged-construction trial is available to roll back.");\n        }\n        staged_construction_removal_transaction_->rejectTrial();\n    }\n\n    void commitConstructionSubstepState() override\n    {\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &SmallDeformationLocalAssemblerInterface<DisplacementDim>::\n                commitConstructionSubstepState,\n            local_assemblers_, getActiveElementIDs());\n    }\n\n    void rollbackConstructionSubstepState() override\n    {\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &SmallDeformationLocalAssemblerInterface<DisplacementDim>::\n                rollbackConstructionSubstepState,\n            local_assemblers_, getActiveElementIDs());\n    }\n\nprivate:\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected SmallDeformation R3D rollback hook anchor")
text = text.replace(anchor, replacement)
sd_h.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction R3E constitutive construction-state hooks")
