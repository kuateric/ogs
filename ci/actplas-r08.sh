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

def build(name, cohesion, dt, endpoint):
    repeat=round(8.0/dt); assert abs(repeat*dt-8)<1e-12
    dst=cases/name; shutil.copytree(src,dst,dirs_exist_ok=True)
    p=dst/'time_linear_excavation.prj'; text=p.read_text(encoding='latin-1')
    assert text.count(old)==1; text=text.replace(old,new)
    marker='            <specific_body_force>0 0</specific_body_force>'
    text=text.replace(marker,marker+'\n            <reference_temperature>T_ref</reference_temperature>')
    params=f'''        <parameter><name>T_ref</name><type>Constant</type><values>293.15</values></parameter>\n        <parameter><name>MC_Cohesion</name><type>Constant</type><value>{cohesion}e6</value></parameter>\n        <parameter><name>MC_FrictionAngle</name><type>Constant</type><value>25</value></parameter>\n        <parameter><name>MC_DilatancyAngle</name><type>Constant</type><value>10</value></parameter>\n        <parameter><name>MC_TransitionAngle</name><type>Constant</type><value>27</value></parameter>\n        <parameter><name>MC_TensionCutOff</name><type>Constant</type><value>1e6</value></parameter>\n'''
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
    # 1 m/s front until endpoint, then hold. Critical centroid band near x=0.275 m is crossed independently of total target extent.
    curve=f'''<curve>\n            <name>excavation_curve</name>\n            <coords>0 {endpoint:.17g} 8</coords>\n            <values>0 {endpoint:.17g} {endpoint:.17g}</values>\n        </curve>'''
    text,n=re.subn(r'<curve>\s*<!-- back-filling half of the tunnel -->\s*<name>excavation_curve</name>.*?</curve>',curve,text,flags=re.S); assert n==1
    ts=f'''                    <timesteps>
                        <pair><repeat>{repeat}</repeat><delta_t>{dt:.17g}</delta_t></pair>
                    </timesteps>'''
    text,n=re.subn(r'                    <timesteps>.*?                    </timesteps>',ts,text,flags=re.S); assert n==1
    p.write_text(text,encoding='latin-1')
    return repeat

spec=[
 ('SM_MC_C5M_DX_0p025_EP2p5',5,0.025,2.5),
 ('SM_MC_C5M_DX_0p0125_EP2p5',5,0.0125,2.5),
 ('SM_MC_C5M_DX_0p00625_EP2p5',5,0.00625,2.5),
 ('SM_MC_C5M_DX_0p003125_EP2p5',5,0.003125,2.5),
 ('SM_MC_C5M_DX_0p00625_EP0p25',5,0.00625,0.25),
 ('SM_MC_C5M_DX_0p00625_EP0p30',5,0.00625,0.30),
 ('SM_MC_C10M_DX_0p050_EP2p5',10,0.05,2.5),
]
with (root/'actplas-evidence'/'case-manifest.tsv').open('w') as f:
    f.write('case\tcohesion_mpa\tdt\tdelta_x\tendpoint\trepeat\n')
    for name,c,dt,ep in spec:
        r=build(name,c,dt,ep); f.write(f'{name}\t{c}\t{dt:.17g}\t{dt:.17g}\t{ep:.17g}\t{r}\n')
(root/'actplas-evidence'/'r08-purpose.txt').write_text(
 'R08 tests whether the C=5 MPa failure near excavation-front x≈0.275 m is removable by sub-column front increments, and brackets the critical spatial location with endpoint 0.25 vs 0.30 m. C=10 MPa, dx=0.05 m is retained as a known stable control.\n')
PY

printf 'case\tcohesion_mpa\tdt\tdelta_x\tendpoint\texit_code\tcompleted\tmfront_integration_failure\tfirst_failed_time\tfront_at_failure\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r08.tsv
while IFS=$'\t' read -r name cohesion dt dx endpoint repeat; do
  [[ "$name" == case ]] && continue
  dir="actplas-cases/$name"; outdir="$(pwd)/actplas-evidence/out_${name}"; log="$(pwd)/actplas-evidence/logs/${name}.log"; mkdir -p "$outdir"
  set +e; (cd "$dir" && "$OGS_BIN" -o "$outdir" time_linear_excavation.prj) >"$log" 2>&1; rc=$?; set -e
  grep -q 'Simulation completed' "$log" && completed=yes || completed=no
  grep -q 'MFront: integration failed' "$log" && mf=yes || mf=no
  ft="$(grep -m1 -oE 'failed in time step #[0-9]+ at t = [^ ]+' "$log" | sed -E 's/.* at t = //' || true)"; [[ -n "$ft" ]] || ft='-'
  li="$(grep 'Iteration #[0-9][0-9]* started' "$log" | tail -1 | sed -E 's/.*Iteration #([0-9]+).*/\1/' || true)"; [[ -n "$li" ]] || li='-'
  if [[ "$ft" != '-' ]]; then ff="$(python3 - "$ft" "$endpoint" <<'PY'
import sys
print(min(float(sys.argv[1]),float(sys.argv[2])))
PY
)"; else ff='-'; fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$cohesion" "$dt" "$dx" "$endpoint" "$rc" "$completed" "$mf" "$ft" "$ff" "$li" | tee -a actplas-evidence/sm-r08.tsv
done < actplas-evidence/case-manifest.tsv

printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
for p in actplas-cases/*/time_linear_excavation.prj; do cp "$p" "actplas-evidence/generated-prj/$(basename "$(dirname "$p")").prj"; done
cat actplas-evidence/sm-r08.tsv
