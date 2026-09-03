#!/usr/bin/env python3
from pathlib import Path

path = Path("ProcessLib/ComponentTransport/ComponentTransportFEM.h")
text = path.read_text()
marker = "// NUMO: positivity-preserving row-sum lumping of the reaction projection"
if marker in text:
    print("NUMO reaction projection patch already present")
    raise SystemExit(0)

old = '''            local_b.noalias() += N.transpose() * ((C_post_int_pt - C_int_pt) /\n                                                  dt * porosity * w);\n        }\n    }\n\n    std::vector<double> const& getIntPtLiquidDensity('''
new = '''            local_b.noalias() += N.transpose() * ((C_post_int_pt - C_int_pt) /\n                                                  dt * porosity * w);\n        }\n\n        // NUMO: positivity-preserving row-sum lumping of the reaction projection.\n        //\n        // With the consistent reaction mass matrix M_C, the assembled source\n        // satisfies, for constant porosity,\n        //\n        //   b = (F_post - M_C * C_old) / dt.\n        //\n        // Replacing only M_C by its row-sum lumped counterpart M_L would leave\n        // this source inconsistent and can itself create negative nodal values.\n        // Therefore compensate the source at the same time, giving\n        //\n        //   b_L = b + (M_C - M_L) * C_old / dt,\n        //\n        // and hence (for K=0) M_L * C_new = F_post. For non-negative\n        // integration-point concentrations and non-negative shape functions,\n        // this diagonal projection is positivity preserving while retaining\n        // the element-integrated mass.\n        auto const consistent_mass_times_C = (local_M * local_C).eval();\n        auto const lumped_reaction_mass = local_M.rowwise().sum().eval();\n        local_M.setZero();\n        local_M.diagonal() = lumped_reaction_mass;\n        local_b.noalias() +=\n            (consistent_mass_times_C - local_M * local_C) / dt;\n    }\n\n    std::vector<double> const& getIntPtLiquidDensity('''

if old not in text:
    raise SystemExit("Expected OGS 6.5.8 reaction assembly block not found; refusing to patch")

path.write_text(text.replace(old, new, 1))
print(f"Patched {path}")
