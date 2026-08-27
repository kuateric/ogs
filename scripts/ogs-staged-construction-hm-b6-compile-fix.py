#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
fem = root / "ProcessLib/HydroMechanics/HydroMechanicsFEM.h"
text = fem.read_text(encoding="utf-8")

# The existing selector is declared in HydroMechanicsFEM-impl.h in canonical
# OGS. HM-B6 calls it from an inline birth hook added to HydroMechanicsFEM.h,
# so make the declaration visible at that earlier point.
include_anchor = '#include "MaterialLib/SolidModels/LinearElasticIsotropic.h"\n'
include_replacement = (
    include_anchor
    + '#include "MaterialLib/SolidModels/SelectSolidConstitutiveRelation.h"\n'
)
if text.count(include_anchor) != 1:
    raise RuntimeError("unexpected HM-B6 selector include anchor")
if 'MaterialLib/SolidModels/SelectSolidConstitutiveRelation.h' not in text:
    text = text.replace(include_anchor, include_replacement, 1)

# HM-B6 deliberately makes the integration-point material binding reassignable.
# initializeConcrete() is outside IntegrationPointData and therefore was not
# covered by the first pointer-conversion pass.
old = '''            ip_data.solid_material.initializeInternalStateVariables(\n                t, x_position, *ip_data.material_state_variables);\n'''
new = '''            ip_data.solid_material->initializeInternalStateVariables(\n                t, x_position, *ip_data.material_state_variables);\n'''
if text.count(old) != 1:
    raise RuntimeError("unexpected HM-B6 initializeConcrete material anchor")
text = text.replace(old, new, 1)

fem.write_text(text, encoding="utf-8")
print("Applied HM-B6 constitutive rebind compile fix")
