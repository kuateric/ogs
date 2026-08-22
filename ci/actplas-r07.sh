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

python3 -m pip install --quiet --disable-pip-version-check meshio
mkdir -p actplas-evidence/logs actplas-evidence/generated-prj
printf 'ogs_binary=%s\n' "$OGS_BIN" > actplas-evidence/runtime.txt

python3 - <<'PY'
import pathlib, shutil, re, collections
import meshio

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

def build(name, cohesion, dt):
    repeat = round(8.0/dt)
    assert abs(repeat*dt - 8.0) < 1e-12
    dst = cases/name
    shutil.copytree(src, dst, dirs_exist_ok=True)
    p = dst/'time_linear_excavation.prj'
    text = p.read_text(encoding='latin-1')
    assert text.count(old) == 1
    text = text.replace(old, new)
    marker = '            <specific_body_force>0 0</specific_body_force>'
    assert text.count(marker) == 1
    text = text.replace(marker, marker+'\n            <reference_temperature>T_ref</reference_temperature>')
    params = f'''        <parameter><name>T_ref</name><type>Constant</type><values>293.15</values></parameter>\n        <parameter><name>MC_Cohesion</name><type>Constant</type><value>{cohesion}e6</value></parameter>\n        <parameter><name>MC_FrictionAngle</name><type>Constant</type><value>25</value></parameter>\n        <parameter><name>MC_DilatancyAngle</name><type>Constant</type><value>10</value></parameter>\n        <parameter><name>MC_TransitionAngle</name><type>Constant</type><value>27</value></parameter>\n        <parameter><name>MC_TensionCutOff</name><type>Constant</type><value>1e6</value></parameter>\n'''
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
    # Front velocity = 1 m/s from x=0 to x=2.5. Thus spatial increment equals dt.
    text, n = re.subn(
        r'<curve>\s*<!-- back-filling half of the tunnel -->\s*<name>excavation_curve</name>.*?</curve>',
        '''<curve>\n            <name>excavation_curve</name>\n            <coords>0 2.5 8</coords>\n            <values>0 2.5 2.5</values>\n        </curve>''', text, flags=re.S)
    if n != 1: raise RuntimeError(f'excavation_curve replacement count={n}')
    ts = f'''                    <timesteps>
                        <pair>
                            <repeat>{repeat}</repeat>
                            <delta_t>{dt:.17g}</delta_t>
                        </pair>
                    </timesteps>'''
    text, n = re.subn(r'                    <timesteps>.*?                    </timesteps>', ts, text, flags=re.S)
    if n != 1: raise RuntimeError(f'timesteps replacement count={n}')
    p.write_text(text, encoding='latin-1')
    return repeat

mesh = meshio.read(src/'A2.vtu')
levels = collections.Counter()
for block, mids in zip(mesh.cells, mesh.cell_data.get('MaterialIDs', [])):
    for conn, mid in zip(block.data, mids):
        if int(mid) != 0: continue
        x = float(mesh.points[conn,0].mean())
        if -1e-12 <= x <= 2.5000001:
            levels[round(x,10)] += 1
xs = sorted(levels)
with (root/'actplas-evidence'/'material0-centroid-x.tsv').open('w') as f:
    f.write('centroid_x\tcell_count\n')
    for x,n in sorted(levels.items()): f.write(f'{x:.10g}\t{n}\n')

spec = [
    ('SM_MC_C10M_DX_0p100',10,0.100),
    ('SM_MC_C10M_DX_0p050',10,0.050),
    ('SM_MC_C10M_DX_0p025',10,0.025),
    ('SM_MC_C5M_DX_0p050',5,0.050),
    ('SM_MC_C5M_DX_0p025',5,0.025),
]
manifest=[]
for name,c,dt in spec:
    repeat=build(name,c,dt)
    max_bands=0
    prev=0.0
    t=dt
    while t <= 2.5 + 1e-12:
        front=min(t,2.5)
        count=sum(1 for x in xs if prev < x <= front + 1e-12)
        max_bands=max(max_bands,count)
        prev=front; t += dt
    manifest.append((name,c,repeat,dt,dt,max_bands))
with (root/'actplas-evidence'/'case-manifest.tsv').open('w') as f:
    f.write('case\tcohesion_mpa\trepeat\tdt\tdelta_x\tmax_centroid_bands_per_step\n')
    for row in manifest: f.write('%s\t%s\t%s\t%.17g\t%.17g\t%s\n'%row)
(root/'actplas-evidence'/'generated-prj-summary.txt').write_text(
    'R07 uses a 1 m/s excavation front so delta_x equals dt. It compares exactly one 0.05 m material-0 centroid band per accepted step against two bands (0.10 m) and half-band stepping (0.025 m), for C=10 MPa and C=5 MPa.\n', encoding='utf-8')
PY

printf 'case\tcohesion_mpa\trepeat\tdt\tdelta_x\tmax_centroid_bands_per_step\texit_code\tcompleted\tmfront_integration_failure\tfirst_failed_time\tfront_at_failure\tbands_crossed_in_failed_step\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r07.tsv
while IFS=$'\t' read -r name cohesion repeat dt delta_x maxbands; do
  [[ "$name" == case ]] && continue
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
  if [[ "$fail_time" != '-' ]]; then
    read -r front_fail bands_fail < <(python3 - "$fail_time" "$dt" <<'PY'
import sys
ft=float(sys.argv[1]); dt=float(sys.argv[2]); prev=max(0.0,ft-dt); front=min(ft,2.5)
xs=[0.025+0.05*i for i in range(50)]
bands=sum(1 for x in xs if prev < x <= front+1e-12)
print(front,bands)
PY
)
  else front_fail='-'; bands_fail='-'; fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$cohesion" "$repeat" "$dt" "$delta_x" "$maxbands" "$rc" "$completed" "$mf_fail" "$fail_time" "$front_fail" "$bands_fail" "$last_iter" | tee -a actplas-evidence/sm-r07.tsv
done < actplas-evidence/case-manifest.tsv

printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
for p in actplas-cases/*/time_linear_excavation.prj; do cp "$p" "actplas-evidence/generated-prj/$(basename "$(dirname "$p")").prj"; done
cat actplas-evidence/material0-centroid-x.tsv
cat actplas-evidence/sm-r07.tsv
