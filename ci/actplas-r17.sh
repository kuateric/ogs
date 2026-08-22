#!/usr/bin/env bash
set -euo pipefail

# R17 preserves exact canonical OGS mechanics. It reuses the validated R14
# diagnostic binary, then isolates the four material-0 cells that cross the
# x=0.275 m centre-of-gravity deactivation threshold. Those four cells are
# assigned unique material ids in copied case meshes so they can be released
# simultaneously, individually, or sequentially from the project file.
# No OGS production source is changed by this diagnostic.
bash ci/actplas-r14.sh

cd ogs-upstream
OGS_BIN="$(readlink -f ../build/release/bin/ogs)"
BASE_DIR="actplas-cases/SM_MC_C5M_LOCATION_DIAG"
test -x "$OGS_BIN"
test -f "$BASE_DIR/time_linear_excavation.prj"
test -f "$BASE_DIR/A2.vtu"

python3 - <<'PY'
from pathlib import Path
import base64, copy, re, shutil, struct
import xml.etree.ElementTree as ET

root=Path.cwd(); base=root/'actplas-cases'/'SM_MC_C5M_LOCATION_DIAG'
out=root/'actplas-cases'; ev=root/'actplas-evidence'/'generated-prj'

# Read the upstream VTK appended/base64 mesh and identify the four material-0
# cells crossing the exact x=0.275 m threshold, as proven independently in R16.
mesh=base/'A2.vtu'; tree=ET.parse(mesh); vtkroot=tree.getroot(); piece=vtkroot.find('.//Piece')
appended=vtkroot.find('.//AppendedData')
assert piece is not None and appended is not None and appended.text
encoded=''.join(appended.text.split()); assert encoded.startswith('_'); body=encoded[1:]
endian='<' if vtkroot.attrib.get('byte_order','LittleEndian')=='LittleEndian' else '>'
header_fmt={'UInt32':'I','UInt64':'Q'}[vtkroot.attrib.get('header_type','UInt32')]
header_size=struct.calcsize(endian+header_fmt)
vtk_types={'Float64':'d','Float32':'f','Int64':'q','UInt64':'Q','Int32':'i','UInt32':'I','Int16':'h','UInt16':'H','Int8':'b','UInt8':'B'}
arrays=[a for a in piece.findall('.//DataArray') if a.attrib.get('format')=='appended']
offsets=sorted(int(a.attrib['offset']) for a in arrays)
nextoff={o:(offsets[i+1] if i+1<len(offsets) else len(body)) for i,o in enumerate(offsets)}

def decode(a):
    fmt=vtk_types[a.attrib['type']]
    o=int(a.attrib['offset']); block=base64.b64decode(body[o:nextoff[o]])
    nbytes=struct.unpack_from(endian+header_fmt,block,0)[0]
    payload=block[header_size:header_size+nbytes]
    n=nbytes//struct.calcsize(endian+fmt)
    return list(struct.unpack(endian+str(n)+fmt,payload))

def encode_into(body_text,a,vals):
    fmt=vtk_types[a.attrib['type']]; o=int(a.attrib['offset']); e=nextoff[o]
    payload=struct.pack(endian+str(len(vals))+fmt,*vals)
    block=struct.pack(endian+header_fmt,len(payload))+payload
    enc=base64.b64encode(block).decode('ascii')
    assert len(enc)==e-o, (len(enc),e-o,a.attrib)
    return body_text[:o]+enc+body_text[e:]

pts=[float(x) for x in decode(piece.find('./Points/DataArray'))]
points=[tuple(pts[i:i+3]) for i in range(0,len(pts),3)]
cells=piece.find('./Cells'); ca={a.attrib.get('Name'):a for a in cells.findall('./DataArray')}
conn=[int(x) for x in decode(ca['connectivity'])]; offs=[int(x) for x in decode(ca['offsets'])]
cell_nodes=[]; s=0
for o in offs: cell_nodes.append(conn[s:o]); s=o
centroids=[tuple(sum(points[j][k] for j in ids)/len(ids) for k in range(3)) for ids in cell_nodes]
cell_data=piece.find('./CellData'); mat_da=next(a for a in cell_data.findall('./DataArray') if a.attrib.get('Name')=='MaterialIDs')
material=[int(x) for x in decode(mat_da)]
trigger=[i for i,c in enumerate(centroids) if material[i]==0 and c[0]>0.2749+1e-12 and c[0]<=0.2750+1e-12]
assert len(trigger)==4, trigger
# bottom -> top based on y centroid
trigger=sorted(trigger,key=lambda i:centroids[i][1])
assert trigger==[30,31,32,33], trigger
ids={cell:10+k for k,cell in enumerate(trigger)}

# Patch only MaterialIDs in the copied meshes. Block size is unchanged, so all
# VTK appended offsets remain valid.
def write_mesh(dst):
    tr=ET.parse(mesh); rr=tr.getroot(); pp=rr.find('.//Piece'); ap=rr.find('.//AppendedData')
    enc=''.join(ap.text.split()); bb=enc[1:]
    cd=pp.find('./CellData'); md=next(a for a in cd.findall('./DataArray') if a.attrib.get('Name')=='MaterialIDs')
    vals=material[:]
    for cell,mid in ids.items(): vals[cell]=mid
    # offsets/nextoff are identical to source because XML DataArray layout is unchanged.
    bb=encode_into(bb,md,vals)
    ap.text='_'+bb
    tr.write(dst,encoding='ISO-8859-1',xml_declaration=True)

# All cases keep the regular moving-front deactivation for material 0. The four
# trigger cells (ids 10..13) are controlled by explicit time intervals.
# Times align with the fixed dt=0.025 grid. t_end=0.425 observes recovery after release.
schedules={
    'HOLD': {},
    'SIMUL': {10:0.275,11:0.275,12:0.275,13:0.275},
    'TOP_ONLY': {13:0.275},
    'LOWER3': {10:0.275,11:0.275,12:0.275},
    'BOTTOM_UP': {10:0.275,11:0.300,12:0.325,13:0.350},
    'TOP_DOWN': {13:0.275,12:0.300,11:0.325,10:0.350},
}

for tag,schedule in schedules.items():
    dst=out/f'SM_MC_C5M_RELEASE_{tag}'; shutil.copytree(base,dst,dirs_exist_ok=True)
    write_mesh(dst/'A2.vtu')
    p=dst/'time_linear_excavation.prj'; t=p.read_text(encoding='latin-1')
    t=t.replace('<constitutive_relation id="0,1">','<constitutive_relation id="0,1,10,11,12,13">',1)
    t=t.replace('<medium id="0, 1">','<medium id="0, 1, 10, 11, 12, 13">',1)
    extra=[]
    for mid,ts in sorted(schedule.items(),key=lambda kv:(kv[1],kv[0])):
        extra.append(f'''                <deactivated_subdomain>\n                    <time_interval><start>{ts:.3f}</start><end>8.0</end></time_interval>\n                    <material_ids>{mid}</material_ids>\n                </deactivated_subdomain>''')
    marker='            </deactivated_subdomains>'
    assert t.count(marker)==1
    t=t.replace(marker,('\n'.join(extra)+'\n' if extra else '')+marker,1)
    t=t.replace('<t_end>8</t_end>','<t_end>0.425</t_end>',1)
    t,n=re.subn(r'<timesteps>\s*<pair><repeat>320</repeat><delta_t>0\.025</delta_t></pair>\s*</timesteps>',
                '<timesteps>\n                        <pair><repeat>17</repeat><delta_t>0.025</delta_t></pair>\n                    </timesteps>',t,flags=re.S)
    assert n==1
    p.write_text(t,encoding='latin-1')
    (ev/f'SM_MC_C5M_RELEASE_{tag}.prj').write_text(t,encoding='latin-1')

meta=root/'actplas-evidence'/'r17-trigger-cells.txt'
with meta.open('w') as f:
    f.write('canonical_ogs_sha=adf770974c7ee0435702fe617634d03d17ab7cb8\n')
    for cell in trigger:
        c=centroids[cell]
        f.write(f'cell={cell} unique_material_id={ids[cell]} centroid=[{c[0]:.12f},{c[1]:.12f},{c[2]:.12f}]\n')
    f.write('ordering=bottom_to_top:30,31,32,33\n')
print(meta.read_text())
PY

printf 'case\texit_code\tcompleted\tmfront_failure\tmgis_rdt\tfirst_failed_time\tlast_nonlinear_iteration\n' > actplas-evidence/sm-r17.tsv
for tag in HOLD SIMUL TOP_ONLY LOWER3 BOTTOM_UP TOP_DOWN; do
  dir="actplas-cases/SM_MC_C5M_RELEASE_${tag}"
  outdir="$(pwd)/actplas-evidence/out_RELEASE_${tag}"; mkdir -p "$outdir"
  log="$(pwd)/actplas-evidence/logs/RELEASE_${tag}.log"
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
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$tag" "$rc" "$completed" "$mf" "$rdt" "$ft" "$li" | tee -a actplas-evidence/sm-r17.tsv
done

cat > actplas-evidence/r17-purpose.txt <<'EOF'
R17 SEQUENTIAL RELEASE DIAGNOSTIC
R16 proved that cells 30,31,32,33 cross the x=0.275 material-0 deactivation threshold simultaneously and that top cell 33 is node-adjacent to the first failing active element 490.
R17 changes only copied-case MaterialIDs and .prj deactivation scheduling. Canonical OGS production mechanics remain unchanged.
HOLD keeps the four trigger cells active; SIMUL reproduces simultaneous removal via four unique ids; TOP_ONLY and LOWER3 isolate topology; BOTTOM_UP and TOP_DOWN stagger one cell per accepted 0.025-s step.
The goal is to determine whether sequencing the same four removals stabilizes the strongly plastic C=5 MPa case.
EOF
printf 'ogs_upstream_sha=%s\nogs_checkout_sha=%s\nworkflow_sha=%s\n' "$OGS_UPSTREAM_SHA" "$(git rev-parse HEAD)" "${GITHUB_SHA:-unknown}" > actplas-evidence/provenance.txt
cat actplas-evidence/sm-r17.tsv
cat actplas-evidence/r17-purpose.txt
