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
        <parameter><name>MC_Cohesion</name><type>Constant</type><value>10e6</value></parameter>
        <parameter><name>MC_FrictionAngle</name><type>Constant</type><value>25</value></parameter>
        <parameter><name>MC_DilatancyAngle</name><type>Constant</type><value>10</value></parameter>
        <parameter><name>MC_TransitionAngle</name><type>Constant</type><value>27</value></parameter>
        <parameter><name>MC_TensionCutOff</name><type>Constant</type><value>1e6</value></parameter>
'''

def build(name, endpoint, dt):
    dst = cases/name
    shutil.copytree(src, dst, dirs_exist_ok=True)
    p = dst/'time_linear_excavation.prj'
    text = p.read_text(encoding='latin-1')
    assert text.count(old) == 1
    text = text.replace(old, new)
    marker = '            <specific_body_force>0 0</specific_body_force>'
    assert text.count(marker) == 1
    text = text.replace(marker, marker+'\n            <reference_temperature>T_ref</reference_temperature>')
    text = text.replace('    </parameters>', params+'    </parameters>')
    ds = '''            <deactivated_subdomains>
                <deactivated_subdomain>
                    <time_curve>excavation_curve</time_curve>
                    <line_segment>
                        <start>0 0 0</start>
                        <end>2.5 0 0</end>
                    </line_segment>
                    <material_ids>0</material_ids>
                </deactivated_subdomain>
            </deactivated_subdomains>'''
    text, n = re.subn(r'            <deactivated_subdomains>.*?            </deactivated_subdomains>', ds, text, flags=re.S)
    if n != 1: raise RuntimeError(f'deactivated_subdomains replacement count={n}')
    text, n = re.subn(
        r'<curve>\s*<!-- back-filling half of the tunnel -->\s*<name>excavation_curve</name>.*?</curve>',
        f'''<curve>
            <name>excavation_curve</name>
            <coords>0 1 8</coords>
            <values>0 {endpoint} {endpoint}</values>
        </curve>''', text, flags=re.S)
    if n != 1: raise RuntimeError(f'excavation_curve replacement count={n}')
    repeat = int(round(8.0/dt))
    assert abs(repeat*dt - 8.0) < 1e-10
    ts = f'''                    <timesteps>
                        <pair>
                            <repeat>{repeat}</repeat>
                            <delta_t>{dt}</delta_t>
                        </pair>
                    </timesteps>'''
    text, n = re.subn(r'                    <timesteps>.*?                    </timesteps>', ts, text, flags=re.S)
    if n != 1: raise RuntimeError(f'timesteps replacement count={n}')
    p.write_text(text, encoding='latin-1')

# R05 isolates whether stability is governed by the spatial front increment
# delta_x = endpoint * dt (the front advances linearly from t=0 to t=1).
for endpoint, dts in {
    2.5:(0.05,0.04,0.025,0.02,0.0125,0.01),
    2.0:(0.05,0.04,0.025,0.02),
    1.5:(0.05,0.04,0.025,0.02),
    1.25:(0.05,0.04,0.025,0.02),
}.items():
    etag = str(endpoint).replace('.', 'p')
    for dt in dts:
        dtag = str(dt).replace('.', 'p')
        build(f'SM_MC_C10M_PROGRESS_END_{etag}_DT_{dtag}', endpoint, dt)

(root/'actplas-evidence'/'generated-prj-summary.txt').write_text(
'R05 holds C=10 MPa and all mechanics fixed while refining the truly progressive excavation front. It varies endpoint and dt so the spatial front increment delta_x=endpoint*dt spans the R04 pass/fail interval. This tests whether failure is tied to a critical front position near x~1 or to removing too much material in one accepted step.\n', encoding='utf-8')
PY

printf 'case\tendpoint\tdt\tdelta_x\texit_code\tcompleted\tmfront_integration_failure\tfirst_failed_time\tfront_at_failure\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r05.tsv
run_case() {
  local name="$1" endpoint="$2" dt="$3" dir outdir log rc completed mf_fail fail_time last_iter delta_x front_fail
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
  delta_x="$(python3 -c "print(float('$endpoint')*float('$dt'))")"
  if [[ "$fail_time" != '-' ]]; then front_fail="$(python3 -c "print(float('$endpoint')*min(float('$fail_time'),1.0))")"; else front_fail='-'; fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$endpoint" "$dt" "$delta_x" "$rc" "$completed" "$mf_fail" "$fail_time" "$front_fail" "$last_iter" | tee -a actplas-evidence/sm-r05.tsv
}

for endpoint in 2.5 2.0 1.5 1.25; do
  etag="${endpoint/./p}"
  case "$endpoint" in
    2.5) dts="0.05 0.04 0.025 0.02 0.0125 0.01" ;;
    *) dts="0.05 0.04 0.025 0.02" ;;
  esac
  for dt in $dts; do
    dtag="${dt/./p}"
    run_case "SM_MC_C10M_PROGRESS_END_${etag}_DT_${dtag}" "$endpoint" "$dt"
  done
done

printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
for p in actplas-cases/*/time_linear_excavation.prj; do cp "$p" "actplas-evidence/generated-prj/$(basename "$(dirname "$p")").prj"; done
cat actplas-evidence/sm-r05.tsv
