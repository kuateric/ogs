#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
time_loop = root / "ProcessLib/TimeLoop.cpp"
text = time_loop.read_text(encoding="utf-8")

anchor = '''    return nonlinear_solver_status;\n}\n\nTimeLoop::TimeLoop(\n'''
helper = '''    return nonlinear_solver_status;\n}\n\n// Staged-construction nonlinear solve at unchanged physical time.  Unlike\n// solveOneTimeStepOneProcess(), this helper deliberately does not call\n// time_disc.nextTimestep().  The surrounding physical time step therefore\n// remains the sole owner of t/dt advancement while adaptive construction\n// continuation may perform multiple equilibrium solves at the same t and dt.\nNumLib::NonlinearSolverStatus solveOneConstructionSubstepOneProcess(\n    std::vector<GlobalVector*>& x, std::size_t const timestep, double const t,\n    double const delta_t, ProcessData const& process_data,\n    Output& output_control)\n{\n    auto& process = process_data.process;\n    int const process_id = process_data.process_id;\n    auto& conv_crit = *process_data.conv_crit;\n    auto& ode_sys = *process_data.tdisc_ode_sys;\n    auto& nonlinear_solver = process_data.nonlinear_solver;\n    auto const nl_tag = process_data.nonlinear_solver_tag;\n\n    setEquationSystem(nonlinear_solver, ode_sys, conv_crit, nl_tag);\n\n    auto const post_iteration_callback =\n        [&](int iteration, std::vector<GlobalVector*> const& current_x)\n        {\n            output_control.doOutputNonlinearIteration(\n                process, process_id, timestep, t, current_x, iteration);\n        };\n\n    auto const nonlinear_solver_status =\n        nonlinear_solver.solve(x, post_iteration_callback, process_id);\n\n    if (nonlinear_solver_status.error_norms_met)\n    {\n        process.postNonLinearSolver(*x[process_id], t, delta_t, process_id);\n    }\n\n    return nonlinear_solver_status;\n}\n\nTimeLoop::TimeLoop(\n'''

if "solveOneConstructionSubstepOneProcess" not in text:
    if text.count(anchor) != 1:
        raise RuntimeError("Unexpected solveOneTimeStepOneProcess anchor in ProcessLib/TimeLoop.cpp")
    text = text.replace(anchor, helper, 1)
    time_loop.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction R3H constant-physical-time nonlinear solve bridge")
