#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
time_loop = root / "ProcessLib/TimeLoop.cpp"
text = time_loop.read_text(encoding="utf-8")

# R3I is the first runtime activation of the adaptive construction continuation.
# It is deliberately restricted to the uncoupled process path.  Physical time
# is advanced exactly once by solveOneTimeStepOneProcess(); all subsequent
# lambda solves reuse the already advanced time-discretized ODE system and do
# not call nextTimestep() again.

insert_anchor = '''    return nonlinear_solver_status;\n}\n\nTimeLoop::TimeLoop(\n'''
helper = r'''    return nonlinear_solver_status;
}

void runPendingConstructionSubstepsOneProcess(
    std::vector<GlobalVector*>& x,
    std::vector<GlobalVector*> const& x_prev,
    std::size_t const timestep, double const t, double const delta_t,
    ProcessLib::ProcessData& process_data,
    std::vector<ProcessLib::Output> const& outputs)
{
    auto& process = process_data.process;
    int const process_id = process_data.process_id;

    if (!process.hasPendingConstructionSubsteps())
    {
        return;
    }

    // The converged physical solve at lambda=0 is the constitutive baseline
    // for continuation.  Commit that already evaluated state without advancing
    // physical time; subsequent accepted construction trials build on it.
    process.commitConstructionSubstepState();

    auto& ode_sys = *process_data.tdisc_ode_sys;
    auto& solution_backup = NumLib::GlobalVectorProvider::provider.getVector(
        ode_sys.getMatrixSpecifications(process_id));

    std::size_t accepted_trials = 0;
    std::size_t rejected_trials = 0;

    try
    {
        while (process.hasPendingConstructionSubsteps())
        {
            MathLib::LinAlg::copy(*x[process_id], solution_backup);

            auto const lambda = process.beginConstructionSubstepTrial();
            if (!lambda)
            {
                OGS_FATAL(
                    "Process reports pending staged construction but did not "
                    "open a construction trial.");
            }

            INFO(
                "Staged construction trial for process #{:d}: lambda = {:g} "
                "at unchanged physical time t = {:g}.",
                process_id, *lambda, t);

            auto const status = solveOneConstructionSubstepOneProcess(
                x, x_prev, timestep, t, delta_t, process_data, outputs);
            process_data.nonlinear_solver_status = status;

            if (status.error_norms_met)
            {
                // Commit constitutive/process state first, then publish the
                // corresponding construction coordinate atomically.
                process.commitConstructionSubstepState();
                process.commitConstructionSubstepTrial();
                ++accepted_trials;
                continue;
            }

            // Restore the primary solution before rejecting/cutting back the
            // construction coordinate.  Constitutive trial state was never
            // pushed back, so rollback leaves the last committed MFront/MGIS
            // s0 and StatefulDataPrev baseline intact.
            MathLib::LinAlg::copy(solution_backup, *x[process_id]);
            process.rollbackConstructionSubstepState();
            process.rollbackConstructionSubstepTrial();
            ++rejected_trials;

            WARN(
                "Staged construction trial rejected for process #{:d}; "
                "adaptive cutback will retry at unchanged physical time.",
                process_id);
        }
    }
    catch (...)
    {
        NumLib::GlobalVectorProvider::provider.releaseVector(solution_backup);
        throw;
    }

    NumLib::GlobalVectorProvider::provider.releaseVector(solution_backup);

    INFO(
        "Staged construction transition completed for process #{:d}: {:d} "
        "accepted trial(s), {:d} rejected trial(s), physical time unchanged "
        "at t = {:g}.",
        process_id, accepted_trials, rejected_trials, t);
}

TimeLoop::TimeLoop(
'''
if text.count(insert_anchor) != 1:
    raise RuntimeError("Unexpected TimeLoop R3H helper anchor")
text = text.replace(insert_anchor, helper, 1)

runtime_anchor = '''    if (nonlinear_solver_status.error_norms_met)\n    {\n        // Later on, the timestep_algorithm might reject the timestep. We assume\n        // that this is a rare case, so still, we call preOutput() here. We\n'''
runtime_replacement = '''    if (nonlinear_solver_status.error_norms_met)\n    {\n        // A deactivation event first converges at lambda=0 with the retained\n        // pre-removal force.  Complete the adaptive force release at the same\n        // physical t/dt before output and the ordinary physical postTimestep().\n        // Staggered multiphysics continuation is intentionally deferred to a\n        // later gate; R3I activates only the uncoupled process path.\n        bool const has_pending_construction = std::ranges::any_of(\n            _per_process_data, [](auto const& process_data)\n            { return process_data->process.hasPendingConstructionSubsteps(); });\n\n        if (has_pending_construction && _staggered_coupling)\n        {\n            OGS_FATAL(\n                "Adaptive staged-construction continuation is not yet enabled "\n                "for staggered coupled processes.");\n        }\n\n        if (has_pending_construction)\n        {\n            for (auto& process_data : _per_process_data)\n            {\n                runPendingConstructionSubstepsOneProcess(\n                    _process_solutions, _process_solutions_prev, timesteps,\n                    t(), dt, *process_data, _outputs);\n            }\n        }\n\n        // Later on, the timestep_algorithm might reject the timestep. We assume\n        // that this is a rare case, so still, we call preOutput() here. We\n'''
if text.count(runtime_anchor) != 1:
    raise RuntimeError("Unexpected preTsNonlinearSolvePostTs success anchor")
text = text.replace(runtime_anchor, runtime_replacement, 1)

time_loop.write_text(text, encoding="utf-8")
print("Applied OGS Staged Construction R3I adaptive runtime continuation wiring")
