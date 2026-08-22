#!/usr/bin/env bash
set -euo pipefail

# R16 preserves exact OGS mechanics. It reuses R15 and then proves which
# discrete excavation cells cross the center-of-gravity deactivation threshold
# at x=0.275 m and how they are topologically related to the first failing
# MFront integration point (element 490).
bash ci/actplas-r15.sh

cd ogs-upstream
python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET

mesh = Path('Tests/Data/Mechanics/Excavation/A2.vtu')
root = ET.parse(mesh).getroot()
piece = root.find('.//Piece')
assert piece is not None

pts_da = piece.find('./Points/DataArray')
assert pts_da is not None and pts_da.text
vals = [float(x) for x in pts_da.text.split()]
assert len(vals) % 3 == 0
points = [tuple(vals[i:i+3]) for i in range(0, len(vals), 3)]

cells = piece.find('./Cells')
assert cells is not None
arrays = {a.attrib.get('Name'): a for a in cells.findall('./DataArray')}
conn = [int(x) for x in arrays['connectivity'].text.split()]
offs = [int(x) for x in arrays['offsets'].text.split()]

cell_nodes = []
start = 0
for off in offs:
    cell_nodes.append(conn[start:off])
    start = off

def centroid(ids):
    n = len(ids)
    return tuple(sum(points[j][k] for j in ids)/n for k in range(3))

def bounds(ids):
    xs=[points[j][0] for j in ids]; ys=[points[j][1] for j in ids]
    return min(xs),max(xs),min(ys),max(ys)

# Deactivation in the upstream project applies only to material id 0.  R16's
# original topology diagnostic accidentally bracketed every cell in the mesh,
# including surrounding rock, which made its hard-coded assertion a harness
# error rather than a mechanics finding.
cell_data = piece.find('./CellData')
assert cell_data is not None
material_da = None
for a in cell_data.findall('./DataArray'):
    if a.attrib.get('Name') in ('MaterialIDs', 'MaterialID', 'material_id'):
        material_da = a
        break
assert material_da is not None and material_da.text
material_ids = [int(float(x)) for x in material_da.text.split()]
assert len(material_ids) == len(cell_nodes)

centroids = [centroid(ids) for ids in cell_nodes]
pre = 0.2749
exact = 0.2750
eps = 1e-12
trigger = [
    i for i,c in enumerate(centroids)
    if material_ids[i] == 0 and c[0] > pre+eps and c[0] <= exact+eps
]
assert trigger, 'No material-0 cells cross the x=0.275 deactivation threshold'

failed = 490
assert 0 <= failed < len(cell_nodes)
fc = centroids[failed]
fb = bounds(cell_nodes[failed])
failed_nodes = set(cell_nodes[failed])
rows=[]
for i in trigger:
    shared = sorted(failed_nodes.intersection(cell_nodes[i]))
    rows.append((i, centroids[i], bounds(cell_nodes[i]), shared))

out=Path('actplas-evidence/r16-trigger-topology.txt')
with out.open('w') as f:
    f.write('canonical_ogs_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n')
    f.write('threshold_pre=0.2749\nthreshold_exact=0.2750\n')
    f.write('deactivation_material_id=0\n')
    f.write('newly_deactivated_cells=' + ','.join(map(str,trigger)) + '\n')
    for i,c,b,shared in rows:
        f.write(f'cell={i} centroid=[{c[0]:.12f},{c[1]:.12f},{c[2]:.12f}] bounds=[{b[0]:.12f},{b[1]:.12f},{b[2]:.12f},{b[3]:.12f}] shared_nodes_with_490={shared}\n')
    f.write(f'failed_element=490 material_id={material_ids[failed]} centroid=[{fc[0]:.12f},{fc[1]:.12f},{fc[2]:.12f}] bounds=[{fb[0]:.12f},{fb[1]:.12f},{fb[2]:.12f},{fb[3]:.12f}]\n')
    adjacent=[i for i,_,_,shared in rows if shared]
    f.write('trigger_cells_adjacent_to_failed_element=' + ','.join(map(str,adjacent)) + '\n')
    if adjacent:
        f.write('interpretation=The x=0.275 event removes material-0 excavation cells and at least one of those cells is node-adjacent to failed active element 490. This directly links the discrete deactivation event to the first non-integrable active material point.\n')
    else:
        f.write('interpretation=The x=0.275 material-0 deactivation event is confirmed, but no direct node adjacency to failed element 490 was found; spatial load-path correlation requires the next diagnostic.\n')

print(out.read_text())
PY

cat > actplas-evidence/r16-conclusion.txt <<'EOF'
R16 TOPOLOGY DIAGNOSTIC
R15 proves PRE x=0.2749 passes while EXACT x=0.2750 and POST x=0.2751 fail.
R14 proves the first constitutive failure is in element 490 at xyz=[0.261010,0.266206,0], Newton iteration 2, with MGIS rdt=0.1.
R16 now filters the topology calculation by the actual deactivation material id (0), avoiding the previous harness-only assertion defect, and records the material-0 cells crossing the exact x=0.275 center-of-gravity threshold plus their node adjacency to element 490.
No OGS production mechanics are changed.
EOF
printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
cat actplas-evidence/r16-trigger-topology.txt
cat actplas-evidence/r16-conclusion.txt
