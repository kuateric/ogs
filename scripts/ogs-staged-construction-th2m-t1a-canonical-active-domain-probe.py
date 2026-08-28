#!/usr/bin/env python3
"""TH2M-T1A: inspect the pinned canonical TH2M active-domain architecture.

The companion workflow downloads source files from the canonical upstream OGS
SHA before invoking this script. This keeps the probe independent of all
staged-construction patches inherited by the development branch.
"""
from pathlib import Path
import sys


def require(text: str, token: str, where: str) -> None:
    if token not in text:
        raise RuntimeError(f"missing canonical TH2M anchor {token!r} in {where}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: probe.py <TH2MProcess.cpp> <CreateTH2MProcess.cpp>"
        )

    process_path = Path(sys.argv[1])
    create_path = Path(sys.argv[2])
    process = process_path.read_text()
    create = create_path.read_text()

    # Canonical TH2M is monolithic in the pinned OGS baseline and orders the
    # primary fields p_g, p_c, T, u in one global process-variable vector.
    require(create, 'OGS_FATAL("A Staggered version of TH2M is not implemented.")', str(create_path))
    require(create, "findProcessVariables(", str(create_path))
    pg = create.find('"gas_pressure"')
    pc = create.find('"capillary_pressure"', pg + 1)
    temp = create.find('"temperature"', pc + 1)
    disp = create.find('"displacement"', temp + 1)
    if min(pg, pc, temp, disp) < 0 or not (pg < pc < temp < disp):
        raise RuntimeError(
            "canonical TH2M primary-variable ordering p_g/p_c/T/u not found in "
            f"{create_path}"
        )

    # One process-wide active-element set governs assembly lifecycle, state
    # commit and secondary-variable evaluation. Therefore staged construction
    # must not let gas, liquid/capillary, thermal and mechanical fields develop
    # independent element activity states.
    require(process, "updateActiveElements()", str(process_path))
    require(process, "getActiveElementIDs()", str(process_path))
    require(process, "&LocalAssemblerInterface<DisplacementDim>::postTimestep", str(process_path))
    require(process, "&LocalAssemblerInterface<DisplacementDim>::computeSecondaryVariable", str(process_path))

    # The canonical monolithic Jacobian identifies the three non-deformation
    # components explicitly; displacement follows in the same global system.
    require(process, "{0, 1, 2} /* P_g, P_c, T */", str(process_path))
    require(process, "AssemblyMixin<TH2MProcess<DisplacementDim>>::assembleWithJacobian", str(process_path))

    print("TH2M-T1A canonical active-domain architecture PASS")
    print("finding: one monolithic active-element set governs p_g/p_c/T/u lifecycle")
    print(
        "requirement: staged-construction void/birth must synchronize gas pressure, "
        "capillary pressure, temperature and displacement domain transitions"
    )


if __name__ == "__main__":
    main()
