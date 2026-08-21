#!/usr/bin/env bash
set -euo pipefail

: "${OGS_UPSTREAM_SHA:=adf770974c7ee0435702fe617634d03d17ab7cb8}"
: "${OGS_UPSTREAM_URL:=https://gitlab.opengeosys.org/ogs/ogs.git}"

rm -rf ogs-upstream
git clone --filter=blob:none --no-checkout "$OGS_UPSTREAM_URL" ogs-upstream
cd ogs-upstream
git fetch --depth=1 origin "$OGS_UPSTREAM_SHA"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "$OGS_UPSTREAM_SHA"
test -f Tests/Data/Mechanics/Excavation/time_linear_excavation.prj
test -f Tests/Data/Mechanics/MohrCoulombAbboSloan/slope.prj
test -f MaterialLib/SolidModels/MFront/MohrCoulombAbboSloan.mfront

cmake --preset release \
  -DOGS_BUILD_GUI=OFF \
  -DOGS_BUILD_UTILS=OFF \
  -DOGS_BUILD_TESTING=ON \
  -DOGS_USE_MFRONT=ON \
  '-DOGS_BUILD_PROCESSES=SmallDeformation;HydroMechanics;ThermoRichardsMechanics'
cmake --build --preset release --parallel 2

mkdir -p actplas-evidence/controls actplas-evidence/logs actplas-evidence/generated-prj
OGS_BIN="$(find "$(pwd)/../build/release" -type f -name ogs -perm -111 2>/dev/null | head -n1 || true)"
if [[ -z "$OGS_BIN" ]]; then
  OGS_BIN="$(find "$(pwd)/../build" -type f -name ogs -perm -111 2>/dev/null | head -n1 || true)"
fi
test -n "$OGS_BIN"
OGS_BIN="$(readlink -f "$OGS_BIN")"
printf 'ogs_binary=%s\n' "$OGS_BIN" > actplas-evidence/runtime.txt

printf 'control\texit_code\tcompleted\n' > actplas-evidence/controls.tsv
run_control() {
  local name="$1" dir="$2" prj="$3" outdir log rc completed
  outdir="$(pwd)/actplas-evidence/controls/out_${name}"
  log="$(pwd)/actplas-evidence/controls/${name}.log"
  mkdir -p "$outdir"
  set +e
  (cd "$dir" && "$OGS_BIN" -o "$outdir" "$prj") >"$log" 2>&1
  rc=$?
  set -e
  if grep -q 'Simulation completed' "$log"; then completed=yes; else completed=no; fi
  printf '%s\t%s\t%s\n' "$name" "$rc" "$completed" | tee -a actplas-evidence/controls.tsv
}
run_control SM_ELASTIC_EXCAVATION Tests/Data/Mechanics/Excavation time_linear_excavation.prj
run_control SM_MC_SLOPE Tests/Data/Mechanics/MohrCoulombAbboSloan slope.prj

python3 - <<'PY'
import pathlib, re, shutil
root = pathlib.Path.cwd()
src = root / 'Tests/Data/Mechanics/Excavation'
cases = root / 'actplas-cases'
cases.mkdir(exist_ok=True)
old = '''            <constitutive_relation id="0,1">
                <type>LinearElasticIsotropic</type>
                <youngs_modulus>E</youngs_modulus>
                <poissons_ratio>nu</poissons_ratio>
            </constitutive_relation>'''
new = '''            <constitutive_relation id="0,1">
                <type>MFront</type>
                <behaviour>MohrCoulombAbboSloan</behaviour>
                <material_properties>
                    <material_property name="YoungModulus" parameter="E"/>
                    <material_property name="PoissonRatio" parameter="nu"/>
                    <material_property name="Cohesion" parameter="MC_Cohesion"/>
                    <material_property name="FrictionAngle" parameter="MC_FrictionAngle"/>
                    <material_property name="DilatancyAngle" parameter="MC_DilatancyAngle"/>
                    <material_property name="TransitionAngle" parameter="MC_TransitionAngle"/>
                    <material_property name="TensionCutOffParameter" parameter="MC_TensionCutOff"/>
                </material_properties>
            </constitutive_relation>'''
params_template = '''        <parameter><name>T_ref</name><type>Constant</type><values>293.15</values></parameter>
        <parameter><name>MC_Cohesion</name><type>Constant</type><value>{cohesion}</value></parameter>
        <parameter><name>MC_FrictionAngle</name><type>Constant</type><value>25</value></parameter>
        <parameter><name>MC_DilatancyAngle</name><type>Constant</type><value>10</value></parameter>
        <parameter><name>MC_TransitionAngle</name><type>Constant</type><value>27</value></parameter>
        <parameter><name>MC_TensionCutOff</name><type>Constant</type><value>1e6</value></parameter>
'''

def build_case(name, cohesion, remove_deact=False):
    dst = cases / name
    shutil.copytree(src, dst, dirs_exist_ok=True)
    p = dst / 'time_linear_excavation.prj'
    text = p.read_text(encoding='latin-1')
    if text.count(old) != 1:
        raise RuntimeError('expected exactly one elastic constitutive relation')
    text = text.replace(old, new)
    marker = '            <specific_body_force>0 0</specific_body_force>'
    if text.count(marker) != 1:
        raise RuntimeError('unexpected process layout')
    text = text.replace(marker, marker + '\n            <reference_temperature>T_ref</reference_temperature>')
    if text.count('    </parameters>') != 1:
        raise RuntimeError('unexpected parameters layout')
    text = text.replace('    </parameters>', params_template.format(cohesion=cohesion) + '    </parameters>')
    if remove_deact:
        text, n = re.subn(r'\s*<deactivated_subdomains>.*?</deactivated_subdomains>', '', text, count=1, flags=re.S)
        if n != 1:
            raise RuntimeError('expected exactly one deactivated_subdomains block')
    p.write_text(text, encoding='latin-1')

build_case('SM_MC_NO_DEACT', '5e6', remove_deact=True)
for tag, cohesion in [('100M','100e6'),('50M','50e6'),('20M','20e6'),('10M','10e6'),('5M','5e6'),('2M','2e6'),('1M','1e6')]:
    build_case(f'SM_MC_DEACT_C{tag}', cohesion, remove_deact=False)

(root/'actplas-evidence'/'generated-prj-summary.txt').write_text(
    'SM_MC_NO_DEACT_C5M = exact upstream excavation with MFront MohrCoulombAbboSloan and deactivated_subdomains removed; this is only a runtime/material-load control, not a matched excavation stress path.\n'
    'SM_MC_DEACT cohesion sweep = exact same upstream excavation/deactivation path and identical MC parameters except cohesion. High cohesion is intended as the near-elastic deactivation control; decreasing cohesion probes onset of plasticity-related failure.\n', encoding='utf-8')
PY

printf 'case\tcohesion\texit_code\tcompleted\tmfront_integration_failure\tfirst_failed_time\n' > actplas-evidence/sm-r01.tsv
run_case() {
  local name="$1" cohesion="$2" dir outdir log rc completed mf_fail fail_time
  dir="actplas-cases/$name"
  outdir="$(pwd)/actplas-evidence/out_${name}"
  log="$(pwd)/actplas-evidence/logs/${name}.log"
  mkdir -p "$outdir"
  set +e
  (cd "$dir" && "$OGS_BIN" -o "$outdir" time_linear_excavation.prj) >"$log" 2>&1
  rc=$?
  set -e
  if grep -q 'Simulation completed' "$log"; then completed=yes; else completed=no; fi
  if grep -q 'MFront: integration failed' "$log"; then mf_fail=yes; else mf_fail=no; fi
  fail_time="$(grep -m1 -oE 'failed in time step #[0-9]+ at t = [^ ]+' "$log" | sed -E 's/.* at t = //' || true)"
  [[ -n "$fail_time" ]] || fail_time='-'
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$cohesion" "$rc" "$completed" "$mf_fail" "$fail_time" | tee -a actplas-evidence/sm-r01.tsv
}
run_case SM_MC_NO_DEACT 5e6
run_case SM_MC_DEACT_C100M 100e6
run_case SM_MC_DEACT_C50M 50e6
run_case SM_MC_DEACT_C20M 20e6
run_case SM_MC_DEACT_C10M 10e6
run_case SM_MC_DEACT_C5M 5e6
run_case SM_MC_DEACT_C2M 2e6
run_case SM_MC_DEACT_C1M 1e6

printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' \
  "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
cp actplas-cases/SM_MC_NO_DEACT/time_linear_excavation.prj actplas-evidence/generated-prj/SM_MC_NO_DEACT_C5M.prj
for name in SM_MC_DEACT_C100M SM_MC_DEACT_C50M SM_MC_DEACT_C20M SM_MC_DEACT_C10M SM_MC_DEACT_C5M SM_MC_DEACT_C2M SM_MC_DEACT_C1M; do
  cp "actplas-cases/$name/time_linear_excavation.prj" "actplas-evidence/generated-prj/$name.prj"
done
cat actplas-evidence/controls.tsv
cat actplas-evidence/sm-r01.tsv
