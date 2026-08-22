#!/usr/bin/env bash
set -euo pipefail

# R19 restores the real pre-event excavation history up to x=0.25 m, then
# freezes the regular material-0 moving front before the critical x=0.275 m
# event. The four R16 trigger cells 30..33 retain their unique MaterialIDs and
# are released only by the explicit R17 schedules. This isolates whether the
# R18 all-PASS result was caused by removing the pre-existing excavation state.
# Canonical OGS production mechanics remain unchanged.
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
    # Keep the regular moving-front deactivation, but force the excavation
    # curve to reproduce x=t only until x=0.25 m and then hold x=0.25 m.
    # Thus material-0 cells with centroid <=0.25 have the same pre-event
    # removal history while no additional ordinary material-0 cells are
    # removed at/after the explicit trigger-cell releases.
    pat=r'(<curve>\s*<name>excavation_curve</name>\s*<coords>).*?(</coords>\s*<values>).*?(</values>\s*</curve>)'
    repl=r'\g<1>0 0.25 0.425\g<2>0 0.25 0.25\g<3>'
    t,n=re.subn(pat,repl,t,count=1,flags=re.S)
    assert n==1, (tag,n)
    p.write_text(t,encoding='latin-1')
    (ev/f'SM_MC_C5M_R19_{tag}.prj').write_text(t,encoding='latin-1')
PY

printf 'case\texit_code\tcompleted\tmfront_failure\tmgis_rdt\tfirst_failed_time\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r19.tsv
for tag in HOLD SIMUL TOP_ONLY LOWER3 BOTTOM_UP TOP_DOWN; do
  dir="actplas-cases/SM_MC_C5M_RELEASE_${tag}"
  outdir="$(pwd)/actplas-evidence/out_R19_${tag}"; mkdir -p "$outdir"
  log="$(pwd)/actplas-evidence/logs/R19_${tag}.log"
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
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$tag" "$rc" "$completed" "$mf" "$rdt" "$ft" "$li" | tee -a actplas-evidence/sm-r19.tsv
done

cat > actplas-evidence/r19-purpose.txt <<'EOF'
R19 PRECONDITIONED FOUR-CELL RELEASE DIAGNOSTIC
R18 proved that removing cells 30..33 in an otherwise unexcavated C=5 MPa model is stable even for simultaneous release.
R19 restores the real progressive material-0 excavation history only up to x=0.25 m, then freezes that moving front.
The four trigger cells 30..33 remain controlled exclusively by the explicit HOLD/SIMUL/TOP_ONLY/LOWER3/BOTTOM_UP/TOP_DOWN schedules.
This tests whether the critical failure requires the pre-existing excavation/plastic state rather than the four-cell release in isolation.
Canonical OGS production mechanics and exact upstream SHA remain unchanged.
EOF
printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
cat actplas-evidence/sm-r19.tsv
cat actplas-evidence/r19-purpose.txt
