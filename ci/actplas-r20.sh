#!/usr/bin/env bash
set -euo pipefail

# R20 starts from the validated R19 preconditioned state. R19 proved that with
# the real excavation history frozen at x=0.25 m, simultaneous release of
# trigger cells 30..33 fails, TOP_ONLY fails, LOWER3 passes, and full BOTTOM_UP
# sequencing passes. R20 varies only the delay between releasing the lower
# three cells and the critical crown cell 33 (MaterialID 13).
# Canonical OGS production mechanics remain unchanged.
bash ci/actplas-r19.sh

cd ogs-upstream
OGS_BIN="$(readlink -f ../build/release/bin/ogs)"
test -x "$OGS_BIN"

python3 - <<'PY'
from pathlib import Path
import re, shutil
root=Path.cwd(); cases=root/'actplas-cases'; ev=root/'actplas-evidence'/'generated-prj'
base=cases/'SM_MC_C5M_RELEASE_HOLD'
assert (base/'time_linear_excavation.prj').is_file()

# lower cells 30..32 correspond to MaterialIDs 10..12. They are all released
# at the critical event t=0.275. Crown cell 33 / MaterialID 13 is then released
# after 0,1,2,3,4 accepted dt=0.025 steps, or held indefinitely.
variants={
    'CROWN_D0':0.275,
    'CROWN_D1':0.300,
    'CROWN_D2':0.325,
    'CROWN_D3':0.350,
    'CROWN_D4':0.375,
    'CROWN_HOLD':None,
}
for tag,top_time in variants.items():
    dst=cases/f'SM_MC_C5M_R20_{tag}'
    shutil.copytree(base,dst,dirs_exist_ok=True)
    p=dst/'time_linear_excavation.prj'; t=p.read_text(encoding='latin-1')
    # The R19 HOLD project contains only the regular material-0 front, frozen
    # at x=0.25. Add explicit release schedules for the four unique trigger ids.
    extra=[]
    for mid in (10,11,12):
        extra.append(f'''                <deactivated_subdomain>\n                    <time_interval><start>0.275</start><end>8.0</end></time_interval>\n                    <material_ids>{mid}</material_ids>\n                </deactivated_subdomain>''')
    if top_time is not None:
        extra.append(f'''                <deactivated_subdomain>\n                    <time_interval><start>{top_time:.3f}</start><end>8.0</end></time_interval>\n                    <material_ids>13</material_ids>\n                </deactivated_subdomain>''')
    marker='            </deactivated_subdomains>'
    assert t.count(marker)==1
    t=t.replace(marker,'\n'.join(extra)+'\n'+marker,1)
    # Observe at least two accepted steps after the latest possible crown release.
    t=t.replace('<t_end>0.425</t_end>','<t_end>0.425</t_end>',1)
    p.write_text(t,encoding='latin-1')
    (ev/f'SM_MC_C5M_R20_{tag}.prj').write_text(t,encoding='latin-1')
PY

printf 'case\texit_code\tcompleted\tmfront_failure\tmgis_rdt\tfirst_failed_time\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r20.tsv
for tag in CROWN_D0 CROWN_D1 CROWN_D2 CROWN_D3 CROWN_D4 CROWN_HOLD; do
  dir="actplas-cases/SM_MC_C5M_R20_${tag}"
  outdir="$(pwd)/actplas-evidence/out_R20_${tag}"; mkdir -p "$outdir"
  log="$(pwd)/actplas-evidence/logs/R20_${tag}.log"
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
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$tag" "$rc" "$completed" "$mf" "$rdt" "$ft" "$li" | tee -a actplas-evidence/sm-r20.tsv
done

cat > actplas-evidence/r20-purpose.txt <<'EOF'
R20 CROWN-CELL RELAXATION DIAGNOSTIC
R19 established at identical pre-event excavation history that SIMUL and TOP_ONLY fail, LOWER3 passes, and complete BOTTOM_UP sequencing passes.
R20 releases lower trigger cells 30..32 simultaneously at t=0.275, then releases crown cell 33 after 0..4 accepted dt=0.025 steps, with CROWN_HOLD as control.
This isolates whether an accepted equilibrium/plastic-state update after removing the lower cells is sufficient to make subsequent crown-cell removal integrable.
Canonical OGS production mechanics and exact upstream SHA remain unchanged.
EOF
printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
cat actplas-evidence/sm-r20.tsv
cat actplas-evidence/r20-purpose.txt
