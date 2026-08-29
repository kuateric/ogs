#!/usr/bin/env bash
set -euo pipefail

# TH2M-T2D extends the authoritative T2C fresh-birth runtime with a real
# MFront/MGIS constitutive law. MFront-specific probes are CI-only evidence;
# the production fresh-birth implementation remains material-law neutral.

base="scripts/run-ogs-staged-construction-th2m-t1b.sh"
t2c="scripts/run-ogs-staged-construction-th2m-t2c.sh"
test -f "$base"
test -f "$t2c"

# Convert the already-normalized T1B/T2C fixture from linear elasticity to a
# real MFront behaviour and enable MFront in the pinned canonical build.
python3 - <<'PY'
from pathlib import Path
p = Path('scripts/run-ogs-staged-construction-th2m-t1b.sh')
text = p.read_text(encoding='utf-8')

build_anchor = "  '-DOGS_BUILD_PROCESSES=TH2M'"
if text.count(build_anchor) != 1:
    raise RuntimeError('T2D TH2M build anchor changed')
text = text.replace(build_anchor,
                    "  -DOGS_USE_MFRONT=ON \\\n  '-DOGS_BUILD_PROCESSES=TH2M'", 1)

linear = '''for child in list(cr):
    cr.remove(child)
ET.SubElement(cr, 'type').text = 'LinearElasticIsotropic'
ET.SubElement(cr, 'youngs_modulus').text = 'E'
ET.SubElement(cr, 'poissons_ratio').text = 'nu'
cr.set('id', '0,1')'''
mfront = '''for child in list(cr):
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
cr.set('id', '0,1')'''
if text.count(linear) != 1:
    raise RuntimeError('T2D linear constitutive fixture anchor changed')
text = text.replace(linear, mfront, 1)

# Add the same established Mohr-Coulomb parameters already exercised by A4.
param_anchor = "tree.write(p, encoding='ISO-8859-1', xml_declaration=True)"
param_insert = '''parameters = root.find('parameters')
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

tree.write(p, encoding='ISO-8859-1', xml_declaration=True)'''
if text.count(param_anchor) != 1:
    raise RuntimeError('T2D parameter insertion anchor changed')
text = text.replace(param_anchor, param_insert, 1)
p.write_text(text, encoding='utf-8')
PY

# Derive the T2C gate and insert CI-only instrumentation at the exact canonical
# MFront/MGIS state boundary. The canonical implementation constructs a fresh
# MaterialStateVariablesMFront containing a fresh mgis::behaviour::BehaviourData,
# then initializes law-defined ISVs and synchronizes s1 -> s0. T2D logs those
# operations at runtime without changing their semantics.
python3 - <<'PY'
from pathlib import Path
src = Path('scripts/run-ogs-staged-construction-th2m-t2c.sh').read_text(encoding='utf-8')
needle = '''python3 /tmp/th2m-t2b-runtime.py
git diff --check'''
insert = r'''python3 /tmp/th2m-t2b-runtime.py
python3 - <<'PY_MFRONT'
from pathlib import Path
p = Path('MaterialLib/SolidModels/MFront/MFrontGeneric.h')
text = p.read_text(encoding='utf-8')
alloc = '''    createMaterialStateVariables() const
    {
        return std::make_unique<MaterialStateVariablesMFront<DisplacementDim>>(
            equivalent_plastic_strain_offset_, _behaviour);
    }'''
alloc_probe = '''    createMaterialStateVariables() const
    {
        INFO("TH2M-T2D MFront/MGIS fresh BehaviourData allocation");
        return std::make_unique<MaterialStateVariablesMFront<DisplacementDim>>(
            equivalent_plastic_strain_offset_, _behaviour);
    }'''
if text.count(alloc) != 1:
    raise RuntimeError('canonical MFront state-allocation anchor changed')
text = text.replace(alloc, alloc_probe, 1)
init = '''        auto& state =
            static_cast<MaterialStateVariablesMFront<DisplacementDim>&>(
                material_state_variables);

        auto const& ivs = getInternalVariables();'''
init_probe = '''        auto& state =
            static_cast<MaterialStateVariablesMFront<DisplacementDim>&>(
                material_state_variables);
        INFO("TH2M-T2D MFront/MGIS virgin state initializer at t = {:g}", t);

        auto const& ivs = getInternalVariables();'''
if text.count(init) != 1:
    raise RuntimeError('canonical MFront initializer anchor changed')
text = text.replace(init, init_probe, 1)
p.write_text(text, encoding='utf-8')
PY_MFRONT
git diff --check'''
if src.count(needle) != 1:
    raise RuntimeError('T2D T2C canonical patch anchor changed')
src = src.replace(needle, insert, 1)

# Rename gate paths while retaining T2C's exact active-set and birth assertions.
src = src.replace('TH2M-T2C', 'TH2M-T2D').replace('th2m-t2c', 'th2m-t2d').replace('TH2M_T2C', 'TH2M_T2D')

# Require evidence that real MFront/MGIS state initialization occurred at the
# reactivation time. The generic T2B birth path invokes the virtual material-law
# factory and initializer; these probes therefore demonstrate dynamic dispatch
# into the actual MFront state implementation rather than a linear surrogate.
needle = """if not reactivated <= referenced:\n    raise RuntimeError(f'missing u_birth captures: reactivated={sorted(reactivated)} referenced={sorted(referenced)}')\nPath('../th2m-t2d-evidence.txt').write_text(\n"""
insert = """if not reactivated <= referenced:\n    raise RuntimeError(f'missing u_birth captures: reactivated={sorted(reactivated)} referenced={sorted(referenced)}')\nmfront_allocations = log.count('TH2M-T2D MFront/MGIS fresh BehaviourData allocation')\nmfront_birth_initializers = len(re.findall(r'TH2M-T2D MFront/MGIS virgin state initializer at t = 2(?:\\.0+)?', log))\nif mfront_allocations == 0:\n    raise RuntimeError('no real MFront/MGIS BehaviourData allocation observed')\nif mfront_birth_initializers == 0:\n    raise RuntimeError('no MFront/MGIS virgin initializer observed at reactivation t=2')\nif 'MFront: integration failed' in log:\n    raise RuntimeError('MFront integration failure detected')\nPath('../th2m-t2d-evidence.txt').write_text(\n"""
if src.count(needle) != 1:
    raise RuntimeError('T2D evidence anchor changed')
src = src.replace(needle, insert, 1)
needle = """    'birth_stress=zero_unless_explicit_placement_state\\n'\n    'physical_stiffness=full_from_first_active_assembly\\n'\n"""
insert = """    'birth_stress=zero_unless_explicit_placement_state\\n'\n    f'mfront_behaviour_data_allocations={mfront_allocations}\\n'\n    f'mfront_virgin_initializers_t2={mfront_birth_initializers}\\n'\n    'mfront_mgis_stale_history_carried_over=false_by_fresh_object_replacement\\n'\n    'physical_stiffness=full_from_first_active_assembly\\n'\n"""
if src.count(needle) != 1:
    raise RuntimeError('T2D evidence field anchor changed')
src = src.replace(needle, insert, 1)
Path('/tmp/run-th2m-t2d.sh').write_text(src, encoding='utf-8')
PY

chmod +x /tmp/run-th2m-t2d.sh
/tmp/run-th2m-t2d.sh
