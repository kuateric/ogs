#!/usr/bin/env bash
set -euo pipefail

# R18 isolates the four R16/R17 trigger cells from every later moving-front
# deactivation event. It first reuses R17 to generate the copied meshes and
# unique MaterialIDs, then removes only the regular material-0 time-curve
# deactivation block from the copied R17 project files. Explicit schedules for
# ids 10..13 remain unchanged. Canonical OGS production mechanics are untouched.
bash ci/actplas-r17.sh

cd ogs-upstream
OGS_BIN="$(readlink -f ../build/release/bin/ogs)"
test -x "$OGS_BIN"

python3 - <<'PY'
from pathlib import Path
import re
root=Path.cwd(); cases=root/'actplas-cases'; ev=root/'actplas-evidence'/'generated-prj'
for tag in ('HOLD','SIMUL','TOP_ONLY','LOWER3','BOTTOM_UP','TOP_DOWN'):
    p=cases/f'SM_MC_C5M_RELEASE_{tag}'/'time_linear_excavation.prj'
    t=p.read_text(encoding='latin-1')
    # Remove exactly the moving-front block acting on material 0. Keep all
    # explicit time-interval blocks for unique ids 10..13.
    pat=r'\s*<deactivated_subdomain>\s*<time_curve>excavation_curve</time_curve>\s*<line_segment>.*?</line_segment>\s*<material_ids>0</material_ids>\s*</deactivated_subdomain>'
    t,n=re.subn(pat,'',t,count=1,flags=re.S)
    assert n==1, (tag,n)
    p.write_text(t,encoding='latin-1')
    (ev/f'SM_MC_C5M_R18_{tag}.prj').write_text(t,encoding='latin-1')
PY

printf 'case\texit_code\tcompleted\tmfront_failure\tmgis_rdt\tfirst_failed_time\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r18.tsv
for tag in HOLD SIMUL TOP_ONLY LOWER3 BOTTOM_UP TOP_DOWN; do
  dir="actplas-cases/SM_MC_C5M_RELEASE_${tag}"
  outdir="$(pwd)/actplas-evidence/out_R18_${tag}"; mkdir -p "$outdir"
  log="$(pwd)/actplas-evidence/logs/R18_${tag}.log"
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
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$tag" "$rc" "$completed" "$mf" "$rdt" "$ft" "$li" | tee -a actplas-evidence/sm-r18.tsv
done

cat > actplas-evidence/r18-purpose.txt <<'EOF'
R18 ISOLATED FOUR-CELL RELEASE DIAGNOSTIC
R17 showed sequencing delays failure, but HOLD still failed later because the regular material-0 moving front continued removing other cells.
R18 removes that moving-front deactivation only in copied project files, leaving all non-trigger material-0 cells active through t_end=0.425.
Thus HOLD is a true no-release control and SIMUL/TOP_ONLY/LOWER3/BOTTOM_UP/TOP_DOWN isolate only cells 30..33.
Canonical OGS production mechanics and exact upstream SHA remain unchanged.
EOF
printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
cat actplas-evidence/sm-r18.tsv
cat actplas-evidence/r18-purpose.txt
