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

# A4L — literature-guided full stress-free birth.
# Abaqus full progressive activation defines the configuration at activation as
# the stress-free reference configuration. The material then enters with its
# full physical operator; the reference configuration, rather than a fractional
# stiffness/residual/strain multiplier, prevents spurious birth stress. A4C and
# A4F already provide the corresponding OGS semantics (u_birth reference and
# fresh MFront history). Remove the experimental A4E/A4I operator homotopies and
# use one full-physics construction trial at unchanged physical time.
la = root / "ProcessLib/SmallDeformation/LocalAssemblerInterface.h"
text = la.read_text(encoding="utf-8")
old = '''    double activationConstitutiveKinematicScale() const
    {
        // Once the birth physical step has completed the material owns normal
        // placement-relative kinematics and no construction scaling applies.
        return activation_birth_step_ ? activation_contribution_scale_ : 1.0;
    }
'''
new = '''    double activationConstitutiveKinematicScale() const
    {
        // A4L: full activation uses physical placement-relative kinematics from
        // birth. The captured placement configuration defines zero strain.
        return 1.0;
    }
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4I constitutive kinematic scale block for A4L")
la.write_text(text.replace(old, new, 1), encoding="utf-8")

fem = root / "ProcessLib/SmallDeformation/SmallDeformationFEM.h"
text = fem.read_text(encoding="utf-8")
old = '''        // Placement-regularized activation homotopy.  Scaling residual and
        // tangent by the same lambda would cancel lambda from the Newton
        // correction and would make newborn DOFs arbitrarily soft.  Keep the
        // full material tangent as kinematic support while ramping only the
        // activation driving residual.  At lambda=1 this is exactly the
        // physical SmallDeformation system.
        auto const activation_scale = this->activationContributionScale();
        local_b *= activation_scale;
'''
new = '''        // A4L stress-free birth: assemble the full physical residual and
        // consistent tangent. The newborn material is stress free because its
        // strain is measured from the captured placement configuration.
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4E activation residual homotopy for A4L")
fem.write_text(text.replace(old, new, 1), encoding="utf-8")

sd_cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = sd_cpp.read_text(encoding="utf-8")
old = '''        staged_construction_activation_transition_ = std::make_unique<
            StagedConstruction::ActivationTransition>();

        // Placement begins contribution-free. The existing TimeLoop
        // construction driver advances this scale at unchanged physical time.
        GlobalExecutor::executeSelectedMemberOnDereferenced(
            &LocalAssemblerInterface::setActivationContributionScale,
            local_assemblers_, staged_construction_activation_element_ids_, 0.0);
'''
new = '''        // A4L: full stress-free birth in one construction trial. The fresh
        // constitutive state and placement reference carry the birth semantics;
        // no fictitious fractional material operator is used.
        staged_construction_activation_transition_ = std::make_unique<
            StagedConstruction::ActivationTransition>(1.0);
        GlobalExecutor::executeSelectedMemberOnDereferenced(
            &LocalAssemblerInterface::setActivationContributionScale,
            local_assemblers_, staged_construction_activation_element_ids_, 1.0);
        INFO(
            "A4L stress-free birth: full physical operator published for {:d} "
            "newly activated elements.",
            staged_construction_activation_element_ids_.size());
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4B activation initialization for A4L")
sd_cpp.write_text(text.replace(old, new, 1), encoding="utf-8")

print("Applied OGS Staged Construction A4L stress-free birth full physical operator")

# A4J is intentionally NOT chained here. The authoritative runner applies A4J
# as its own explicit stage immediately after A4I. Chaining it here would apply
# the same patch twice and make the second invocation fail its idempotency guard.
