#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
time_loop = root / "ProcessLib/TimeLoop.cpp"
text = time_loop.read_text(encoding="utf-8")

anchor = '''    return nonlinear_solver_status;\n}\n\nTimeLoop::TimeLoop(\n'''
helper = '''    return nonlinear_solver_status;\n}\n\n// Staged-construction nonlinear solve at unchanged physical time.  Unlike\n// solveOneTimeStepOneProcess(), this helper deliberately does not call\n// time_disc.nextTimestep().  The surrounding physical time step therefore\n// remains the sole owner of t/dt advancement while adaptive construction\n// continuation may perform multiple equilibrium solves at the same t and dt.\nNumLib::NonlinearSolverStatus solveOneConstructionSubstepOneProcess(\n    std::vector<GlobalVector*>& x,\n    std::vector<GlobalVector*> const& x_prev,\n    std::size_t const timestep, double const t, double const delta_t,\n    ProcessData const& process_data, std::vector<Output> const& outputs)\n{\n    auto& process = process_data.process;\n    int const process_id = process_data.process_id;\n    auto& nonlinear_solver = process_data.nonlinear_solver;\n\n    setEquationSystem(process_data);\n\n    auto const post_iteration_callback =\n        [&](int const iteration, bool const converged,\n            std::vector<GlobalVector*> const& current_x)\n        {\n            // Keep nonlinear-iteration output semantics identical to a regular\n            // physical solve, but do not execute physical-time hooks here.\n            for (auto const& output : outputs)\n            {\n                output.doOutputNonlinearIteration(\n                    process, process_id, timestep, NumLib::Time(t), iteration,\n                    converged, current_x);\n            }\n        };\n\n    auto const nonlinear_solver_status = nonlinear_solver.solve(\n        x, x_prev, post_iteration_callback, process_id);\n\n    if (!nonlinear_solver_status.error_norms_met)\n    {\n        return nonlinear_solver_status;\n    }\n\n    process.postNonLinearSolver(x, x_prev, t, delta_t, process_id);\n\n    return nonlinear_solver_status;\n}\n\nTimeLoop::TimeLoop(\n'''

if "solveOneConstructionSubstepOneProcess" not in text:
    if text.count(anchor) != 1:
        raise RuntimeError("Unexpected solveOneTimeStepOneProcess anchor in ProcessLib/TimeLoop.cpp")
    text = text.replace(anchor, helper, 1)
    time_loop.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction R3H constant-physical-time nonlinear solve bridge")
