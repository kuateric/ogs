#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4I: diagnostic constitutive birth-deformation homotopy.
# This remains in the historical patch stack as a deterministic precursor.
# A4L is applied as its own post-A4J gate and removes the experimental
# activation scaling from the final runtime.
la = root / "ProcessLib/SmallDeformation/LocalAssemblerInterface.h"
text = la.read_text(encoding="utf-8")
anchor = '''    double activationContributionScale() const
    {
        return activation_contribution_scale_;
    }

'''
if text.count(anchor) != 1:
    raise RuntimeError("Unexpected A4B activation scale getter")
addition = anchor + '''    double activationConstitutiveKinematicScale() const
    {
        return activation_birth_step_ ? activation_contribution_scale_ : 1.0;
    }

'''
la.write_text(text.replace(anchor, addition), encoding="utf-8")

fem = root / "ProcessLib/SmallDeformation/SmallDeformationFEM.h"
text = fem.read_text(encoding="utf-8")
old = '''        Eigen::VectorXd const u_constitutive =
            this->activationRelativeDisplacement(u);
        Eigen::VectorXd const u_prev_constitutive =
            this->activationPreviousRelativeDisplacement(u_prev);
'''
new = '''        double const constitutive_activation_scale =
            this->activationConstitutiveKinematicScale();
        Eigen::VectorXd const u_constitutive =
            constitutive_activation_scale *
            this->activationRelativeDisplacement(u);
        Eigen::VectorXd const u_prev_constitutive =
            constitutive_activation_scale *
            this->activationPreviousRelativeDisplacement(u_prev);
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4F constitutive displacement mapping")
fem.write_text(text.replace(old, new), encoding="utf-8")
print("Applied OGS Staged Construction A4I constitutive birth-deformation homotopy")

# A4K: publish a pending activation before advancing an unsupported cavity
# through the ordinary physical solve. A4J, applied next by the runner, supplies
# the pending-publication API used by the final translation unit.
time_loop = root / "ProcessLib/TimeLoop.cpp"
text = time_loop.read_text(encoding="utf-8")
solve_anchor = '''    NumLib::NonlinearSolverStatus nonlinear_solver_status;

    if (!process_data.process.hasPendingPreSolveConstructionSubsteps())
'''
solve_replacement = '''    if (process_data.process.hasPendingActivationPublication(
            process_data.process_id))
    {
        INFO(
            "Staged construction pre-physical activation publication for "
            "process #{:d} at activation time t = {:g}.",
            process_data.process_id, t());
        process_data.process.publishPendingActivation(
            x, t(), dt, process_data.process_id);
    }

    NumLib::NonlinearSolverStatus nonlinear_solver_status;

    if (!process_data.process.hasPendingPreSolveConstructionSubsteps())
'''
if text.count(solve_anchor) != 1:
    raise RuntimeError("Unexpected A4D solveMonolithicProcess layout for A4K")
time_loop.write_text(text.replace(solve_anchor, solve_replacement, 1), encoding="utf-8")
print("Applied OGS Staged Construction A4K pre-physical activation ordering")
