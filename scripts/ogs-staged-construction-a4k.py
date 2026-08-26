#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4K: publish a deferred placement event before the ordinary physical solve,
# then reuse A4D's pre-solve activation continuation. A4J proved that advancing
# the unsupported cavity to t_{n+1} before birth is itself numerically/physically
# wrong for the strong-contrast case: the inactive baseline can collapse before
# the backfill is ever published. Construction therefore happens at the start of
# the activation time step from the last converged configuration; only the first
# activation trial advances the physical time discretization, and cutback retries
# remain at the same t/dt.

time_loop = root / "ProcessLib/TimeLoop.cpp"
text = time_loop.read_text(encoding="utf-8")

anchor = '''    NumLib::NonlinearSolverStatus nonlinear_solver_status;\n\n    if (!process_data.process.hasPendingPreSolveConstructionSubsteps())\n'''
replacement = '''    // A4K: a pending newborn domain must be published before the physical\n    // t_{n+1} solve.  Solving that step with an intentionally unsupported void\n    // (A4J inactive-baseline ordering) can create a large deformation before\n    // the backfill exists.  Publish at the last converged placement\n    // configuration, then let A4D open the first adaptive activation trial.\n    if (process_data.process.hasPendingActivationPublication(\n            process_data.process_id))\n    {\n        INFO(\n            "Staged construction pre-physical activation publication for "\n            "process #{:d} at activation time t = {:g}.",\n            process_data.process_id, t());\n        process_data.process.publishPendingActivation(\n            x, t(), dt, process_data.process_id);\n    }\n\n    NumLib::NonlinearSolverStatus nonlinear_solver_status;\n\n    if (!process_data.process.hasPendingPreSolveConstructionSubsteps())\n'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected A4D solveMonolithicProcess anchor for A4K")
text = text.replace(anchor, replacement, 1)

time_loop.write_text(text, encoding="utf-8")
print("Applied OGS Staged Construction A4K pre-physical activation publication")
