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
  cmake --preset release -DOGS_BUILD_GUI=OFF -DOGS_BUILD_UTILS=OFF -DOGS_BUILD_TESTING=ON -DOGS_USE_MFRONT=ON '-DOGS_BUILD_PROCESSES=SmallDeformation;HydroMechanics;ThermoRichardsMechanics'
  cmake --build --preset release --parallel 2
else
  echo "ACTPLAS_RUNTIME_CACHE=HIT_SKIP_OGS_BUILD"
fi
OGS_BIN="$(readlink -f "$OGS_BIN")"
test -x "$OGS_BIN"

BUILD_DIR="$(pwd)/../build/release"
MFRONT_SRC="MaterialLib/SolidModels/MFront/MohrCoulombAbboSloan.mfront"
MFRONT_LIB="$BUILD_DIR/lib/libOgsMFrontBehaviour.so"
test -f "$MFRONT_SRC"
test -f "$MFRONT_LIB"
cp "$MFRONT_SRC" /tmp/MohrCoulombAbboSloan.original.mfront

mkdir -p actplas-evidence/logs actplas-evidence/generated-prj actplas-cases
printf 'ogs_binary=%s\nmfront_library=%s\n' "$OGS_BIN" "$MFRONT_LIB" > actplas-evidence/runtime.txt

python3 - <<'PY'
import pathlib, shutil, re
root=pathlib.Path.cwd(); src=root/'Tests/Data/Mechanics/Excavation'; dst=root/'actplas-cases'/'SM_MC_C5M_LOCAL_DIAG'
shutil.copytree(src,dst,dirs_exist_ok=True)
p=dst/'time_linear_excavation.prj'; text=p.read_text(encoding='latin-1')
old='''            <constitutive_relation id="0,1">
                <type>LinearElasticIsotropic</type>
                <youngs_modulus>E</youngs_modulus>
                <poissons_ratio>nu</poissons_ratio>
            </constitutive_relation>'''
new='''            <constitutive_relation id="0,1">
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
assert text.count(old)==1; text=text.replace(old,new)
marker='            <specific_body_force>0 0</specific_body_force>'
text=text.replace(marker,marker+'\n            <reference_temperature>T_ref</reference_temperature>')
params='''        <parameter><name>T_ref</name><type>Constant</type><values>293.15</values></parameter>
        <parameter><name>MC_Cohesion</name><type>Constant</type><value>5e6</value></parameter>
        <parameter><name>MC_FrictionAngle</name><type>Constant</type><value>25</value></parameter>
        <parameter><name>MC_DilatancyAngle</name><type>Constant</type><value>10</value></parameter>
        <parameter><name>MC_TransitionAngle</name><type>Constant</type><value>27</value></parameter>
        <parameter><name>MC_TensionCutOff</name><type>Constant</type><value>1e6</value></parameter>
'''
text=text.replace('    </parameters>',params+'    </parameters>')
ds='''            <deactivated_subdomains>
                <deactivated_subdomain>
                    <time_curve>excavation_curve</time_curve>
                    <line_segment>
                        <start>0 0 0</start>
                        <end>2.5 0 0</end>
                    </line_segment>
                    <material_ids>0</material_ids>
                </deactivated_subdomain>
            </deactivated_subdomains>'''
text,n=re.subn(r'            <deactivated_subdomains>.*?            </deactivated_subdomains>',ds,text,flags=re.S); assert n==1
curve='''<curve>
            <name>excavation_curve</name>
            <coords>0 2.5 8</coords>
            <values>0 2.5 2.5</values>
        </curve>'''
text,n=re.subn(r'<curve>\s*<!-- back-filling half of the tunnel -->\s*<name>excavation_curve</name>.*?</curve>',curve,text,flags=re.S); assert n==1
ts='''                    <timesteps>
                        <pair><repeat>320</repeat><delta_t>0.025</delta_t></pair>
                    </timesteps>'''
text,n=re.subn(r'                    <timesteps>.*?                    </timesteps>',ts,text,flags=re.S); assert n==1
text=text.replace('            <max_iter>10</max_iter>','            <max_iter>30</max_iter>')
p.write_text(text,encoding='latin-1')
(root/'actplas-evidence'/'generated-prj'/'SM_MC_C5M_LOCAL_DIAG.prj').write_text(text,encoding='latin-1')
PY

# Diagnostic-only MFront variants. OGS C++ production mechanics remain untouched.
printf 'case\tepsilon\tlocal_max_iter\texit_code\tcompleted\tmfront_integration_failure\tfirst_failed_time\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r11.tsv

run_variant() {
  local name="$1" eps="$2" local_iter="$3"
  cp /tmp/MohrCoulombAbboSloan.original.mfront "$MFRONT_SRC"
  python3 - "$MFRONT_SRC" "$eps" "$local_iter" <<'PY'
import pathlib,re,sys
p=pathlib.Path(sys.argv[1]); eps=sys.argv[2]; it=sys.argv[3]
t=p.read_text()
t,n=re.subn(r'@Epsilon\s+[^;]+;', f'@Epsilon {eps};', t); assert n==1
t,n=re.subn(r'@MaximumNumberOfIterations\s+[^;]+;', f'@MaximumNumberOfIterations {it};', t); assert n==1
p.write_text(t)
PY
  # Rebuild only the generated MFront behaviour library. No OGS C++ rebuild.
  cmake --build "$BUILD_DIR" --target build_mfront --parallel 2 >"actplas-evidence/logs/${name}_build.log" 2>&1
  local dir="actplas-cases/SM_MC_C5M_LOCAL_DIAG"
  local outdir="$(pwd)/actplas-evidence/out_${name}"; mkdir -p "$outdir"
  local log="$(pwd)/actplas-evidence/logs/${name}.log"
  set +e
  (cd "$dir" && "$OGS_BIN" -o "$outdir" time_linear_excavation.prj) >"$log" 2>&1
  local rc=$?
  set -e
  grep -q 'Simulation completed' "$log" && local completed=yes || local completed=no
  grep -q 'MFront: integration failed' "$log" && local mf=yes || local mf=no
  local ft li
  ft="$(grep -m1 -oE 'failed in time step #[0-9]+ at t = [^ ]+' "$log" | sed -E 's/.* at t = //' || true)"; [[ -n "$ft" ]] || ft='-'
  li="$(grep 'Iteration #[0-9][0-9]* started' "$log" | tail -1 | sed -E 's/.*Iteration #([0-9]+).*/\1/' || true)"; [[ -n "$li" ]] || li='-'
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$eps" "$local_iter" "$rc" "$completed" "$mf" "$ft" "$li" | tee -a actplas-evidence/sm-r11.tsv
}

run_variant BASE_E14_I200 1e-14 200
run_variant EPS_E12_I200 1e-12 200
run_variant EPS_E10_I200 1e-10 200
run_variant EPS_E8_I200 1e-8 200
run_variant EPS_E14_I400 1e-14 400

cp /tmp/MohrCoulombAbboSloan.original.mfront "$MFRONT_SRC"
printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
printf '%s\n' 'R11 diagnostic: only MohrCoulombAbboSloan local MFront @Epsilon and @MaximumNumberOfIterations are varied; OGS C++ mechanics and deactivation implementation are unchanged. The generated behaviour library is rebuilt via build_mfront only.' > actplas-evidence/r11-purpose.txt
cat actplas-evidence/sm-r11.tsv
