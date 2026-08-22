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

mkdir -p actplas-evidence/logs actplas-evidence/generated-prj actplas-cases
printf 'ogs_binary=%s\n' "$OGS_BIN" > actplas-evidence/runtime.txt

python3 - <<'PY'
import pathlib, shutil, re
root=pathlib.Path.cwd(); src=root/'Tests/Data/Mechanics/Excavation'; cases=root/'actplas-cases'
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

def build(name, damping, damping_reduction=None):
    dt=0.025; endpoint=2.5; repeat=320
    dst=cases/name; shutil.copytree(src,dst,dirs_exist_ok=True)
    p=dst/'time_linear_excavation.prj'; text=p.read_text(encoding='latin-1')
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
    # Failure in R08 occurs during Newton iteration 2, so isolate the existing project-level Newton damping facility.
    repl=f'''            <max_iter>30</max_iter>\n            <damping>{damping}</damping>'''
    if damping_reduction is not None:
        repl += f'\n            <damping_reduction>{damping_reduction}</damping_reduction>'
    text=text.replace('            <max_iter>10</max_iter>', repl)
    p.write_text(text,encoding='latin-1')

spec=[
 ('SM_MC_C5M_DAMP_1p0',1.0,None),
 ('SM_MC_C5M_DAMP_0p7',0.7,None),
 ('SM_MC_C5M_DAMP_0p5',0.5,None),
 ('SM_MC_C5M_DAMP_0p3',0.3,None),
 ('SM_MC_C5M_DAMP_0p2',0.2,None),
 ('SM_MC_C5M_DAMP_0p3_RED7',0.3,7.0),
 ('SM_MC_C5M_DAMP_0p2_RED7',0.2,7.0),
]
with (root/'actplas-evidence'/'case-manifest.tsv').open('w') as f:
    f.write('case\tdamping\tdamping_reduction\n')
    for name,d,dr in spec:
        build(name,d,dr); f.write(f'{name}\t{d}\t{dr if dr is not None else "-"}\n')
(root/'actplas-evidence'/'r09-purpose.txt').write_text(
 'R09 keeps the exact C=5 MPa progressive-deactivation case and dx=0.025 m from R08, and varies only the existing OGS Newton damping controls. The goal is to test a project-level robust solution before considering production-code changes.\n')
PY

printf 'case\tdamping\tdamping_reduction\texit_code\tcompleted\tmfront_integration_failure\tfirst_failed_time\tfront_at_failure\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r09.tsv
while IFS=$'\t' read -r name damping reduction; do
  [[ "$name" == case ]] && continue
  dir="actplas-cases/$name"; outdir="$(pwd)/actplas-evidence/out_${name}"; log="$(pwd)/actplas-evidence/logs/${name}.log"; mkdir -p "$outdir"
  set +e; (cd "$dir" && "$OGS_BIN" -o "$outdir" time_linear_excavation.prj) >"$log" 2>&1; rc=$?; set -e
  grep -q 'Simulation completed' "$log" && completed=yes || completed=no
  grep -q 'MFront: integration failed' "$log" && mf=yes || mf=no
  ft="$(grep -m1 -oE 'failed in time step #[0-9]+ at t = [^ ]+' "$log" | sed -E 's/.* at t = //' || true)"; [[ -n "$ft" ]] || ft='-'
  li="$(grep 'Iteration #[0-9][0-9]* started' "$log" | tail -1 | sed -E 's/.*Iteration #([0-9]+).*/\1/' || true)"; [[ -n "$li" ]] || li='-'
  if [[ "$ft" != '-' ]]; then ff="$ft"; else ff='-'; fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$damping" "$reduction" "$rc" "$completed" "$mf" "$ft" "$ff" "$li" | tee -a actplas-evidence/sm-r09.tsv
done < actplas-evidence/case-manifest.tsv

printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
for p in actplas-cases/*/time_linear_excavation.prj; do cp "$p" "actplas-evidence/generated-prj/$(basename "$(dirname "$p")").prj"; done
cat actplas-evidence/sm-r09.tsv
