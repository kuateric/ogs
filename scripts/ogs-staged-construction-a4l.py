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
# A4C/A4F already provide u_birth-relative kinematics and fresh MFront/MGIS
# state. A4J creates the deferred publication path. This patch therefore removes
# the experimental A4E/A4I material/operator homotopies and makes every newborn
# activation publication use the full physical residual, tangent and kinematics.

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
old = '''        auto const activation_scale = this->activationContributionScale();
        local_b *= activation_scale;
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4E activation residual multiplier for A4L")
text = text.replace(
    old,
    '''        // A4L: assemble the full physical residual. Stress-free birth is
        // carried by the placement reference, not by fractional residual scaling.
''',
    1)
fem.write_text(text, encoding="utf-8")

sd_cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = sd_cpp.read_text(encoding="utf-8")
constructor = '''        staged_construction_activation_transition_ =
        std::make_unique<StagedConstruction::ActivationTransition>();
'''
constructor_alt = '''        staged_construction_activation_transition_ = std::make_unique<
            StagedConstruction::ActivationTransition>();
'''
count = text.count(constructor) + text.count(constructor_alt)
if count < 1:
    raise RuntimeError("Could not locate activation transition publication for A4L")
text = text.replace(
    constructor,
    '''        staged_construction_activation_transition_ =
        std::make_unique<StagedConstruction::ActivationTransition>(1.0);
''')
text = text.replace(
    constructor_alt,
    '''        staged_construction_activation_transition_ = std::make_unique<
            StagedConstruction::ActivationTransition>(1.0);
''')

scale_call = '''    GlobalExecutor::executeSelectedMemberOnDereferenced(
        &LocalAssemblerInterface::setActivationContributionScale,
        local_assemblers_, staged_construction_activation_element_ids_, 0.0);
'''
scale_call_indented = '''        GlobalExecutor::executeSelectedMemberOnDereferenced(
            &LocalAssemblerInterface::setActivationContributionScale,
            local_assemblers_, staged_construction_activation_element_ids_, 0.0);
'''
scale_count = text.count(scale_call) + text.count(scale_call_indented)
if scale_count < 1:
    raise RuntimeError("Could not locate activation contribution publication for A4L")
text = text.replace(scale_call, scale_call.replace('0.0);', '1.0);'))
text = text.replace(scale_call_indented,
                    scale_call_indented.replace('0.0);', '1.0);'))

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
