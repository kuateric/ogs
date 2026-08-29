#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# Phase C / Anchor C0 — stress-free installation of an EmbeddedAnchor.
#
# Literature / established-code basis:
# - Abaqus/Standard MODEL CHANGE, ADD=STRAIN FREE: an element installed in an
#   already-deformed configuration takes the current configuration as its new
#   stress-free reference and is fully active immediately. Explicit non-zero
#   initial state is a separate input.
# - FLAC3D structural support installation likewise separates creation of the
#   support from cable pretensioning.
#
# OGS EmbeddedAnchor already exposes `initial_anchor_stress`, which is therefore
# retained as the explicit placement/prestress state.  This patch adds only an
# optional per-anchor `activation_time` cell property.  If that property is not
# present, legacy EmbeddedAnchor behaviour is bit-for-bit preserved.  If it is
# present, the anchor contributes nothing before activation; on its first
# assembly at/after activation it captures the current interpolated bulk
# displacement as its birth reference.  Subsequent strain is measured only from
# displacement increments after birth.  No stiffness scaling/homotopy is used.

header = root / "ProcessLib/BoundaryConditionAndSourceTerm/EmbeddedAnchor.h"
text = header.read_text(encoding="utf-8")
needle = '''    MeshLib::PropertyVector<double> const* anchor_stiffness_ = nullptr;\n'''
replacement = '''    MeshLib::PropertyVector<double> const* anchor_stiffness_ = nullptr;\n\n    // Optional staged-construction placement state.  Absence preserves legacy\n    // behaviour.  Presence makes each anchor inactive before activation_time\n    // and strain-free in the configuration first seen at activation.\n    MeshLib::PropertyVector<double> const* activation_time_ = nullptr;\n    mutable std::vector<Eigen::Vector<double, 2 * GlobalDim>> birth_local_x_;\n    mutable std::vector<bool> birth_reference_captured_;\n'''
if text.count(needle) != 1:
    raise RuntimeError("Could not uniquely locate EmbeddedAnchor member insertion point")
header.write_text(text.replace(needle, replacement, 1), encoding="utf-8")

cpp = root / "ProcessLib/BoundaryConditionAndSourceTerm/EmbeddedAnchor.cpp"
text = cpp.read_text(encoding="utf-8")

needle = '''    std::string_view const anchor_stiffness_string = "anchor_stiffness";\n    anchor_stiffness_ =\n        st_mesh_.getProperties().template getPropertyVector<double>(\n            anchor_stiffness_string);\n}\n'''
replacement = '''    std::string_view const anchor_stiffness_string = "anchor_stiffness";\n    anchor_stiffness_ =\n        st_mesh_.getProperties().template getPropertyVector<double>(\n            anchor_stiffness_string);\n\n    // `activation_time` is deliberately optional.  Existing EmbeddedAnchor\n    // meshes without it keep the pre-Phase-C total-displacement semantics.\n    if (st_mesh_.getProperties().hasPropertyVector("activation_time"))\n    {\n        activation_time_ =\n            st_mesh_.getProperties().template getPropertyVector<double>(\n                "activation_time");\n        birth_local_x_.resize(st_mesh_.getNumberOfElements());\n        birth_reference_captured_.assign(st_mesh_.getNumberOfElements(), false);\n        INFO("EmbeddedAnchor staged-construction lifecycle enabled for {:d} "\n             "anchor element(s).",\n             st_mesh_.getNumberOfElements());\n    }\n}\n'''
if text.count(needle) != 1:
    raise RuntimeError("Could not uniquely locate EmbeddedAnchor constructor tail")
text = text.replace(needle, replacement, 1)

text = text.replace(
    '''void EmbeddedAnchor<GlobalDim>::integrate(const double /*t*/,\n                                          GlobalVector const& x,\n''',
    '''void EmbeddedAnchor<GlobalDim>::integrate(const double t,\n                                          GlobalVector const& x,\n''',
    1,
)
if 'integrate(const double /*t*/' in text:
    raise RuntimeError("EmbeddedAnchor integrate() time argument replacement failed")

needle = '''        auto const anchor_element_id = anchor_element->getID();\n        std::vector<GlobalIndexType> global_indices;\n'''
replacement = '''        auto const anchor_element_id = anchor_element->getID();\n\n        if (activation_time_ && t < (*activation_time_)[anchor_element_id])\n        {\n            continue;\n        }\n\n        std::vector<GlobalIndexType> global_indices;\n'''
if text.count(needle) != 1:
    raise RuntimeError("Could not uniquely locate EmbeddedAnchor activation guard")
text = text.replace(needle, replacement, 1)

needle = '''        getShapeMatricesAndGlobalIndicesAndDisplacements(\n            anchor_element, nodes_per_element, shape_matrices, global_indices,\n            local_x, x, pos);\n\n        auto node_coords = [anchor_element](int const i)\n'''
replacement = '''        getShapeMatricesAndGlobalIndicesAndDisplacements(\n            anchor_element, nodes_per_element, shape_matrices, global_indices,\n            local_x, x, pos);\n\n        // Stress-free birth uses the last available (normally last converged)\n        // bulk displacement as placement reference.  The anchor is born with\n        // full K immediately; only post-birth displacement increments produce\n        // strain.  `initial_anchor_stress` remains an explicit placement state\n        // and is therefore not zeroed here.\n        Eigen::Vector<double, 2 * GlobalDim> constitutive_local_x = local_x;\n        if (activation_time_)\n        {\n            if (!birth_reference_captured_[anchor_element_id])\n            {\n                birth_local_x_[anchor_element_id] = local_x;\n                birth_reference_captured_[anchor_element_id] = true;\n                INFO("EmbeddedAnchor stress-free birth captured for anchor {:d} "\n                     "at physical time t = {:g}; full physical stiffness active.",\n                     anchor_element_id, t);\n            }\n            constitutive_local_x -= birth_local_x_[anchor_element_id];\n        }\n\n        auto node_coords = [anchor_element](int const i)\n'''
if text.count(needle) != 1:
    raise RuntimeError("Could not uniquely locate EmbeddedAnchor birth capture point")
text = text.replace(needle, replacement, 1)

needle = '''        // Displacement in the two nodes.\n        auto u = [&local_x](int const i)\n        { return local_x(nodeLocalIndices<GlobalDim>(i)); };\n'''
replacement = '''        // Displacement relative to the placement configuration for staged\n        // anchors, or total displacement for legacy anchors.\n        auto u = [&constitutive_local_x](int const i)\n        { return constitutive_local_x(nodeLocalIndices<GlobalDim>(i)); };\n'''
if text.count(needle) != 1:
    raise RuntimeError("Could not uniquely locate EmbeddedAnchor displacement view")
text = text.replace(needle, replacement, 1)

cpp.write_text(text, encoding="utf-8")

print("Applied Phase C Anchor C0 stress-free-birth lifecycle")
