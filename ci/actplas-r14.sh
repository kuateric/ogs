#!/usr/bin/env bash
set -euo pipefail

# R14 reuses the validated R13 reproducer and adds diagnostic-only spatial
# information to the MFront failure message. No OGS mechanics are changed.
cp ci/actplas-r13.sh /tmp/actplas-r14-base.sh
python3 - <<'PY'
from pathlib import Path
p=Path('/tmp/actplas-r14-base.sh')
t=p.read_text()
old='''                std::to_string(dt) + ", error=\\\\\\\"" +\\n                std::string(behaviour_data.error_message ? behaviour_data.error_message : "") +'''
new='''                std::to_string(dt) + ", element_id=" +\\n                (x.getElementID() ? std::to_string(*x.getElementID()) : std::string("NA")) +\\n                ", xyz=[" +\\n                (x.getCoordinates() ? std::to_string((*x.getCoordinates())[0]) : std::string("NA")) + "," +\\n                (x.getCoordinates() ? std::to_string((*x.getCoordinates())[1]) : std::string("NA")) + "," +\\n                (x.getCoordinates() ? std::to_string((*x.getCoordinates())[2]) : std::string("NA")) + "]" +\\n                ", error=\\\\\\\"" +\\n                std::string(behaviour_data.error_message ? behaviour_data.error_message : "") +'''
if old not in t:
    raise SystemExit('R14 patch anchor not found in R13 script')
t=t.replace(old,new,1)
t=t.replace('STATE_DIAG','LOCATION_DIAG')
t=t.replace('sm-r13.tsv','sm-r14.tsv')
t=t.replace('R13 diagnostic-only instrumentation:', 'R14 diagnostic-only instrumentation:')
t=t.replace('r13-purpose.txt','r14-purpose.txt')
p.write_text(t)
PY
bash /tmp/actplas-r14-base.sh

# Freeze a compact location record for the first failure.
msg="$(cat ogs-upstream/actplas-evidence/first-mfront-failure.txt 2>/dev/null || true)"
eid="$(printf '%s' "$msg" | sed -nE 's/.*element_id=([^, ]+).*/\1/p')"
xyz="$(printf '%s' "$msg" | sed -nE 's/.*xyz=\[([^]]+)\].*/\1/p')"
{
  printf 'element_id=%s\n' "${eid:--}"
  printf 'xyz=%s\n' "${xyz:--}"
  printf 'failure_message=%s\n' "$msg"
} > ogs-upstream/actplas-evidence/r14-location.txt
cat ogs-upstream/actplas-evidence/r14-location.txt
