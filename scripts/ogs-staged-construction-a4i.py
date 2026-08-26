#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4I: diagnostic constitutive birth-deformation homotopy. A4L below removes
# this experimental scaling after using it as a stable patch landmark.
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

# A4L — literature-guided full-physics stress-free birth.
# Abaqus and PLAXIS semantics: the placement/deformed configuration is the new
# stress-free reference; stiffness/strength are fully active from birth. The
# global out-of-balance force is handled by the nonlinear equilibrium solve,
# not by scaling the material operator toward zero.
la = root / "ProcessLib/SmallDeformation/LocalAssemblerInterface.h"
text = la.read_text(encoding="utf-8")
old = '''    double activationConstitutiveKinematicScale() const
    {
        return activation_birth_step_ ? activation_contribution_scale_ : 1.0;
    }
'''
new = '''    double activationConstitutiveKinematicScale() const
    {
        // A4L: placement-relative constitutive kinematics are physical from birth.
        return 1.0;
    }
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4I kinematic scale for A4L")
la.write_text(text.replace(old, new, 1), encoding="utf-8")

fem = root / "ProcessLib/SmallDeformation/SmallDeformationFEM.h"
text = fem.read_text(encoding="utf-8")
old = '''        auto const activation_scale = this->activationContributionScale();
        local_b *= activation_scale;
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4E residual multiplier for A4L")
text = text.replace(old, '''        // A4L: full physical residual; stress-free birth is carried by the
        // captured placement reference, not a fractional material operator.
''', 1)
fem.write_text(text, encoding="utf-8")

# A4J is applied after this script and creates the actual deferred publication
# implementation. Rewrite that generator now so the generated A4J path itself
# publishes the full physical operator, rather than patching an obsolete pre-A4J
# activation branch.
a4j = root / "ogs-staged-construction-a4j.py"
text = a4j.read_text(encoding="utf-8")
old_ctor = '''    staged_construction_activation_transition_ =
        std::make_unique<StagedConstruction::ActivationTransition>();
'''
new_ctor = '''    staged_construction_activation_transition_ =
        std::make_unique<StagedConstruction::ActivationTransition>(1.0);
'''
if text.count(old_ctor) != 1:
    raise RuntimeError("Unexpected A4J deferred activation constructor for A4L")
text = text.replace(old_ctor, new_ctor, 1)
old_scale = '''    GlobalExecutor::executeSelectedMemberOnDereferenced(
        &LocalAssemblerInterface::setActivationContributionScale,
        local_assemblers_, staged_construction_activation_element_ids_, 0.0);
'''
new_scale = old_scale.replace('0.0);', '1.0);')
if text.count(old_scale) != 1:
    raise RuntimeError("Unexpected A4J deferred activation scale for A4L")
text = text.replace(old_scale, new_scale, 1)
needle = '''    AssemblyMixin<SmallDeformationProcess<DisplacementDim>>::updateActiveElements();

    INFO(
        "Staged construction activation published for process #{:d}: {:d} "
'''
replacement = '''    AssemblyMixin<SmallDeformationProcess<DisplacementDim>>::updateActiveElements();

    INFO(
        "A4L stress-free birth: full physical operator published for {:d} "
        "newly activated element(s) at physical time t = {:g}.",
        staged_construction_activation_element_ids_.size(), t);

    INFO(
        "Staged construction activation published for process #{:d}: {:d} "
'''
if text.count(needle) != 1:
    raise RuntimeError("Unexpected A4J runtime evidence anchor for A4L")
text = text.replace(needle, replacement, 1)
a4j.write_text(text, encoding="utf-8")
print("Applied OGS Staged Construction A4L full-physics semantics to deferred A4J birth path")
