#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4I: A4G/A4H prove that the newborn elements start with zero residual and
# finite tangent and that the completed excavation retained force is exactly
# zero at later activation.  The remaining global Newton correction is almost
# independent of activation lambda.  Scaling only the assembled residual (A4E)
# therefore cannot protect MFront: the constitutive integration has already
# seen the full placement-relative displacement before assembly scaling is
# applied.
#
# During the birth physical step, use the activation continuation coordinate as
# a constitutive kinematic homotopy as well:
#
#   u_constitutive(lambda) = lambda * (u - u_placement)
#
# with the birth predecessor treated consistently through the same scale.  The
# regularizing full tangent introduced by A4E remains intentionally active so
# newborn DOFs retain finite kinematic support.  At lambda=1 the constitutive
# kinematics and assembled equations are exactly the physical system again.

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
        // Once the birth physical step has completed the material owns normal
        // placement-relative kinematics and no construction scaling applies.
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

# A4K ordering correction. A4J demonstrated that an inactive physical baseline
# at t_{n+1} can itself fail before a strong-contrast backfill is published.
# Once updateDeactivatedSubdomains() has recorded a pending activation, publish
# it before the ordinary physical nonlinear solve and reuse A4D's existing
# pre-solve adaptive activation continuation. A4J adds the pending-publication
# API later in the patch sequence; the final translation unit sees that API.
time_loop = root / "ProcessLib/TimeLoop.cpp"
text = time_loop.read_text(encoding="utf-8")
solve_anchor = '''    NumLib::NonlinearSolverStatus nonlinear_solver_status;

    if (!process_data.process.hasPendingPreSolveConstructionSubsteps())
'''
solve_replacement = '''    // A4K: birth must precede physical advancement of an unsupported cavity.
    // Publish from the last converged placement configuration, then A4D opens
    // the first activation trial before the ordinary physical solve.
    if (process_data.process.hasPendingActivationPublication(
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
time_loop.write_text(text.replace(solve_anchor, solve_replacement, 1),
                     encoding="utf-8")

print("Applied OGS Staged Construction A4K pre-physical activation ordering")

# A4J is intentionally NOT chained here. The authoritative runner applies A4J
# as its own explicit stage immediately after A4I. Chaining it here would apply
# the same patch twice and make the second invocation fail its idempotency guard.
