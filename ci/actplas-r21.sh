#!/usr/bin/env bash
set -euo pipefail

# ACTPLAS R21: transfer the closed SM methodology to the canonical
# HydroMechanics A2 excavation benchmark. OGS production mechanics are not
# modified. The exact-ref cached runtime is reused; only copied .prj cases are
# changed.

rm -rf ogs-upstream

git clone --filter=blob:none --no-checkout "${OGS_UPSTREAM_URL}" ogs-upstream
cd ogs-upstream
git fetch --depth=1 origin "${OGS_UPSTREAM_SHA}"
git checkout --detach FETCH_HEAD
test "$(git rev-parse HEAD)" = "${OGS_UPSTREAM_SHA}"

OGS_BIN="$(readlink -f ../build/release/bin/ogs)"
test -x "$OGS_BIN"
mkdir -p actplas-evidence/logs actplas-evidence/generated-prj actplas-cases
printf 'ACTPLAS_RUNTIME_CACHE=HIT_BASELINE\n' | tee actplas-evidence/runtime-cache.txt

# 1. Direct canonical elastic HM A2 control.
set +e
(cd Tests/Data/HydroMechanics/A2 && "$OGS_BIN" -o "$(pwd)/../../../actplas-evidence/out_HM_ELASTIC" A2.prj) > actplas-evidence/logs/HM_ELASTIC.log 2>&1
elastic_rc=$?
set -e

# 2. Create minimal MFront MohrCoulombAbboSloan copies. Preserve both HM
# constitutive relation IDs and all hydraulic/media structure. NO_DEACT differs
# from DEACT only by removal of the existing displacement/pressure
# deactivated_subdomains blocks.
python3 - <<'PY'
from pathlib import Path
import re, shutil

root = Path.cwd()
src = root/'Tests/Data/HydroMechanics/A2'
cases = root/'actplas-cases'
ev = root/'actplas-evidence/generated-prj'

relation_tpl = '''            <constitutive_relation id="{mid}">
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

params_tpl = '''        <parameter>
            <name>MC_Cohesion</name><type>Constant</type><value>{cohesion}</value>
        </parameter>
        <parameter>
            <name>MC_FrictionAngle</name><type>Constant</type><value>25</value>
        </parameter>
        <parameter>
            <name>MC_DilatancyAngle</name><type>Constant</type><value>10</value>
        </parameter>
        <parameter>
            <name>MC_TransitionAngle</name><type>Constant</type><value>27</value>
        </parameter>
        <parameter>
            <name>MC_TensionCutOff</name><type>Constant</type><value>1e6</value>
        </parameter>
'''

for cohesion, tag in [(100e6,'C100M'), (20e6,'C20M'), (10e6,'C10M'), (5e6,'C5M')]:
    for mode in ('NO_DEACT','DEACT'):
        dst = cases/f'HM_MC_{tag}_{mode}'
        shutil.copytree(src, dst, dirs_exist_ok=True)
        p = dst/'A2.prj'
        t = p.read_text(encoding='latin-1')

        for mid in ('0','1'):
            pat = rf'\s*<constitutive_relation id="{mid}">.*?</constitutive_relation>'
            t, n = re.subn(pat, '\n'+relation_tpl.format(mid=mid), t, count=1, flags=re.S)
            assert n == 1, (mid, n)

        # Add MC parameters without touching existing E/nu or HM parameters.
        marker = '    </parameters>'
        assert t.count(marker) == 1
        t = t.replace(marker, params_tpl.format(cohesion=f'{cohesion:.0f}') + marker, 1)

        # End after the complete 0.4 m excavation ramp to keep the diagnostic
        # compact while preserving the original early-event stepping.
        t = t.replace('<t_end>2764800</t_end>', '<t_end>20000</t_end>', 1)

        if mode == 'NO_DEACT':
            t, n = re.subn(r'\s*<deactivated_subdomains>.*?</deactivated_subdomains>', '', t, flags=re.S)
            assert n == 2, n  # displacement and pressure blocks

        p.write_text(t, encoding='latin-1')
        (ev/f'HM_MC_{tag}_{mode}.prj').write_text(t, encoding='latin-1')
PY

printf 'case\texit_code\tcompleted\tmfront_failure\tfirst_failed_time\tlast_nonlinear_iteration\n' > actplas-evidence/hm-r21.tsv
printf 'HM_ELASTIC\t%s\t' "$elastic_rc" >> actplas-evidence/hm-r21.tsv
if grep -q 'Simulation completed' actplas-evidence/logs/HM_ELASTIC.log; then printf 'yes\tno\t-\t-\n' >> actplas-evidence/hm-r21.tsv; else printf 'no\tno\t-\t-\n' >> actplas-evidence/hm-r21.tsv; fi

for tag in C100M C20M C10M C5M; do
  for mode in NO_DEACT DEACT; do
    case="HM_MC_${tag}_${mode}"
    dir="actplas-cases/${case}"
    outdir="$(pwd)/actplas-evidence/out_${case}"; mkdir -p "$outdir"
    log="$(pwd)/actplas-evidence/logs/${case}.log"
    set +e
    (cd "$dir" && "$OGS_BIN" -o "$outdir" A2.prj) >"$log" 2>&1
    rc=$?
    set -e
    completed=no; grep -q 'Simulation completed' "$log" && completed=yes || true
    mf=no; grep -q 'MFront: integration failed' "$log" && mf=yes || true
    ft="$(grep -m1 -oE 'failed in time step #[0-9]+ at t = [^ ]+' "$log" | sed -E 's/.* at t = //' || true)"; [[ -n "$ft" ]] || ft='-'
    li="$(grep 'Iteration #[0-9][0-9]* started' "$log" | tail -1 | sed -E 's/.*Iteration #([0-9]+).*/\1/' || true)"; [[ -n "$li" ]] || li='-'
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$case" "$rc" "$completed" "$mf" "$ft" "$li" | tee -a actplas-evidence/hm-r21.tsv
  done
done

cat > actplas-evidence/r21-purpose.txt <<'EOF'
R21 HYDROMECHANICS TRANSFER GATE
SM root cause is closed experimentally: a strongly plastic pre-excavation state plus a discrete deactivation event can produce a non-integrable MFront trial state; an accepted intermediate equilibrium/commit step stabilizes the critical release sequence.
R21 transfers the same controlled method to canonical HydroMechanics/A2. It first runs the untouched upstream elastic HM benchmark, then replaces only constitutive relations id=0 and id=1 with MohrCoulombAbboSloan in copied cases.
For each cohesion level, NO_DEACT and DEACT preserve identical HM media, pressure coupling, initial stress, loads, and time stepping; NO_DEACT removes only the existing displacement/pressure deactivation blocks.
No OGS production mechanics are modified. Canonical exact-ref SHA is preserved.
EOF
printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
cat actplas-evidence/hm-r21.tsv
cat actplas-evidence/r21-purpose.txt
