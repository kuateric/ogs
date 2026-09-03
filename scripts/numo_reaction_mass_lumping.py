#!/usr/bin/env python3
from pathlib import Path

path = Path("ProcessLib/ComponentTransport/ComponentTransportFEM.h")
text = path.read_text()
marker = "// NUMO: row-sum lump the reaction mass matrix"
if marker in text:
    print("NUMO reaction mass-lumping patch already present")
    raise SystemExit(0)

old = '''            local_b.noalias() += N.transpose() * ((C_post_int_pt - C_int_pt) /\n                                                  dt * porosity * w);\n        }\n    }\n\n    std::vector<double> const& getIntPtLiquidDensity('''
new = '''            local_b.noalias() += N.transpose() * ((C_post_int_pt - C_int_pt) /\n                                                  dt * porosity * w);\n        }\n\n        // NUMO: row-sum lump the reaction mass matrix.  The chemical\n        // reaction increment is computed at integration points and projected\n        // back to nodal transport unknowns.  A consistent reaction mass\n        // matrix can introduce sign-changing nodal corrections for steep\n        // chemical gradients.  Row-sum lumping preserves the element mass\n        // while removing the off-diagonal coupling responsible for that\n        // projection oscillation.\n        auto const lumped_reaction_mass = local_M.rowwise().sum().eval();\n        local_M.setZero();\n        local_M.diagonal() = lumped_reaction_mass;\n    }\n\n    std::vector<double> const& getIntPtLiquidDensity('''

if old not in text:
    raise SystemExit("Expected OGS 6.5.8 reaction assembly block not found; refusing to patch")

path.write_text(text.replace(old, new, 1))
print(f"Patched {path}")
