#!/usr/bin/env python3
from pathlib import Path
import subprocess

# TH2M-T3 derives an authoritative loaded construction-equilibrium runtime from
# the already-authoritative T2D MFront/MGIS fresh-birth runtime. It changes only
# the CI fixture: gravity is restored and the mechanically over-constrained
# all-node zero-displacement boundary is replaced by minimal rigid-body supports.
# No stiffness/residual/material homotopy and no additional construction time
# step are introduced.

subprocess.run(
    ['python3', 'scripts/prepare-ogs-staged-construction-th2m-t2d.py'],
    check=True,
)

runtime = Path('/tmp/run-th2m-t2d.sh')
if not runtime.is_file():
    raise RuntimeError('TH2M-T3 expected generated T2D runtime is missing')
src = runtime.read_text(encoding='utf-8')

src = src.replace('TH2M-T2D', 'TH2M-T3').replace('th2m-t2d', 'th2m-t3').replace('TH2M_T2D', 'TH2M_T3')

load_anchor = "proc.find('specific_body_force').text = '0 0'"
if src.count(load_anchor) != 1:
    raise RuntimeError('TH2M-T3 specific-body-force anchor changed')
src = src.replace(load_anchor, "proc.find('specific_body_force').text = '0 -9.81'", 1)

identity_end = "p.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')\nPY\n\npython3 - <<'PY'\nfrom pathlib import Path\nimport xml.etree.ElementTree as ET\n"
support_writer = r"""p.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
PY

python3 - <<'PY'
from pathlib import Path

# Boundary-to-bulk correspondence in OGS is authoritative through
# bulk_node_ids. Do not scrape coordinates from domain.vtu here: the canonical
# fixture and createQuadraticMesh legitimately use VTK appended encoding, for
# which Point DataArray text is empty. Point coordinates in these one-node
# Dirichlet submeshes are therefore only geometric metadata; the bulk IDs below
# select the actual mechanics DOFs. Distinct coordinates keep the point meshes
# well-formed without changing the physical bulk geometry or operator.
def write_point_mesh(path, bulk_id, xyz):
    Path(path).write_text(f'''<?xml version="1.0"?>
<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">
  <UnstructuredGrid>
    <Piece NumberOfPoints="1" NumberOfCells="1">
      <PointData><DataArray type="UInt64" Name="bulk_node_ids" format="ascii">{bulk_id}</DataArray></PointData>
      <CellData></CellData>
      <Points><DataArray type="Float64" NumberOfComponents="3" format="ascii">{xyz[0]} {xyz[1]} {xyz[2]}</DataArray></Points>
      <Cells>
        <DataArray type="Int64" Name="connectivity" format="ascii">0</DataArray>
        <DataArray type="Int64" Name="offsets" format="ascii">1</DataArray>
        <DataArray type="UInt8" Name="types" format="ascii">1</DataArray>
      </Cells>
    </Piece>
  </UnstructuredGrid>
</VTKFile>
''', encoding='utf-8')

write_point_mesh('th2m-t3-case/support0.vtu', 0, (0.0, 0.0, 0.0))
write_point_mesh('th2m-t3-case/support1.vtu', 1, (1.0, 0.0, 0.0))
PY

python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET
"""
if src.count(identity_end) != 1:
    raise RuntimeError('TH2M-T3 support-mesh injection anchor changed')
src = src.replace(identity_end, support_writer, 1)

mesh_anchor = "ET.SubElement(meshes, 'mesh').text = 'domain.vtu'"
mesh_replacement = """ET.SubElement(meshes, 'mesh').text = 'domain.vtu'
ET.SubElement(meshes, 'mesh').text = 'support0.vtu'
ET.SubElement(meshes, 'mesh').text = 'support1.vtu'"""
if src.count(mesh_anchor) != 1:
    raise RuntimeError('TH2M-T3 mesh-list anchor changed')
src = src.replace(mesh_anchor, mesh_replacement, 1)

bc_block = """# Keep mechanics nonsingular with full-domain zero displacement. The fixture mesh
# carries an identity bulk_node_ids map, satisfying OGS boundary-to-bulk mapping.
# Local TH2M contributions are still assembled before global Dirichlet elimination
# and are captured by the instrumented assembler trace.
bcs = ET.SubElement(variables['displacement'], 'boundary_conditions')
for comp in ('0', '1'):
    bc = ET.SubElement(bcs, 'boundary_condition')
    ET.SubElement(bc, 'mesh').text = 'domain'
    ET.SubElement(bc, 'type').text = 'Dirichlet'
    ET.SubElement(bc, 'component').text = comp
    ET.SubElement(bc, 'parameter').text = 'zero'
"""
bc_replacement = """# Minimal rigid-body supports for a genuinely loaded 2-D equilibrium problem.
bcs = ET.SubElement(variables['displacement'], 'boundary_conditions')
for mesh_name, components in (('support0', ('0', '1')), ('support1', ('1',))):
    for comp in components:
        bc = ET.SubElement(bcs, 'boundary_condition')
        ET.SubElement(bc, 'mesh').text = mesh_name
        ET.SubElement(bc, 'type').text = 'Dirichlet'
        ET.SubElement(bc, 'component').text = comp
        ET.SubElement(bc, 'parameter').text = 'zero'
"""
if src.count(bc_block) != 1:
    raise RuntimeError('TH2M-T3 displacement-BC anchor changed')
src = src.replace(bc_block, bc_replacement, 1)

evidence_anchor = "Path('../th2m-t3-evidence.txt').write_text("
evidence_insert = r"""import xml.etree.ElementTree as ET
import math
pvd_files = list(Path('th2m-t3-out').glob('*.pvd'))
if not pvd_files:
    raise RuntimeError('TH2M-T3 PVD output missing')
pvd = ET.parse(pvd_files[0]).getroot()
datasets = []
for ds in pvd.findall('.//DataSet'):
    try:
        t = float(ds.attrib.get('timestep', 'nan'))
    except ValueError:
        continue
    fn = ds.attrib.get('file')
    if fn:
        datasets.append((t, Path('th2m-t3-out') / fn))

def displacement_vectors(vtu):
    root = ET.parse(vtu).getroot()
    for arr in root.findall('.//PointData/DataArray'):
        if arr.attrib.get('Name') == 'displacement':
            ncomp = int(arr.attrib.get('NumberOfComponents', '1'))
            vals = [float(x) for x in (arr.text or '').split()]
            return [vals[i:i+ncomp] for i in range(0, len(vals), ncomp)]
    raise RuntimeError(f'displacement array missing in {vtu}')

def state_at(target):
    candidates = [(abs(t-target), p) for t, p in datasets if p.exists()]
    if not candidates:
        raise RuntimeError(f'no TH2M-T3 output near t={target}')
    d, p = min(candidates)
    if d > 1e-9:
        raise RuntimeError(f'no exact TH2M-T3 output at t={target}; nearest delta={d}')
    return displacement_vectors(p)

u1 = state_at(1.0)
u2 = state_at(2.0)
if len(u1) != len(u2):
    raise RuntimeError('TH2M-T3 displacement vector size changed')
correction = max(
    math.sqrt(sum((a-b)**2 for a, b in zip(v1, v2)))
    for v1, v2 in zip(u1, u2)
)
if not correction > 1e-14:
    raise RuntimeError(f'no measurable loaded construction-equilibrium correction: {correction}')
Path('../th2m-t3-evidence.txt').write_text(
"""
if src.count(evidence_anchor) != 1:
    raise RuntimeError('TH2M-T3 evidence anchor changed')
src = src.replace(evidence_anchor, evidence_insert, 1)

field_anchor = """    'physical_stiffness=full_from_first_active_assembly\\n'
"""
field_insert = """    f'loaded_equilibrium_displacement_correction={correction:.17g}\\n'
    'equilibrium_target_time=reactivation_target_t2\\n'
    'construction_pseudo_time=false\\n'
    'physical_body_force=0_-9.81\\n'
    'mechanical_supports=minimal_rigid_body_only\\n'
    'physical_stiffness=full_from_first_active_assembly\\n'
"""
if src.count(field_anchor) != 1:
    raise RuntimeError('TH2M-T3 evidence-field anchor changed')
src = src.replace(field_anchor, field_insert, 1)

Path('/tmp/run-th2m-t3.sh').write_text(src, encoding='utf-8')
