#!/usr/bin/env bash
set -euo pipefail

# ACTPLAS R22: transfer the closed SM/HM diagnostic method to the canonical
# ThermoRichardsMechanics A2 excavation benchmark. No OGS production mechanics
# are modified. The exact-ref cached runtime is reused; only copied .prj cases
# are changed.

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

# 1. Direct canonical elastic TRM A2 control.
set +e
(cd Tests/Data/ThermoRichardsMechanics/A2 && "$OGS_BIN" -o "$(pwd)/../../../actplas-evidence/out_TRM_ELASTIC" A2.prj) > actplas-evidence/logs/TRM_ELASTIC.log 2>&1
elastic_rc=$?
set -e

# 2. Create minimal MFront MohrCoulombAbboSloan copies. Preserve the single
# canonical constitutive relation covering material IDs 0 and 1 and all TRM
# thermal/hydraulic/media structure. NO_DEACT differs from DEACT only by
# removal of the existing displacement/pressure/temperature deactivation
# blocks.
python3 - <<'PY'
from pathlib import Path
import re, shutil

root = Path.cwd()
src = root/'Tests/Data/ThermoRichardsMechanics/A2'
cases = root/'actplas-cases'
ev = root/'actplas-evidence/generated-prj'

relation = '''            <constitutive_relation id="0,1">
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
        dst = cases/f'TRM_MC_{tag}_{mode}'
        shutil.copytree(src, dst, dirs_exist_ok=True)
        p = dst/'A2.prj'
        t = p.read_text(encoding='latin-1')

        pat = r'\s*<constitutive_relation id="0,1">.*?</constitutive_relation>'
        t, n = re.subn(pat, '\n'+relation, t, count=1, flags=re.S)
        assert n == 1, n

        marker = '    </parameters>'
        assert t.count(marker) == 1
        t = t.replace(marker, params_tpl.format(cohesion=f'{cohesion:.0f}') + marker, 1)

        # End after the complete 0.4 m excavation ramp to keep the transfer
        # diagnostic compact while retaining the canonical early-event steps.
        t = t.replace('<t_end>2764800</t_end>', '<t_end>20000</t_end>', 1)

        if mode == 'NO_DEACT':
            t, n = re.subn(r'\s*<deactivated_subdomains>.*?</deactivated_subdomains>', '', t, flags=re.S)
            assert n == 3, n  # displacement, pressure and temperature blocks

        p.write_text(t, encoding='latin-1')
        (ev/f'TRM_MC_{tag}_{mode}.prj').write_text(t, encoding='latin-1')
PY

printf 'case\texit_code\tcompleted\tmfront_failure\tfirst_failed_time\tlast_nonlinear_iteration\n' > actplas-evidence/trm-r22.tsv
printf 'TRM_ELASTIC\t%s\t' "$elastic_rc" >> actplas-evidence/trm-r22.tsv
if grep -q 'Simulation completed' actplas-evidence/logs/TRM_ELASTIC.log; then printf 'yes\tno\t-\t-\n' >> actplas-evidence/trm-r22.tsv; else printf 'no\tno\t-\t-\n' >> actplas-evidence/trm-r22.tsv; fi

for tag in C100M C20M C10M C5M; do
  for mode in NO_DEACT DEACT; do
    case="TRM_MC_${tag}_${mode}"
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
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$case" "$rc" "$completed" "$mf" "$ft" "$li" | tee -a actplas-evidence/trm-r22.tsv
  done
done

cat > actplas-evidence/r22-purpose.txt <<'EOF'
R22 THERMO-RICHARDS-MECHANICS TRANSFER GATE
SM root cause is experimentally closed: strongly plastic excavation state history plus a discrete deactivation event can produce a non-integrable MFront trial state; an accepted intermediate equilibrium/commit step stabilizes the critical release sequence.
R21 HM transfer showed the canonical HydroMechanics/A2 benchmark completed for elastic and all tested MohrCoulombAbboSloan cohesion levels (100/20/10/5 MPa), both with and without its canonical displacement/pressure deactivation.
R22 transfers the same controlled method to canonical ThermoRichardsMechanics/A2. It first runs the untouched upstream elastic TRM benchmark, then replaces only the constitutive relation id=0,1 with MohrCoulombAbboSloan in copied cases.
For each cohesion level, NO_DEACT and DEACT preserve identical TRM media, pressure/temperature coupling, initial stress, loads, and time stepping; NO_DEACT removes only the existing displacement/pressure/temperature deactivation blocks.
No OGS production mechanics are modified. Canonical exact-ref SHA is preserved.
EOF
printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
cat actplas-evidence/trm-r22.tsv
cat actplas-evidence/r22-purpose.txt
