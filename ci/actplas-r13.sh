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

BUILD_DIR="$(pwd)/../build/release"
OGS_BIN="$BUILD_DIR/bin/ogs"
if [[ ! -x "$OGS_BIN" ]]; then
  echo "ACTPLAS_RUNTIME_CACHE=MISS_BUILD"
  cmake --preset release -DOGS_BUILD_GUI=OFF -DOGS_BUILD_UTILS=OFF -DOGS_BUILD_TESTING=ON -DOGS_USE_MFRONT=ON '-DOGS_BUILD_PROCESSES=SmallDeformation;HydroMechanics;ThermoRichardsMechanics'
  cmake --build --preset release --parallel 2
else
  echo "ACTPLAS_RUNTIME_CACHE=HIT_BASELINE"
fi
OGS_BIN="$(readlink -f "$OGS_BIN")"
test -x "$OGS_BIN"

mkdir -p actplas-evidence/logs actplas-evidence/generated-prj actplas-cases
printf 'ogs_binary=%s\n' "$OGS_BIN" > actplas-evidence/runtime.txt

python3 - <<'PY'
import pathlib, shutil, re
root=pathlib.Path.cwd(); src=root/'Tests/Data/Mechanics/Excavation'; dst=root/'actplas-cases'/'SM_MC_C5M_STATE_DIAG'
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
(root/'actplas-evidence'/'generated-prj'/'SM_MC_C5M_STATE_DIAG.prj').write_text(text,encoding='latin-1')
PY

# Diagnostic-only source instrumentation. Preserve mechanics; enrich the failure
# message with MGIS recommendation, error buffer, and start/end local state.
HDR="MaterialLib/SolidModels/MFront/MFrontGeneric.h"
cp "$HDR" /tmp/MFrontGeneric.original.h
python3 - "$HDR" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1]); t=p.read_text()
old='''            throw NumLib::AssemblyException(\n                "MFront: integration failed with status " +\n                std::to_string(status) + ".");'''
new='''            throw NumLib::AssemblyException(\n                "MFront: integration failed with status " +\n                std::to_string(status) + ", rdt=" +\n                std::to_string(behaviour_data.rdt) + ", dt=" +\n                std::to_string(dt) + ", error=\\\"" +\n                std::string(behaviour_data.error_message ? behaviour_data.error_message : "") +\n                "\\\", g0=[" + std::to_string(behaviour_data.s0.gradients[0]) + "," +\n                std::to_string(behaviour_data.s0.gradients[1]) + "," +\n                std::to_string(behaviour_data.s0.gradients[2]) + "," +\n                std::to_string(behaviour_data.s0.gradients[3]) + "]" +\n                ", g1=[" + std::to_string(behaviour_data.s1.gradients[0]) + "," +\n                std::to_string(behaviour_data.s1.gradients[1]) + "," +\n                std::to_string(behaviour_data.s1.gradients[2]) + "," +\n                std::to_string(behaviour_data.s1.gradients[3]) + "]" +\n                ", f0=[" + std::to_string(behaviour_data.s0.thermodynamic_forces[0]) + "," +\n                std::to_string(behaviour_data.s0.thermodynamic_forces[1]) + "," +\n                std::to_string(behaviour_data.s0.thermodynamic_forces[2]) + "," +\n                std::to_string(behaviour_data.s0.thermodynamic_forces[3]) + "]" +\n                ", f1=[" + std::to_string(behaviour_data.s1.thermodynamic_forces[0]) + "," +\n                std::to_string(behaviour_data.s1.thermodynamic_forces[1]) + "," +\n                std::to_string(behaviour_data.s1.thermodynamic_forces[2]) + "," +\n                std::to_string(behaviour_data.s1.thermodynamic_forces[3]) + "].");'''
assert old in t
t=t.replace(old,new,1)
p.write_text(t)
PY

cmake --build "$BUILD_DIR" --target ogs --parallel 2 > actplas-evidence/logs/r13_rebuild.log 2>&1

dir="actplas-cases/SM_MC_C5M_STATE_DIAG"
outdir="$(pwd)/actplas-evidence/out_STATE_DIAG"; mkdir -p "$outdir"
log="$(pwd)/actplas-evidence/logs/STATE_DIAG.log"
set +e
(cd "$dir" && "$OGS_BIN" -o "$outdir" time_linear_excavation.prj) >"$log" 2>&1
rc=$?
set -e

completed=no; grep -q 'Simulation completed' "$log" && completed=yes || true
mf=no; grep -q 'MFront: integration failed' "$log" && mf=yes || true
msg="$(grep -m1 'MFront: integration failed' "$log" || true)"
printf '%s\n' "$msg" > actplas-evidence/first-mfront-failure.txt
rdt="$(printf '%s' "$msg" | sed -nE 's/.*rdt=([^, ]+).*/\1/p')"; [[ -n "$rdt" ]] || rdt='-'
ft="$(grep -m1 -oE 'failed in time step #[0-9]+ at t = [^ ]+' "$log" | sed -E 's/.* at t = //' || true)"; [[ -n "$ft" ]] || ft='-'
li="$(grep 'Iteration #[0-9][0-9]* started' "$log" | tail -1 | sed -E 's/.*Iteration #([0-9]+).*/\1/' || true)"; [[ -n "$li" ]] || li='-'
printf 'case\texit_code\tcompleted\tmfront_failure\tmgis_rdt\tfirst_failed_time\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r13.tsv
printf 'STATE_DIAG\t%s\t%s\t%s\t%s\t%s\t%s\n' "$rc" "$completed" "$mf" "$rdt" "$ft" "$li" | tee -a actplas-evidence/sm-r13.tsv

cp /tmp/MFrontGeneric.original.h "$HDR"
printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
printf '%s\n' 'R13 diagnostic-only instrumentation: exact upstream OGS mechanics are preserved; failure diagnostics expose MGIS error_message plus local s0/s1 gradients and thermodynamic forces.' > actplas-evidence/r13-purpose.txt
cat actplas-evidence/sm-r13.tsv
