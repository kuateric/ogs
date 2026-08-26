#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# A4E: A4B scaled both the activation residual and tangent by the same lambda.
# Algebraically that cannot reduce the Newton correction because
#   (lambda J) dx = -(lambda r)
# has the same dx as J dx = -r.  For newly placed material this also makes the
# active DOF block arbitrarily soft as lambda -> 0.
#
# Use a placement-regularized homotopy instead: ramp the activation residual
# while keeping the material tangent fully active.  This gives the newborn
# domain finite kinematic support at every trial and makes cutback reduce the
# driving imbalance.  At lambda=1 the equations are exactly the physical
# SmallDeformation equations again.

fem = root / "ProcessLib/SmallDeformation/SmallDeformationFEM.h"
text = fem.read_text(encoding="utf-8")
old = '''        // Newly placed material is introduced through a construction\n        // coordinate at fixed physical time. Residual and consistent tangent\n        // must use the same scale to retain Newton consistency.\n        auto const activation_scale = this->activationContributionScale();\n        local_b *= activation_scale;\n        local_Jac *= activation_scale;\n'''
new = '''        // Placement-regularized activation homotopy.  Scaling residual and\n        // tangent by the same lambda would cancel lambda from the Newton\n        // correction and would make newborn DOFs arbitrarily soft.  Keep the\n        // full material tangent as kinematic support while ramping only the\n        // activation driving residual.  At lambda=1 this is exactly the\n        // physical SmallDeformation system.\n        auto const activation_scale = this->activationContributionScale();\n        local_b *= activation_scale;\n'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected A4B activation scaling block")
fem.write_text(text.replace(old, new), encoding="utf-8")

print("Applied OGS Staged Construction A4E placement-regularized activation homotopy")
