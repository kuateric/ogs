from pathlib import Path

root = Path.cwd()
create = (root / 'ProcessLib/RichardsMechanics/CreateRichardsMechanicsProcess.cpp').read_text()
proc = (root / 'ProcessLib/RichardsMechanics/RichardsMechanicsProcess.cpp').read_text()

required_create = [
    '"pressure"',
    '"displacement"',
    'createConstitutiveRelations<DisplacementDim>',
    'materialIDs(mesh)',
]
for token in required_create:
    if token not in create:
        raise RuntimeError(f'RM-R0 missing canonical token in create process: {token}')

required_process = [
    'getActiveElementIDs()',
    '&LocalAssemblerIF::setInitialConditions',
    '&LocalAssemblerIF::preTimestep',
    '&LocalAssemblerIF::postTimestep',
    '&LocalAssemblerIF::computeSecondaryVariable',
]
for token in required_process:
    if token not in proc:
        raise RuntimeError(f'RM-R0 missing canonical lifecycle token: {token}')

if create.find('"pressure"') > create.find('"displacement"'):
    raise RuntimeError('RM-R0 canonical monolithic variable order is not pressure -> displacement')

print('RM-R0 PASS candidate: canonical RichardsMechanics is pressure/displacement coupled, material-ID aware, and uses the process active-element set for lifecycle-sensitive execution.')
