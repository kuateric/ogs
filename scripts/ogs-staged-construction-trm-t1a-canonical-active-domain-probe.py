#!/usr/bin/env python3
"""TRM-T1A: inspect the pinned canonical TRM active-domain architecture.

The companion workflow extracts source files from the canonical OGS SHA with
`git show` before invoking this script.  This keeps the probe independent of
all staged-construction patches inherited by the development branch.
"""
from pathlib import Path
import sys


def require(text: str, token: str, where: str) -> None:
    if token not in text:
        raise RuntimeError(f"missing canonical TRM anchor {token!r} in {where}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: probe.py <ThermoRichardsMechanicsProcess.cpp> <CreateThermoRichardsMechanicsProcess.cpp>")

    process_path = Path(sys.argv[1])
    create_path = Path(sys.argv[2])
    process = process_path.read_text()
    create = create_path.read_text()

    # Canonical monolithic field ordering.
    for token in (
        'findProcessVariables(process_variables, "temperature")',
        'findProcessVariables(process_variables, "pressure")',
        'findProcessVariables(process_variables, "displacement")',
    ):
        require(create, token, str(create_path))

    # One process-wide active set controls assembly lifecycle and constitutive
    # commit/output.  Thus synchronized T/p/u domain selection is the key T1
    # invariant; individual thermal/hydraulic/mechanical operators must not
    # maintain independent hidden activity states.
    require(process, 'updateActiveElements()', str(process_path))
    require(process, 'getActiveElementIDs()', str(process_path))
    require(process, '&LocalAssemblerIF::postTimestep', str(process_path))
    require(process, '&LocalAssemblerIF::computeSecondaryVariable', str(process_path))

    # MFront TRM is an explicit canonical instantiation; T1+ cannot silently
    # solve the lifecycle only for native elastic constitutive relations.
    require(process, '#if OGS_USE_MFRONT', str(process_path))
    require(process, 'ConstitutiveStressSaturation_StrainPressureTemperature', str(process_path))

    print('TRM-T1A canonical active-domain architecture PASS')
    print('finding: one monolithic active-element set governs T/p/u TRM lifecycle')
    print('requirement: staged-construction void/birth must synchronize temperature, pressure and displacement domain transitions')


if __name__ == '__main__':
    main()
