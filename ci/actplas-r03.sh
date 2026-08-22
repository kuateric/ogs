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

OGS_BIN="$(pwd)/../build/release/bin/ogs"
if [[ ! -x "$OGS_BIN" ]]; then
  echo "ACTPLAS_RUNTIME_CACHE=MISS_BUILD"
  cmake --preset release \
    -DOGS_BUILD_GUI=OFF \
    -DOGS_BUILD_UTILS=OFF \
    -DOGS_BUILD_TESTING=ON \
    -DOGS_USE_MFRONT=ON \
    '-DOGS_BUILD_PROCESSES=SmallDeformation;HydroMechanics;ThermoRichardsMechanics'
  cmake --build --preset release --parallel 2
else
  echo "ACTPLAS_RUNTIME_CACHE=HIT_SKIP_BUILD"
fi
OGS_BIN="$(readlink -f "$OGS_BIN")"
test -x "$OGS_BIN"

mkdir -p actplas-evidence/logs actplas-evidence/generated-prj
printf 'ogs_binary=%s\n' "$OGS_BIN" > actplas-evidence/runtime.txt

python3 - <<'PY'
import pathlib, re, shutil
root = pathlib.Path.cwd()
src = root/'Tests/Data/Mechanics/Excavation'
cases = root/'actplas-cases'; cases.mkdir(exist_ok=True)
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
params = '''        <parameter><name>T_ref</name><type>Constant</type><values>293.15</values></parameter>
        <parameter><name>MC_Cohesion</name><type>Constant</type><value>{}</value></parameter>
        <parameter><name>MC_FrictionAngle</name><type>Constant</type><value>25</value></parameter>
        <parameter><name>MC_DilatancyAngle</name><type>Constant</type><value>10</value></parameter>
        <parameter><name>MC_TransitionAngle</name><type>Constant</type><value>27</value></parameter>
        <parameter><name>MC_TensionCutOff</name><type>Constant</type><value>1e6</value></parameter>
'''

def build(name, cohesion, gradual_only=False):
    dst = cases/name
    shutil.copytree(src, dst, dirs_exist_ok=True)
    p=dst/'time_linear_excavation.prj'
    text=p.read_text(encoding='latin-1')
    assert text.count(old)==1
    text=text.replace(old,new)
    marker='            <specific_body_force>0 0</specific_body_force>'
    assert text.count(marker)==1
    text=text.replace(marker, marker+'\n            <reference_temperature>T_ref</reference_temperature>')
    text=text.replace('    </parameters>', params.format(cohesion)+'    </parameters>')
    if gradual_only:
        # Remove only the first abrupt full-material deactivation interval.
        pat=r'''\s*<deactivated_subdomain>\s*<time_interval>\s*<start>0\.51\s*</start>\s*<end>\s*1\.0\s*</end>\s*</time_interval>\s*<material_ids>0</material_ids>\s*</deactivated_subdomain>'''
        text,n=re.subn(pat,'',text,flags=re.S)
        if n!=1:
            raise RuntimeError(f'expected one abrupt block, removed={n}')
    p.write_text(text,encoding='latin-1')

for tag,val in [('14000','14e6'),('13750','13.75e6'),('13500','13.5e6'),('13250','13.25e6'),('13000','13e6'),('12750','12.75e6'),('12500','12.5e6'),('12000','12e6')]:
    build('SM_MC_DEACT_C'+tag+'K', val)
build('SM_MC_DEACT_C10M_GRADUAL_ONLY','10e6',gradual_only=True)

(root/'actplas-evidence'/'generated-prj-summary.txt').write_text(
'R03 refines the R02 cohesion transition between 12 and 14 MPa without changing geometry, solver, initial stress, or deactivation definition.\n'
'R03_GRADUAL_ONLY keeps C=10 MPa and the upstream time_curve/line_segment deactivation but removes only the abrupt full-material time_interval block active after t=0.51. This isolates whether the constitutive integration failure is driven by the discontinuous bulk element removal.\n', encoding='utf-8')
PY

printf 'case\tcohesion\tdeactivation_mode\texit_code\tcompleted\tmfront_integration_failure\tfirst_failed_time\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r03.tsv
run_case() {
  local name="$1" cohesion="$2" mode="$3" dir outdir log rc completed mf_fail fail_time last_iter
  dir="actplas-cases/$name"; outdir="$(pwd)/actplas-evidence/out_${name}"; log="$(pwd)/actplas-evidence/logs/${name}.log"
  mkdir -p "$outdir"
  set +e
  (cd "$dir" && "$OGS_BIN" -o "$outdir" time_linear_excavation.prj) >"$log" 2>&1
  rc=$?
  set -e
  grep -q 'Simulation completed' "$log" && completed=yes || completed=no
  grep -q 'MFront: integration failed' "$log" && mf_fail=yes || mf_fail=no
  fail_time="$(grep -m1 -oE 'failed in time step #[0-9]+ at t = [^ ]+' "$log" | sed -E 's/.* at t = //' || true)"; [[ -n "$fail_time" ]] || fail_time='-'
  last_iter="$(grep 'Iteration #[0-9][0-9]* started' "$log" | tail -1 | sed -E 's/.*Iteration #([0-9]+).*/\1/' || true)"; [[ -n "$last_iter" ]] || last_iter='-'
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$cohesion" "$mode" "$rc" "$completed" "$mf_fail" "$fail_time" "$last_iter" | tee -a actplas-evidence/sm-r03.tsv
}

for tag in 14000 13750 13500 13250 13000 12750 12500 12000; do
  case "$tag" in
    14000) c=14e6;; 13750) c=13.75e6;; 13500) c=13.5e6;; 13250) c=13.25e6;; 13000) c=13e6;; 12750) c=12.75e6;; 12500) c=12.5e6;; 12000) c=12e6;;
  esac
  run_case "SM_MC_DEACT_C${tag}K" "$c" abrupt_plus_curve
done
run_case SM_MC_DEACT_C10M_GRADUAL_ONLY 10e6 gradual_curve_only

printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
for p in actplas-cases/*/time_linear_excavation.prj; do cp "$p" "actplas-evidence/generated-prj/$(basename "$(dirname "$p")").prj"; done
cat actplas-evidence/sm-r03.tsv
