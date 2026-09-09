#!/usr/bin/env python3
"""Native G5-A01 two-domain SmallDeformation acceptance benchmark.

Generates two geometrically adjacent but topologically disconnected quad
segments. Coincident interface coordinates use duplicate bulk nodes and are
coupled only by the production G5 mechanical_interface pairs.
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RUNTIME_RE = re.compile(
    r"OGS-STR-G5-RUNTIME pair=(?P<pair>\d+) "
    r"gap=(?P<gap>[-+0-9.eE]+) "
    r"slip=(?P<slip>[-+0-9.eE]+) "
    r"normal_traction=(?P<tn>[-+0-9.eE]+) "
    r"tangential_traction=(?P<tt>[-+0-9.eE]+) "
    r"state=(?P<state>[A-Z]+) "
    r"plastic_slip=(?P<ps>[-+0-9.eE]+)"
)

POINTS = [
    (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0),
    (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 1.0, 0.0), (1.0, 1.0, 0.0),
]
CELLS = [(0, 1, 2, 3), (4, 5, 6, 7)]
INTERFACE_PAIRS = ((1, 4), (2, 7))


def _data(parent, *, name: str | None, dtype: str, components: int | None, text: str) -> None:
    attrs = {"type": dtype, "format": "ascii"}
    if name is not None:
        attrs["Name"] = name
    if components is not None:
        attrs["NumberOfComponents"] = str(components)
    ET.SubElement(parent, "DataArray", attrs).text = text


def write_domain_vtu(path: Path) -> None:
    vtk = ET.Element("VTKFile", type="UnstructuredGrid", version="0.1", byte_order="LittleEndian")
    ug = ET.SubElement(vtk, "UnstructuredGrid")
    piece = ET.SubElement(ug, "Piece", NumberOfPoints=str(len(POINTS)), NumberOfCells=str(len(CELLS)))
    pts = ET.SubElement(piece, "Points")
    _data(pts, name=None, dtype="Float64", components=3,
          text=" ".join(str(v) for p in POINTS for v in p))
    cells = ET.SubElement(piece, "Cells")
    _data(cells, name="connectivity", dtype="Int64", components=None,
          text=" ".join(str(i) for c in CELLS for i in c))
    _data(cells, name="offsets", dtype="Int64", components=None, text="4 8")
    _data(cells, name="types", dtype="UInt8", components=None, text="9 9")
    cell_data = ET.SubElement(piece, "CellData", Scalars="MaterialIDs")
    _data(cell_data, name="MaterialIDs", dtype="Int32", components=None, text="0 0")
    ET.ElementTree(vtk).write(path, encoding="utf-8", xml_declaration=True)


def write_boundary_vtu(path: Path, bulk_ids: tuple[int, int]) -> None:
    points = [POINTS[i] for i in bulk_ids]
    vtk = ET.Element("VTKFile", type="UnstructuredGrid", version="0.1", byte_order="LittleEndian")
    ug = ET.SubElement(vtk, "UnstructuredGrid")
    piece = ET.SubElement(ug, "Piece", NumberOfPoints="2", NumberOfCells="1")
    pts = ET.SubElement(piece, "Points")
    _data(pts, name=None, dtype="Float64", components=3,
          text=" ".join(str(v) for p in points for v in p))
    cells = ET.SubElement(piece, "Cells")
    _data(cells, name="connectivity", dtype="Int64", components=None, text="0 1")
    _data(cells, name="offsets", dtype="Int64", components=None, text="2")
    _data(cells, name="types", dtype="UInt8", components=None, text="3")
    point_data = ET.SubElement(piece, "PointData")
    # OGS requires the boundary-to-bulk node map to match std::size_t exactly;
    # on the x86_64 exact-ref runner that is VTK UInt64, not signed Int64.
    _data(point_data, name="bulk_node_ids", dtype="UInt64", components=None,
          text=f"{bulk_ids[0]} {bulk_ids[1]}")
    ET.ElementTree(vtk).write(path, encoding="utf-8", xml_declaration=True)


def add_parameter(parent: ET.Element, name: str, value: str, *, values: bool = False) -> None:
    p = ET.SubElement(parent, "parameter")
    ET.SubElement(p, "name").text = name
    ET.SubElement(p, "type").text = "Constant"
    ET.SubElement(p, "values" if values else "value").text = value


def write_project(path: Path) -> None:
    root = ET.Element("OpenGeoSysProject")
    meshes = ET.SubElement(root, "meshes")
    for f in ("g5_a01_two_domain.vtu", "left.vtu", "right.vtu"):
        ET.SubElement(meshes, "mesh").text = f

    processes = ET.SubElement(root, "processes")
    process = ET.SubElement(processes, "process")
    ET.SubElement(process, "name").text = "SD"
    ET.SubElement(process, "type").text = "SMALL_DEFORMATION"
    ET.SubElement(process, "integration_order").text = "2"
    cr = ET.SubElement(process, "constitutive_relation")
    ET.SubElement(cr, "type").text = "LinearElasticIsotropic"
    ET.SubElement(cr, "youngs_modulus").text = "E"
    ET.SubElement(cr, "poissons_ratio").text = "nu"
    ET.SubElement(process, "specific_body_force").text = "0 0"
    pvs = ET.SubElement(process, "process_variables")
    ET.SubElement(pvs, "process_variable").text = "displacement"

    mi = ET.SubElement(process, "mechanical_interface")
    mat = ET.SubElement(mi, "material")
    ET.SubElement(mat, "id").text = "0"
    ET.SubElement(mat, "normal_stiffness").text = "1e14"
    ET.SubElement(mat, "tangential_stiffness").text = "1e14"
    ET.SubElement(mat, "friction_coefficient").text = "1.0"
    for a, b in INTERFACE_PAIRS:
        pair = ET.SubElement(mi, "pair")
        ET.SubElement(pair, "side_a_node_id").text = str(a)
        ET.SubElement(pair, "side_b_node_id").text = str(b)
        ET.SubElement(pair, "normal").text = "1 0"
        ET.SubElement(pair, "initial_normal_gap").text = "-1e-6"
        ET.SubElement(pair, "interface_material_id").text = "0"

    process_variables = ET.SubElement(root, "process_variables")
    pv = ET.SubElement(process_variables, "process_variable")
    ET.SubElement(pv, "name").text = "displacement"
    ET.SubElement(pv, "components").text = "2"
    ET.SubElement(pv, "order").text = "1"
    ET.SubElement(pv, "initial_condition").text = "u0"
    bcs = ET.SubElement(pv, "boundary_conditions")
    for mesh, component, parameter in (
        ("left", "0", "zero"), ("left", "1", "zero"),
        ("right", "0", "compression"), ("right", "1", "zero"),
    ):
        bc = ET.SubElement(bcs, "boundary_condition")
        ET.SubElement(bc, "mesh").text = mesh
        ET.SubElement(bc, "type").text = "Dirichlet"
        ET.SubElement(bc, "component").text = component
        ET.SubElement(bc, "parameter").text = parameter

    params = ET.SubElement(root, "parameters")
    add_parameter(params, "u0", "0 0", values=True)
    add_parameter(params, "zero", "0")
    add_parameter(params, "compression", "-1e-3")
    add_parameter(params, "E", "1e9")
    add_parameter(params, "nu", "0.25")

    media = ET.SubElement(root, "media")
    medium = ET.SubElement(media, "medium", id="0")
    phases = ET.SubElement(medium, "phases")
    phase = ET.SubElement(phases, "phase")
    ET.SubElement(phase, "type").text = "Solid"
    props = ET.SubElement(phase, "properties")
    prop = ET.SubElement(props, "property")
    ET.SubElement(prop, "name").text = "density"
    ET.SubElement(prop, "type").text = "Constant"
    ET.SubElement(prop, "value").text = "1"

    tl = ET.SubElement(root, "time_loop")
    tlps = ET.SubElement(tl, "processes")
    tlp = ET.SubElement(tlps, "process", ref="SD")
    ET.SubElement(tlp, "nonlinear_solver").text = "basic_newton"
    cc = ET.SubElement(tlp, "convergence_criterion")
    ET.SubElement(cc, "type").text = "DeltaX"
    ET.SubElement(cc, "norm_type").text = "NORM2"
    ET.SubElement(cc, "abstol").text = "1e-12"
    ET.SubElement(cc, "reltol").text = "1e-10"
    td = ET.SubElement(tlp, "time_discretization")
    ET.SubElement(td, "type").text = "BackwardEuler"
    ts = ET.SubElement(tlp, "time_stepping")
    ET.SubElement(ts, "type").text = "FixedTimeStepping"
    ET.SubElement(ts, "t_initial").text = "0"
    ET.SubElement(ts, "t_end").text = "1"
    pairs = ET.SubElement(ts, "timesteps")
    tsp = ET.SubElement(pairs, "pair")
    ET.SubElement(tsp, "repeat").text = "1"
    ET.SubElement(tsp, "delta_t").text = "1"
    out = ET.SubElement(tl, "output")
    ET.SubElement(out, "type").text = "VTK"
    ET.SubElement(out, "prefix").text = "G5A01TwoDomain"
    ots = ET.SubElement(out, "timesteps")
    op = ET.SubElement(ots, "pair")
    ET.SubElement(op, "repeat").text = "1"
    ET.SubElement(op, "each_steps").text = "1"
    ET.SubElement(out, "variables")

    nls = ET.SubElement(root, "nonlinear_solvers")
    nl = ET.SubElement(nls, "nonlinear_solver")
    ET.SubElement(nl, "name").text = "basic_newton"
    ET.SubElement(nl, "type").text = "Newton"
    ET.SubElement(nl, "max_iter").text = "12"
    ET.SubElement(nl, "linear_solver").text = "general_linear_solver"
    lss = ET.SubElement(root, "linear_solvers")
    ls = ET.SubElement(lss, "linear_solver")
    ET.SubElement(ls, "name").text = "general_linear_solver"
    eigen = ET.SubElement(ls, "eigen")
    ET.SubElement(eigen, "solver_type").text = "SparseLU"

    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def validate_topology() -> None:
    assert set(CELLS[0]).isdisjoint(CELLS[1])
    for a, b in INTERFACE_PAIRS:
        assert a != b and POINTS[a] == POINTS[b]


def validate_runtime(log_text: str) -> None:
    records = [m.groupdict() for m in RUNTIME_RE.finditer(log_text)]
    if not records:
        raise AssertionError("no G5 runtime diagnostics found")
    seen = {int(r["pair"]) for r in records}
    if not {0, 1}.issubset(seen):
        raise AssertionError(f"both geometric interface pairs were not assembled: seen={sorted(seen)}")
    final = {}
    for r in records:
        final[int(r["pair"])] = r
    for pair_id in (0, 1):
        r = final[pair_id]
        values = [float(r[k]) for k in ("gap", "slip", "tn", "tt", "ps")]
        if not all(math.isfinite(v) for v in values):
            raise AssertionError(f"pair {pair_id}: non-finite runtime diagnostics")
        if float(r["tn"]) >= 0.0:
            raise AssertionError(f"pair {pair_id}: compressive two-domain contact not reached")
    print("G5-A01 native two-domain benchmark: PASS — two disconnected segment cells, "
          "duplicate coincident interface nodes, both interface pairs assembled in compression.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ogs", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    validate_topology()
    write_domain_vtu(args.output_dir / "g5_a01_two_domain.vtu")
    write_boundary_vtu(args.output_dir / "left.vtu", (0, 3))
    write_boundary_vtu(args.output_dir / "right.vtu", (5, 6))
    prj = args.output_dir / "G5A01TwoDomain.prj"
    write_project(prj)
    ET.parse(prj)
    out = args.output_dir / "results"
    out.mkdir(exist_ok=True)
    proc = subprocess.run([str(args.ogs), "-o", str(out), "-m", str(args.output_dir), str(prj)],
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log_text = proc.stdout
    (args.output_dir / "G5A01TwoDomain.log").write_text(log_text, encoding="utf-8")
    sys.stdout.write(log_text)
    if proc.returncode != 0:
        raise SystemExit(f"OGS returned {proc.returncode}")
    if "OGS_FATAL" in log_text or "terminate called" in log_text:
        raise SystemExit("fatal marker in OGS log")
    if not list(out.glob("*.pvd")):
        raise SystemExit("no PVD output produced")
    validate_runtime(log_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
