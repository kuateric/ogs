#!/usr/bin/env python3
from pathlib import Path
import os
import subprocess

# CI-only preparation for TH2M-T2D. This deliberately does not modify the
# production birth algorithm. It converts the proven T1B/T2C fixture to a real
# MFront law and instruments the canonical MFront state allocation/initialization
# boundary. T2D transforms the already-generated T2C runtime, not the T2C source
# generator, to avoid nested quoting/code-generation failure modes.

t1b = Path('scripts/run-ogs-staged-construction-th2m-t1b.sh')
text = t1b.read_text(encoding='utf-8')

build_anchor = "  '-DOGS_BUILD_PROCESSES=TH2M'"
if text.count(build_anchor) != 1:
    raise RuntimeError('T2D TH2M build anchor changed')
text = text.replace(
    build_anchor,
    "  -DOGS_USE_MFRONT=ON \\\n  '-DOGS_BUILD_PROCESSES=TH2M'",
    1,
)

linear = """for child in list(cr):
    cr.remove(child)
ET.SubElement(cr, 'type').text = 'LinearElasticIsotropic'
ET.SubElement(cr, 'youngs_modulus').text = 'E'
ET.SubElement(cr, 'poissons_ratio').text = 'nu'
cr.set('id', '0,1')"""
mfront = """for child in list(cr):
    cr.remove(child)
ET.SubElement(cr, 'type').text = 'MFront'
ET.SubElement(cr, 'behaviour').text = 'MohrCoulombAbboSloan'
props = ET.SubElement(cr, 'material_properties')
for prop_name, parameter_name in (
    ('YoungModulus', 'E'),
    ('PoissonRatio', 'nu'),
    ('Cohesion', 'MC_Cohesion'),
    ('FrictionAngle', 'MC_FrictionAngle'),
    ('DilatancyAngle', 'MC_DilatancyAngle'),
    ('TransitionAngle', 'MC_TransitionAngle'),
    ('TensionCutOffParameter', 'MC_TensionCutOff'),
):
    mp = ET.SubElement(props, 'material_property')
    mp.set('name', prop_name)
    mp.set('parameter', parameter_name)
cr.set('id', '0,1')"""
if text.count(linear) != 1:
    raise RuntimeError('T2D linear constitutive fixture anchor changed')
text = text.replace(linear, mfront, 1)

param_anchor = "tree.write(p, encoding='ISO-8859-1', xml_declaration=True)"
param_insert = """parameters = root.find('parameters')
if parameters is None:
    raise RuntimeError('TH2M parameters block missing')
for name, value in (
    ('MC_Cohesion', '5e6'),
    ('MC_FrictionAngle', '25'),
    ('MC_DilatancyAngle', '10'),
    ('MC_TransitionAngle', '27'),
    ('MC_TensionCutOff', '1e6'),
):
    par = ET.SubElement(parameters, 'parameter')
    ET.SubElement(par, 'name').text = name
    ET.SubElement(par, 'type').text = 'Constant'
    ET.SubElement(par, 'value').text = value

tree.write(p, encoding='ISO-8859-1', xml_declaration=True)"""
if text.count(param_anchor) != 1:
    raise RuntimeError('T2D parameter insertion anchor changed')
text = text.replace(param_anchor, param_insert, 1)
t1b.write_text(text, encoding='utf-8')

# Ask the already-authoritative T2C generator to materialize its final runtime,
# but do not execute it. This is deliberately a supported mode of the same T2C
# gate, so default T2C execution semantics remain unchanged.
env = dict(os.environ)
env['TH2M_T2C_PREPARE_ONLY'] = '1'
subprocess.run(
    ['bash', 'scripts/run-ogs-staged-construction-th2m-t2c.sh'],
    check=True,
    env=env,
)

runtime = Path('/tmp/run-th2m-t2c.sh')
if not runtime.is_file():
    raise RuntimeError('T2D expected generated T2C runtime is missing')
src = runtime.read_text(encoding='utf-8')

# From here onward all anchors are physical lines in the final shell script.
patch_anchor = "python3 /tmp/th2m-t2b-runtime.py\ngit diff --check"
patch_insert = (
    "python3 /tmp/th2m-t2b-runtime.py\n"
    "python3 \"$GITHUB_WORKSPACE/scripts/instrument-ogs-staged-construction-th2m-t2d-mfront.py\"\n"
    "git diff --check"
)
if src.count(patch_anchor) != 1:
    raise RuntimeError('T2D generated-runtime patch anchor changed')
src = src.replace(patch_anchor, patch_insert, 1)

src = src.replace('TH2M-T2C', 'TH2M-T2D')
src = src.replace('th2m-t2c', 'th2m-t2d')
src = src.replace('TH2M_T2C', 'TH2M_T2D')

evidence_anchor = "Path('../th2m-t2d-evidence.txt').write_text("
evidence_insert = """mfront_allocations = log.count('TH2M-T2D MFront/MGIS fresh BehaviourData allocation')
mfront_birth_initializers = len(re.findall(r'TH2M-T2D MFront/MGIS virgin state initializer at t = 2(?:\\.0+)?', log))
if mfront_allocations == 0:
    raise RuntimeError('no real MFront/MGIS BehaviourData allocation observed')
if mfront_birth_initializers == 0:
    raise RuntimeError('no MFront/MGIS virgin initializer observed at reactivation t=2')
if 'MFront: integration failed' in log:
    raise RuntimeError('MFront integration failure detected')
Path('../th2m-t2d-evidence.txt').write_text("""
if src.count(evidence_anchor) != 1:
    raise RuntimeError('T2D generated-runtime evidence anchor changed')
src = src.replace(evidence_anchor, evidence_insert, 1)

field_anchor = """    'birth_stress=zero_unless_explicit_placement_state\\n'
    'physical_stiffness=full_from_first_active_assembly\\n'
"""
field_insert = """    'birth_stress=zero_unless_explicit_placement_state\\n'
    f'mfront_behaviour_data_allocations={mfront_allocations}\\n'
    f'mfront_virgin_initializers_t2={mfront_birth_initializers}\\n'
    'mfront_mgis_stale_history_carried_over=false_by_fresh_object_replacement\\n'
    'physical_stiffness=full_from_first_active_assembly\\n'
"""
if src.count(field_anchor) != 1:
    raise RuntimeError('T2D generated-runtime evidence field anchor changed')
src = src.replace(field_anchor, field_insert, 1)

Path('/tmp/run-th2m-t2d.sh').write_text(src, encoding='utf-8')
