#!/usr/bin/env bash
set -euo pipefail

# R15 preserves exact OGS mechanics and reuses the validated R14 diagnostic
# binary. It probes the discrete center-of-gravity deactivation event around
# x=0.275 m for the C=5 MPa reproducer.
bash ci/actplas-r14.sh

cd ogs-upstream
OGS_BIN="$(readlink -f ../build/release/bin/ogs)"
BASE="actplas-cases/SM_MC_C5M_LOCATION_DIAG/time_linear_excavation.prj"
test -x "$OGS_BIN"
test -f "$BASE"

python3 - <<'PY'
from pathlib import Path
import shutil, re
root=Path.cwd()
base=root/'actplas-cases'/'SM_MC_C5M_LOCATION_DIAG'
out=root/'actplas-cases'
evidence=root/'actplas-evidence'/'generated-prj'
for tag,front in [('PRE','0.2749'),('EXACT','0.2750'),('POST','0.2751')]:
    dst=out/f'SM_MC_C5M_FRONT_{tag}'
    shutil.copytree(base,dst,dirs_exist_ok=True)
    p=dst/'time_linear_excavation.prj'
    t=p.read_text(encoding='latin-1')
    # Hold the excavation front just below, exactly at, or just above the
    # critical 0.275 m cell-centre plane. The run is intentionally truncated
    # shortly after the event.
    t,n=re.subn(r'<curve>\s*<name>excavation_curve</name>\s*<coords>0 2\.5 8</coords>\s*<values>0 2\.5 2\.5</values>\s*</curve>',
                f'''<curve>\n            <name>excavation_curve</name>\n            <coords>0 0.275 0.35</coords>\n            <values>0 {front} {front}</values>\n        </curve>''',t,flags=re.S)
    assert n==1
    t=t.replace('<t_end>8</t_end>','<t_end>0.35</t_end>',1)
    t,n=re.subn(r'<timesteps>\s*<pair><repeat>320</repeat><delta_t>0\.025</delta_t></pair>\s*</timesteps>',
                '<timesteps>\n                        <pair><repeat>14</repeat><delta_t>0.025</delta_t></pair>\n                    </timesteps>',t,flags=re.S)
    assert n==1
    p.write_text(t,encoding='latin-1')
    (evidence/f'SM_MC_C5M_FRONT_{tag}.prj').write_text(t,encoding='latin-1')
PY

printf 'case\tfront\texit_code\tcompleted\tmfront_failure\tmgis_rdt\tfirst_failed_time\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r15.tsv
for item in PRE:0.2749 EXACT:0.2750 POST:0.2751; do
  tag="${item%%:*}"; front="${item##*:}"
  dir="actplas-cases/SM_MC_C5M_FRONT_${tag}"
  outdir="$(pwd)/actplas-evidence/out_FRONT_${tag}"; mkdir -p "$outdir"
  log="$(pwd)/actplas-evidence/logs/FRONT_${tag}.log"
  set +e
  (cd "$dir" && "$OGS_BIN" -o "$outdir" time_linear_excavation.prj) >"$log" 2>&1
  rc=$?
  set -e
  completed=no; grep -q 'Simulation completed' "$log" && completed=yes || true
  mf=no; grep -q 'MFront: integration failed' "$log" && mf=yes || true
  msg="$(grep -m1 'MFront: integration failed' "$log" || true)"
  rdt="$(printf '%s' "$msg" | sed -nE 's/.*rdt=([^, ]+).*/\1/p')"; [[ -n "$rdt" ]] || rdt='-'
  ft="$(grep -m1 -oE 'failed in time step #[0-9]+ at t = [^ ]+' "$log" | sed -E 's/.* at t = //' || true)"; [[ -n "$ft" ]] || ft='-'
  li="$(grep 'Iteration #[0-9][0-9]* started' "$log" | tail -1 | sed -E 's/.*Iteration #([0-9]+).*/\1/' || true)"; [[ -n "$li" ]] || li='-'
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$tag" "$front" "$rc" "$completed" "$mf" "$rdt" "$ft" "$li" | tee -a actplas-evidence/sm-r15.tsv
done

cat > actplas-evidence/r15-geometry.txt <<'EOF'
R14 first failed integration point: element_id=490, xyz=[0.261010,0.266206,0].
From the R14 accepted t=0.25 VTU, element 490 spans approximately x=[0.249156,0.313089] m and has centroid x=0.278061 m.
The critical deactivation front is x=0.275 m; therefore the failed integration point is behind the front while the element centroid is just ahead of it.
Canonical OGS DeactivatedSubdomain::isDeactivated() decides line-segment deactivation from the element center of gravity using <= against the moving front plane.
R15 brackets that discrete event with fronts 0.2749, 0.2750, and 0.2751 m.
EOF
printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
cat actplas-evidence/sm-r15.tsv
cat actplas-evidence/r15-geometry.txt
