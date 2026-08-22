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
import base64
import struct
import xml.etree.ElementTree as ET

mesh = Path('Tests/Data/Mechanics/Excavation/A2.vtu')
root = ET.parse(mesh).getroot()
piece = root.find('.//Piece')
assert piece is not None

# A2.vtu uses VTK XML appended/base64 arrays with UInt64 block headers.
# For base64 AppendedData, VTK's DataArray offsets index the encoded character
# stream (after the leading underscore), not the fully decoded byte stream.
# Each appended block is independently base64 encoded; decode the block bounded
# by the next DataArray offset so padding in one block cannot truncate another.
appended = root.find('.//AppendedData')
assert appended is not None and appended.text
encoded = ''.join(appended.text.split())
assert encoded.startswith('_')
encoded_body = encoded[1:]
byte_order = root.attrib.get('byte_order', 'LittleEndian')
endian = '<' if byte_order == 'LittleEndian' else '>'
header_type = root.attrib.get('header_type', 'UInt32')
header_fmt = {'UInt32': 'I', 'UInt64': 'Q'}[header_type]
header_size = struct.calcsize(endian + header_fmt)

vtk_types = {
    'Float64': 'd', 'Float32': 'f',
    'Int64': 'q', 'UInt64': 'Q',
    'Int32': 'i', 'UInt32': 'I',
    'Int16': 'h', 'UInt16': 'H',
    'Int8': 'b', 'UInt8': 'B',
}

appended_arrays = [
    da for da in piece.findall('.//DataArray')
    if da.attrib.get('format') == 'appended'
]
offsets = sorted(int(da.attrib['offset']) for da in appended_arrays)
next_offset = {
    off: (offsets[i + 1] if i + 1 < len(offsets) else len(encoded_body))
    for i, off in enumerate(offsets)
}

def read_array(da):
    assert da is not None
    fmt = vtk_types[da.attrib['type']]
    if da.attrib.get('format', 'ascii') == 'ascii':
        assert da.text
        conv = float if fmt in ('d', 'f') else int
        return [conv(x) for x in da.text.split()]
    assert da.attrib.get('format') == 'appended'
    offset = int(da.attrib['offset'])
    block_b64 = encoded_body[offset:next_offset[offset]]
    block = base64.b64decode(block_b64)
    assert len(block) >= header_size
    nbytes = struct.unpack_from(endian + header_fmt, block, 0)[0]
    payload = block[header_size:header_size+nbytes]
    assert len(payload) == nbytes, (
        f"VTK appended block truncated at encoded offset {offset}: "
        f"expected {nbytes} payload bytes, got {len(payload)}"
    )
    item_size = struct.calcsize(endian + fmt)
    assert nbytes % item_size == 0
    n = nbytes // item_size
    return list(struct.unpack(endian + str(n) + fmt, payload))

pts_da = piece.find('./Points/DataArray')
vals = [float(x) for x in read_array(pts_da)]
assert len(vals) % 3 == 0
points = [tuple(vals[i:i+3]) for i in range(0, len(vals), 3)]

cells = piece.find('./Cells')
assert cells is not None
arrays = {a.attrib.get('Name'): a for a in cells.findall('./DataArray')}
conn = [int(x) for x in read_array(arrays['connectivity'])]
offs = [int(x) for x in read_array(arrays['offsets'])]

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

# Deactivation in the upstream project applies only to material id 0.
cell_data = piece.find('./CellData')
assert cell_data is not None
material_da = None
for a in cell_data.findall('./DataArray'):
    if a.attrib.get('Name') in ('MaterialIDs', 'MaterialID', 'material_id'):
        material_da = a
        break
assert material_da is not None
material_ids = [int(x) for x in read_array(material_da)]
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
R16 filters the topology calculation by the actual deactivation material id (0) and decodes the upstream A2.vtu appended/base64 blocks according to VTK's encoded-stream offset semantics. It records the material-0 cells crossing the exact x=0.275 center-of-gravity threshold plus their node adjacency to element 490.
No OGS production mechanics are changed.
EOF
printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
cat actplas-evidence/r16-trigger-topology.txt
cat actplas-evidence/r16-conclusion.txt
