#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4L — literature-guided stress-free birth with the full physical operator.
#
# Established staged-construction semantics used here:
# - Abaqus full element activation: the configuration at activation is the
#   stress-free reference configuration; full material properties are active.
# - PLAXIS staged construction: reactivated soil starts from zero stress, is
#   stresslessly pre-deformed to the previous deformed mesh, and stiffness and
#   strength are fully active from the first calculation step. The resulting
#   global out-of-balance force is solved by the nonlinear equilibrium process.
#
# A4C/A4F provide u_birth-relative kinematics and fresh MFront/MGIS state.
# A4J creates the deferred publication path. A4L is deliberately applied after
# A4J and removes the experimental A4E/A4I homotopies from the final runtime.

la = root / "ProcessLib/SmallDeformation/LocalAssemblerInterface.h"
text = la.read_text(encoding="utf-8")
old = '''    double activationConstitutiveKinematicScale() const
    {
        return activation_birth_step_ ? activation_contribution_scale_ : 1.0;
    }
'''
new = '''    double activationConstitutiveKinematicScale() const
    {
        // A4L: the captured placement configuration is the stress-free birth
        // reference. Constitutive kinematics are physical from birth onward.
        return 1.0;
    }
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4I constitutive kinematic scale block for A4L")
la.write_text(text.replace(old, new, 1), encoding="utf-8")

fem = root / "ProcessLib/SmallDeformation/SmallDeformationFEM.h"
text = fem.read_text(encoding="utf-8")
# A4G expanded the A4E two-line residual multiplier with diagnostics. Remove
# that complete historical homotopy block rather than depending on the obsolete
# pre-diagnostic two-line form.
old = '''        auto const activation_scale = this->activationContributionScale();
        auto const activation_unscaled_residual_norm = local_b.norm();
        local_b *= activation_scale;
        if (activation_scale < 1.0)
        {
            INFO("A4G activation assembly element {:d}: lambda={:g}, "
                 "unscaled_local_residual_norm={:g}, "
                 "scaled_local_residual_norm={:g}, tangent_norm={:g}",
                 this->element_.getID(), activation_scale,
                 activation_unscaled_residual_norm, local_b.norm(),
                 local_Jac.norm());
        }
'''
new = '''        // A4L: assemble the full physical residual and tangent. Stress-free
        // birth is carried by the placement reference, not by fractional
        // material/operator scaling.
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4G/A4E activation residual block for A4L")
fem.write_text(text.replace(old, new, 1), encoding="utf-8")

sd_cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = sd_cpp.read_text(encoding="utf-8")
constructor = '''    staged_construction_activation_transition_ =
        std::make_unique<StagedConstruction::ActivationTransition>();
'''
constructor_alt = '''    staged_construction_activation_transition_ = std::make_unique<
        StagedConstruction::ActivationTransition>();
'''
count = text.count(constructor) + text.count(constructor_alt)
if count != 1:
    raise RuntimeError("Could not uniquely locate deferred activation transition for A4L")
text = text.replace(
    constructor,
    '''    staged_construction_activation_transition_ =
        std::make_unique<StagedConstruction::ActivationTransition>(1.0);
''', 1)
text = text.replace(
    constructor_alt,
    '''    staged_construction_activation_transition_ = std::make_unique<
        StagedConstruction::ActivationTransition>(1.0);
''', 1)

scale_call = '''    GlobalExecutor::executeSelectedMemberOnDereferenced(
        &LocalAssemblerInterface::setActivationContributionScale,
        local_assemblers_, staged_construction_activation_element_ids_, 0.0);
'''
if text.count(scale_call) != 1:
    raise RuntimeError("Could not uniquely locate deferred activation contribution scale for A4L")
text = text.replace(scale_call, scale_call.replace('0.0);', '1.0);'), 1)

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
    raise RuntimeError("Unexpected A4J activation publication evidence anchor")
text = text.replace(needle, replacement, 1)
sd_cpp.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction A4L full-physics stress-free birth")
