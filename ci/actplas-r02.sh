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

# The exact-ref runtime is immutable for this diagnostic series. Reuse the
# cached binary directly when available; .prj-only iterations must not force a
# full OGS rebuild. The workspace path is stable on GitHub-hosted runners.
OGS_BIN="$(pwd)/../build/release/bin/ogs"
if [[ -x "$OGS_BIN" ]]; then
  echo "ACTPLAS_RUNTIME_CACHE=HIT_SKIP_BUILD"
else
  echo "ACTPLAS_RUNTIME_CACHE=MISS_BUILD"
  cmake --preset release \
    -DOGS_BUILD_GUI=OFF \
    -DOGS_BUILD_UTILS=OFF \
    -DOGS_BUILD_TESTING=ON \
    -DOGS_USE_MFRONT=ON \
    '-DOGS_BUILD_PROCESSES=SmallDeformation;HydroMechanics;ThermoRichardsMechanics'
  cmake --build --preset release --parallel 2
fi
OGS_BIN="$(readlink -f "$OGS_BIN")"
test -x "$OGS_BIN"

mkdir -p actplas-evidence/controls actplas-evidence/logs actplas-evidence/generated-prj
printf 'ogs_binary=%s\nruntime_cache_skip_build=%s\n' "$OGS_BIN" "$([[ -d ../build/release ]] && echo yes || echo no)" > actplas-evidence/runtime.txt

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
base_ts = '''                    <timesteps>
                        <pair>
                            <repeat>2</repeat>
                            <delta_t>0.5</delta_t>
                        </pair>
                        <pair>
                            <repeat>35</repeat>
                            <delta_t>0.2</delta_t>
                        </pair>
                    </timesteps>'''

def refined_ts(dt):
    n = round(0.5 / dt)
    if abs(n * dt - 0.5) > 1e-12:
        raise RuntimeError(dt)
    return f'''                    <timesteps>
                        <pair>
                            <repeat>1</repeat>
                            <delta_t>0.5</delta_t>
                        </pair>
                        <pair>
                            <repeat>{n}</repeat>
                            <delta_t>{dt:.12g}</delta_t>
                        </pair>
                        <pair>
                            <repeat>35</repeat>
                            <delta_t>0.2</delta_t>
                        </pair>
                    </timesteps>'''

def build_case(name, cohesion, event_dt=None):
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
    if event_dt is not None:
        if text.count(base_ts) != 1:
            raise RuntimeError('unexpected time stepping layout')
        text = text.replace(base_ts, refined_ts(event_dt))
    p.write_text(text, encoding='latin-1')

# Fine cohesion sweep across the R01 bracket: C20M passes, C10M fails.
for tag, cohesion in [('20M','20e6'),('18M','18e6'),('16M','16e6'),('14M','14e6'),('12M','12e6'),('10M','10e6')]:
    build_case(f'SM_MC_DEACT_C{tag}', cohesion)

# Same failing material (C=10 MPa), same deactivation definition, but sample the
# deactivation onset after t=0.51 with progressively smaller global time steps.
for tag, dt in [('DT100',0.1),('DT050',0.05),('DT010',0.01)]:
    build_case(f'SM_MC_DEACT_C10M_{tag}', '10e6', event_dt=dt)

(root/'actplas-evidence'/'generated-prj-summary.txt').write_text(
    'R02 fine cohesion sweep preserves exact upstream excavation geometry, boundary conditions, initial stress, deactivation definition, solver, and all Mohr-Coulomb parameters except cohesion.\n'
    'R02 timestep probes preserve C=10 MPa and the exact deactivation definition; only fixed time-step sampling between t=0.5 and t=1.0 changes. This tests whether smaller global dt can regularize the local MFront failure or simply moves it to the first sampled deactivation time.\n', encoding='utf-8')
PY

printf 'case\tcohesion\tevent_dt\texit_code\tcompleted\tmfront_integration_failure\tfirst_failed_time\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r02.tsv
run_case() {
  local name="$1" cohesion="$2" event_dt="$3" dir outdir log rc completed mf_fail fail_time last_iter
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
  last_iter="$(grep 'Iteration #[0-9][0-9]* started' "$log" | tail -1 | sed -E 's/.*Iteration #([0-9]+).*/\1/' || true)"
  [[ -n "$last_iter" ]] || last_iter='-'
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$cohesion" "$event_dt" "$rc" "$completed" "$mf_fail" "$fail_time" "$last_iter" | tee -a actplas-evidence/sm-r02.tsv
}

for tag in 20M 18M 16M 14M 12M 10M; do
  cohesion="${tag%M}e6"
  run_case "SM_MC_DEACT_C${tag}" "$cohesion" 0.5
done
run_case SM_MC_DEACT_C10M_DT100 10e6 0.1
run_case SM_MC_DEACT_C10M_DT050 10e6 0.05
run_case SM_MC_DEACT_C10M_DT010 10e6 0.01

printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' \
  "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
for name in SM_MC_DEACT_C20M SM_MC_DEACT_C18M SM_MC_DEACT_C16M SM_MC_DEACT_C14M SM_MC_DEACT_C12M SM_MC_DEACT_C10M SM_MC_DEACT_C10M_DT100 SM_MC_DEACT_C10M_DT050 SM_MC_DEACT_C10M_DT010; do
  cp "actplas-cases/$name/time_linear_excavation.prj" "actplas-evidence/generated-prj/$name.prj"
done
cat actplas-evidence/controls.tsv
cat actplas-evidence/sm-r02.tsv
