#!/usr/bin/env python3
"""Reduced two-segment/tubbing joint benchmark for the native G5 runtime.

The benchmark intentionally uses a small, auditable joint coupon rather than a
full tunnel ring. Side A and side B of one mechanical-interface pair represent
adjacent precast lining segments. The joint is pre-compressed and then driven
in tangential relative displacement until Coulomb sliding occurs.

The oracle compares the OGS runtime state against the closed-form return map:
  |t_t| = mu |t_n|                       on the Coulomb surface
  plastic_slip = slip - t_t / k_t        (sign-consistent)

A converged later step with no further displacement may be labelled STICK by
the production law while remaining exactly on the previously reached yield
surface. Therefore SLIP must occur at least once, while the final accepted
state is checked by the constitutive invariants rather than by its label alone.

No reference output from another code is used.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

K_N = 1.0e8  # Pa/m
K_T = 2.0e7  # Pa/m
MU = 0.50
INITIAL_NORMAL_GAP = -5.0e-3  # m; compression/closure in the G5 sign convention

RUNTIME_RE = re.compile(
    r"OGS-STR-G5-RUNTIME pair=(?P<pair>\d+) "
    r"gap=(?P<gap>[-+0-9.eE]+) "
    r"slip=(?P<slip>[-+0-9.eE]+) "
    r"normal_traction=(?P<tn>[-+0-9.eE]+) "
    r"tangential_traction=(?P<tt>[-+0-9.eE]+) "
    r"state=(?P<state>[A-Z]+) "
    r"plastic_slip=(?P<ps>[-+0-9.eE]+)"
)


def build_project(source_prj: Path, output_prj: Path) -> None:
    tree = ET.parse(source_prj)
    root = tree.getroot()
    process = root.find("./processes/process")
    if process is None or process.findtext("type") != "SMALL_DEFORMATION":
        raise RuntimeError("expected canonical SMALL_DEFORMATION project")

    mi = ET.SubElement(process, "mechanical_interface")
    material = ET.SubElement(mi, "material")
    ET.SubElement(material, "id").text = "0"
    ET.SubElement(material, "normal_stiffness").text = f"{K_N:.17g}"
    ET.SubElement(material, "tangential_stiffness").text = f"{K_T:.17g}"
    ET.SubElement(material, "friction_coefficient").text = f"{MU:.17g}"

    pair = ET.SubElement(mi, "pair")
    ET.SubElement(pair, "side_a_node_id").text = "0"
    ET.SubElement(pair, "side_b_node_id").text = "2"
    ET.SubElement(pair, "normal").text = "1 0"
    ET.SubElement(pair, "initial_normal_gap").text = f"{INITIAL_NORMAL_GAP:.17g}"
    ET.SubElement(pair, "interface_material_id").text = "0"

    tree.write(output_prj, encoding="utf-8", xml_declaration=True)


def parse_records(log_text: str) -> list[dict[str, float | str]]:
    records: list[dict[str, float | str]] = []
    for match in RUNTIME_RE.finditer(log_text):
        d = match.groupdict()
        records.append(
            {
                "pair": d["pair"],
                "gap": float(d["gap"]),
                "slip": float(d["slip"]),
                "tn": float(d["tn"]),
                "tt": float(d["tt"]),
                "state": d["state"],
                "ps": float(d["ps"]),
            }
        )
    return records


def assert_close(actual: float, expected: float, *, rel: float = 2e-6, abs_: float = 1e-8) -> None:
    if not math.isclose(actual, expected, rel_tol=rel, abs_tol=abs_):
        raise AssertionError(f"actual={actual:.17g}, expected={expected:.17g}")


def validate(records: list[dict[str, float | str]]) -> dict[str, float | str]:
    if not records:
        raise AssertionError("no G5 runtime records found")

    slip_records = [r for r in records if r["state"] == "SLIP"]
    if not slip_records:
        raise AssertionError("joint never reached SLIP")

    # Prove that an actual return-to-Coulomb event occurred, including the
    # plastic history update. This is stronger than merely checking the final
    # state label.
    yielded = slip_records[-1]
    y_tn = float(yielded["tn"])
    y_tt = float(yielded["tt"])
    y_slip = float(yielded["slip"])
    y_ps = float(yielded["ps"])
    yield_limit = MU * abs(y_tn)
    assert_close(abs(y_tt), yield_limit, rel=2e-6, abs_=1e-6)
    assert_close(y_ps, y_slip - y_tt / K_T, rel=2e-6, abs_=1e-8)
    if abs(y_ps) <= 1e-6:
        raise AssertionError("SLIP event did not advance plastic slip")

    # The accepted final state must retain the constitutive history and remain
    # on the Coulomb surface. With unchanged imposed displacement the
    # production return map may call this subsequent state STICK because the
    # trial traction no longer exceeds the yield surface.
    last = records[-1]
    gap = float(last["gap"])
    slip = float(last["slip"])
    tn = float(last["tn"])
    tt = float(last["tt"])
    ps = float(last["ps"])
    if not all(math.isfinite(v) for v in (gap, slip, tn, tt, ps)):
        raise AssertionError("non-finite runtime quantity")
    if abs(slip) <= 1e-6 or abs(ps) <= 1e-6:
        raise AssertionError("benchmark did not retain material tangential/plastic slip")

    expected_limit = MU * abs(tn)
    assert_close(abs(tt), expected_limit, rel=2e-6, abs_=1e-6)
    expected_ps = slip - tt / K_T
    assert_close(ps, expected_ps, rel=2e-6, abs_=1e-8)
    assert_close(ps, y_ps, rel=2e-6, abs_=1e-8)

    friction_utilization = abs(tt) / expected_limit if expected_limit else math.inf
    assert_close(friction_utilization, 1.0, rel=2e-6, abs_=2e-6)

    return {
        **last,
        "yield_state": yielded["state"],
        "friction_limit": expected_limit,
        "friction_utilization": friction_utilization,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ogs", type=Path, required=True)
    parser.add_argument("--source-prj", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    runtime_prj = args.output_dir / "G5TwoSegmentTubbingJoint.prj"
    result_dir = args.output_dir / "results"
    result_dir.mkdir(exist_ok=True)
    build_project(args.source_prj, runtime_prj)

    cmd = [
        str(args.ogs),
        "-o",
        str(result_dir),
        "-m",
        str(args.source_prj.parent),
        str(runtime_prj),
    ]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log_text = proc.stdout
    (args.output_dir / "G5TwoSegmentTubbingJoint.log").write_text(log_text, encoding="utf-8")
    sys.stdout.write(log_text)
    if proc.returncode != 0:
        raise SystemExit(f"OGS returned {proc.returncode}")
    if "OGS_FATAL" in log_text or "terminate called" in log_text:
        raise SystemExit("fatal marker in OGS log")
    if not list(result_dir.glob("*.pvd")):
        raise SystemExit("no PVD output produced")

    final = validate(parse_records(log_text))
    print(
        "G5 two-segment/tubbing joint benchmark: PASS — "
        f"gap={final['gap']:.9g} m, slip={final['slip']:.9g} m, "
        f"normal_traction={final['tn'] / 1e6:.9g} MPa, "
        f"tangential_traction={final['tt'] / 1e6:.9g} MPa, "
        f"mu={MU:.3g}, friction_utilization={final['friction_utilization']:.9g}, "
        f"plastic_slip={final['ps']:.9g} m, "
        f"yield_event={final['yield_state']}, final_state={final['state']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
