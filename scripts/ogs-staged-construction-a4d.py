#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4D: newly activated elements introduce DOFs that must never enter a physical
# Newton solve with exactly zero assembled stiffness.  Open the first adaptive
# activation trial before the ordinary physical solve.  That solve owns the
# single time-discretization advance; rejected activation trials are retried at
# the same physical t/dt with the construction-only solve helper.
#
# A4M refinement: a successful pre-solve activation is still the physical
# increment owner. Its constitutive state must therefore be committed exactly
# once by the ordinary postTimestep() lifecycle. Committing it here as well
# would push MFront/MGIS s1->s0 and then re-integrate/commit the same physical
# increment a second time in postTimestep(). Construction-only continuation
# state commits remain owned by the R3I continuation path.

process_h = root / "ProcessLib/Process.h"
text = process_h.read_text(encoding="utf-8")
anchor = '''    virtual bool hasPendingConstructionSubsteps() const { return false; }\n\n    virtual std::optional<double> beginConstructionSubstepTrial()\n'''
replacement = '''    virtual bool hasPendingConstructionSubsteps() const { return false; }\n\n    // Activation differs from removal in one important respect: newly active\n    // DOFs must enter Newton with a non-zero trial contribution.  Processes\n    // that return true here ask TimeLoop to open the first construction trial\n    // before the ordinary physical nonlinear solve.\n    virtual bool hasPendingPreSolveConstructionSubsteps() const { return false; }\n\n    virtual std::optional<double> beginConstructionSubstepTrial()\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected Process.h construction-hook layout")
process_h.write_text(text.replace(anchor, replacement), encoding="utf-8")

sd_h = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.h"
text = sd_h.read_text(encoding="utf-8")
anchor = '''    bool hasPendingConstructionSubsteps() const override\n    {\n        bool const removal_pending =\n            staged_construction_removal_transaction_ &&\n            !staged_construction_removal_transaction_->isComplete();\n        bool const activation_pending =\n            staged_construction_activation_transition_ &&\n            !staged_construction_activation_transition_->complete();\n        return removal_pending || activation_pending;\n    }\n\n    std::optional<double> beginConstructionSubstepTrial() override\n'''
replacement = '''    bool hasPendingConstructionSubsteps() const override\n    {\n        bool const removal_pending =\n            staged_construction_removal_transaction_ &&\n            !staged_construction_removal_transaction_->isComplete();\n        bool const activation_pending =\n            staged_construction_activation_transition_ &&\n            !staged_construction_activation_transition_->complete();\n        return removal_pending || activation_pending;\n    }\n\n    bool hasPendingPreSolveConstructionSubsteps() const override\n    {\n        return staged_construction_activation_transition_ &&\n               !staged_construction_activation_transition_->complete();\n    }\n\n    std::optional<double> beginConstructionSubstepTrial() override\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected A4B SmallDeformation construction-hook layout")
sd_h.write_text(text.replace(anchor, replacement), encoding="utf-8")

time_loop = root / "ProcessLib/TimeLoop.cpp"
text = time_loop.read_text(encoding="utf-8")
old = '''    auto const nonlinear_solver_status = solveOneTimeStepOneProcess(\n        x, x_prev, timestep_id, t(), dt, process_data, outputs);\n\n    INFO("[time] Solving process #{:d} took {:g} s in time step #{:d}",\n         process_data.process_id, time_timestep_process.elapsed(), timestep_id);\n\n    return nonlinear_solver_status;\n'''
new = '''    NumLib::NonlinearSolverStatus nonlinear_solver_status;\n\n    if (!process_data.process.hasPendingPreSolveConstructionSubsteps())\n    {\n        nonlinear_solver_status = solveOneTimeStepOneProcess(\n            x, x_prev, timestep_id, t(), dt, process_data, outputs);\n    }\n    else\n    {\n        auto& process = process_data.process;\n        int const process_id = process_data.process_id;\n        auto& ode_sys = *process_data.tdisc_ode_sys;\n        auto& solution_backup =\n            NumLib::GlobalVectorProvider::provider.getVector(\n                ode_sys.getMatrixSpecifications(process_id));\n        MathLib::LinAlg::copy(*x[process_id], solution_backup);\n\n        bool first_trial = true;\n        try\n        {\n            while (process.hasPendingPreSolveConstructionSubsteps())\n            {\n                auto const lambda = process.beginConstructionSubstepTrial();\n                if (!lambda)\n                {\n                    OGS_FATAL(\n                        "Process reports pending pre-solve staged construction "\n                        "but did not open a trial.");\n                }\n\n                INFO(\n                    "Staged construction pre-solve trial for process #{:d}: "\n                    "lambda = {:g} at physical time t = {:g}.",\n                    process_id, *lambda, t());\n\n                // The first attempt is the sole owner of physical time\n                // discretization advancement.  Cutback retries reuse that same\n                // t/dt and therefore must use the construction-only solve.\n                nonlinear_solver_status =\n                    first_trial\n                        ? solveOneTimeStepOneProcess(\n                              x, x_prev, timestep_id, t(), dt, process_data,\n                              outputs)\n                        : solveOneConstructionSubstepOneProcess(\n                              x, x_prev, timestep_id, t(), dt, process_data,\n                              outputs);\n\n                if (nonlinear_solver_status.error_norms_met)\n                {\n                    // A4M: do not push the converged MFront/MGIS trial state\n                    // here. This solve is the accepted physical increment and\n                    // the normal postTimestep() call below the TimeLoop owns\n                    // the single constitutive history commit. A second commit\n                    // here would make postTimestep re-integrate the same\n                    // birth increment from an already advanced state.\n                    process.commitConstructionSubstepTrial();\n                    break;\n                }\n\n                MathLib::LinAlg::copy(solution_backup, *x[process_id]);\n                process.rollbackConstructionSubstepState();\n                process.rollbackConstructionSubstepTrial();\n                first_trial = false;\n\n                WARN(\n                    "Pre-solve staged construction trial rejected for process "\n                    "#{:d}; adaptive cutback retries at unchanged physical "\n                    "time.",\n                    process_id);\n            }\n        }\n        catch (...)\n        {\n            NumLib::GlobalVectorProvider::provider.releaseVector(\n                solution_backup);\n            throw;\n        }\n\n        NumLib::GlobalVectorProvider::provider.releaseVector(solution_backup);\n    }\n\n    INFO("[time] Solving process #{:d} took {:g} s in time step #{:d}",\n         process_data.process_id, time_timestep_process.elapsed(), timestep_id);\n\n    return nonlinear_solver_status;\n'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected solveMonolithicProcess layout after R3I")
time_loop.write_text(text.replace(old, new, 1), encoding="utf-8")

print("Applied OGS Staged Construction A4D/A4M pre-solve activation with single physical state commit")
