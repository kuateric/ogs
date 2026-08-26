#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4L — literature-guided stress-free birth.
#
# Abaqus progressive/full activation treats the configuration at activation as
# stress free and subsequently measures strain from that configuration.  For a
# fully activated element the physical material is present at full stiffness;
# scaling the newborn constitutive kinematics or residual toward zero is not the
# reference semantics.  FLAC3D likewise treats null zones as absent and allows a
# physical constitutive model to be assigned when the zone is filled again.
#
# A4C/A4F already provide the required OGS mechanics:
#   * capture u_birth from the converged placement configuration,
#   * evaluate strains from u-u_birth,
#   * start MFront from a fresh state with zero birth history.
#
# A4L therefore removes the experimental A4E/A4I birth-operator homotopies and
# activates the full physical residual/tangent/constitutive kinematics in one
# construction trial at unchanged physical time.  Nonlinear equilibrium remains
# solved by the normal OGS Newton solver; construction does not advance time.

fem = root / "ProcessLib/SmallDeformation/SmallDeformationFEM.h"
text = fem.read_text(encoding="utf-8")
old = '''        // Placement-regularized activation homotopy.  Scaling residual and\n        // tangent by the same lambda would cancel lambda from the Newton\n        // correction and would make newborn DOFs arbitrarily soft.  Keep the\n        // full material tangent as kinematic support while ramping only the\n        // activation driving residual.  At lambda=1 this is exactly the\n        // physical SmallDeformation system.\n        auto const activation_scale = this->activationContributionScale();\n        local_b *= activation_scale;\n'''
new = '''        // A4L stress-free birth: the newborn element already measures strain\n        // from its captured placement configuration, so assemble its full\n        // physical residual and consistent tangent.  Do not scale the material\n        // operator by a fictitious activation fraction.\n'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4E activation residual-homotopy block")
text = text.replace(old, new, 1)
fem.write_text(text, encoding="utf-8")

la = root / "ProcessLib/SmallDeformation/LocalAssemblerInterface.h"
text = la.read_text(encoding="utf-8")
old = '''    double activationConstitutiveKinematicScale() const\n    {\n        // Once the birth physical step has completed the material owns normal\n        // placement-relative kinematics and no construction scaling applies.\n        return activation_birth_step_ ? activation_contribution_scale_ : 1.0;\n    }\n'''
new = '''    double activationConstitutiveKinematicScale() const\n    {\n        // A4L: full activation uses the physical placement-relative kinematics\n        // immediately. The captured placement configuration, not an artificial\n        // lambda multiplier, defines the stress-free birth state.\n        return 1.0;\n    }\n'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4I constitutive kinematic scale block")
text = text.replace(old, new, 1)
la.write_text(text, encoding="utf-8")

sd_cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = sd_cpp.read_text(encoding="utf-8")
old = '''        staged_construction_activation_transition_ = std::make_unique<\n            StagedConstruction::ActivationTransition>();\n\n        // Placement begins contribution-free. The existing TimeLoop\n        // construction driver advances this scale at unchanged physical time.\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &LocalAssemblerInterface::setActivationContributionScale,\n            local_assemblers_, staged_construction_activation_element_ids_, 0.0);\n'''
new = '''        // A4L full stress-free birth.  The placement reference and fresh\n        // constitutive state make the newly born material stress free; use a\n        // single full-physics activation trial instead of a fractional material\n        // operator.  The TimeLoop still executes this construction trial at the\n        // same physical t/dt.\n        staged_construction_activation_transition_ = std::make_unique<\n            StagedConstruction::ActivationTransition>(1.0);\n        GlobalExecutor::executeSelectedMemberOnDereferenced(\n            &LocalAssemblerInterface::setActivationContributionScale,\n            local_assemblers_, staged_construction_activation_element_ids_, 1.0);\n        INFO(\n            "A4L stress-free birth: full physical operator published for {:d} "\n            "newly activated elements.",\n            staged_construction_activation_element_ids_.size());\n'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4B activation-transition initialization block")
text = text.replace(old, new, 1)
sd_cpp.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction A4L stress-free birth full physical operator")
