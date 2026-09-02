#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# Phase C / Anchor C0 — stress-free installation of an EmbeddedAnchor.
#
# Established-code basis:
# - Abaqus/Standard MODEL CHANGE, ADD=STRAIN FREE: an element installed in an
#   already-deformed configuration takes the current configuration as its new
#   stress-free reference and is fully active immediately.
# - PLAXIS staged construction activates anchors in a construction phase and
#   treats prestress as a separate phase operation/state.
# - FLAC3D structural support installation likewise separates structural
#   support creation from cable pretensioning and then solves disequilibrium.
#
# The important OGS lifecycle rule is stronger than "first assembly after
# activation": Process::preTimestep() is called before assembly of the new
# timestep and receives the converged solution carried from the preceding
# timestep (or the initialized solution at the first step).  Source terms did
# not previously receive that lifecycle event.  This patch therefore adds a
# default no-op SourceTermBase::preTimestep() hook and forwards it from Process.
# EmbeddedAnchor uses that hook to freeze the placement/reference configuration
# BEFORE any Newton assembly at the activation time.  No trial iterate can
# become the birth reference.
#
# If `activation_time` is absent, legacy EmbeddedAnchor behaviour is preserved.
# If present, the anchor contributes nothing before activation; at preTimestep
# of the activation phase it freezes the last converged/current initialized
# bulk configuration as the natural configuration.  Full anchor stiffness is
# active immediately at birth.  `initial_anchor_stress` remains the explicit
# placement/prestress state.  No stiffness/residual/material homotopy is used.


def replace_once(path: Path, needle: str, replacement: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(needle) != 1:
        raise RuntimeError(f"Could not uniquely locate {label} in {path}")
    path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Generic, backwards-compatible source-term lifecycle hook.
# ---------------------------------------------------------------------------
source_term_h = root / "ProcessLib/BoundaryConditionAndSourceTerm/SourceTerm.h"
replace_once(
    source_term_h,
    '''    virtual void integrate(const double t, GlobalVector const& x,\n                           GlobalVector& b, GlobalMatrix* jac) const = 0;\n\n    virtual ~SourceTermBase() = default;\n''',
    '''    virtual void integrate(const double t, GlobalVector const& x,\n                           GlobalVector& b, GlobalMatrix* jac) const = 0;\n\n    /// Lifecycle notification before assembly of a new timestep.  The default\n    /// is deliberately a no-op so all existing source terms remain unchanged.\n    virtual void preTimestep(double const /*t*/, GlobalVector const& /*x*/) {}\n\n    virtual ~SourceTermBase() = default;\n''',
    "SourceTermBase preTimestep hook",
)

collection_h = root / "ProcessLib/BoundaryConditionAndSourceTerm/SourceTermCollection.h"
replace_once(
    collection_h,
    '''    void integrate(const double t, GlobalVector const& x, GlobalVector& b,\n                   GlobalMatrix* jac) const;\n\n    void addSourceTermsForProcessVariables(\n''',
    '''    void integrate(const double t, GlobalVector const& x, GlobalVector& b,\n                   GlobalMatrix* jac) const;\n\n    void preTimestep(double const t, GlobalVector const& x) const;\n\n    void addSourceTermsForProcessVariables(\n''',
    "SourceTermCollection preTimestep declaration",
)

collection_cpp = root / "ProcessLib/BoundaryConditionAndSourceTerm/SourceTermCollection.cpp"
replace_once(
    collection_cpp,
    '''void SourceTermCollection::integrate(const double t, GlobalVector const& x,\n                                     GlobalVector& b, GlobalMatrix* jac) const\n{\n    // For parallel computing with DDC, a partition may not have source term\n    // but a nullptr is assigned to its element in _source_terms.\n    auto non_nullptr = [](std::unique_ptr<SourceTermBase> const& st)\n    { return st != nullptr; };\n\n    for (auto const& st : _source_terms | ranges::views::filter(non_nullptr))\n    {\n        st->integrate(t, x, b, jac);\n    }\n}\n\n}  // namespace ProcessLib\n''',
    '''void SourceTermCollection::integrate(const double t, GlobalVector const& x,\n                                     GlobalVector& b, GlobalMatrix* jac) const\n{\n    // For parallel computing with DDC, a partition may not have source term\n    // but a nullptr is assigned to its element in _source_terms.\n    auto non_nullptr = [](std::unique_ptr<SourceTermBase> const& st)\n    { return st != nullptr; };\n\n    for (auto const& st : _source_terms | ranges::views::filter(non_nullptr))\n    {\n        st->integrate(t, x, b, jac);\n    }\n}\n\nvoid SourceTermCollection::preTimestep(double const t,\n                                       GlobalVector const& x) const\n{\n    auto non_nullptr = [](std::unique_ptr<SourceTermBase> const& st)\n    { return st != nullptr; };\n\n    for (auto const& st : _source_terms | ranges::views::filter(non_nullptr))\n    {\n        st->preTimestep(t, x);\n    }\n}\n\n}  // namespace ProcessLib\n''',
    "SourceTermCollection preTimestep forwarding",
)

process_cpp = root / "ProcessLib/Process.cpp"
replace_once(
    process_cpp,
    '''    for (auto* const solution : x)\n    {\n        MathLib::LinAlg::setLocalAccessibleVector(*solution);\n    }\n    preTimestepConcreteProcess(x, t, delta_t, process_id);\n\n    _boundary_conditions[process_id].preTimestep(t, x, process_id);\n''',
    '''    for (auto* const solution : x)\n    {\n        MathLib::LinAlg::setLocalAccessibleVector(*solution);\n    }\n\n    // Source terms see the carried, last-converged solution before any\n    // assembly/Newton update of this timestep.\n    _source_term_collections[process_id].preTimestep(t, *x[process_id]);\n\n    preTimestepConcreteProcess(x, t, delta_t, process_id);\n\n    _boundary_conditions[process_id].preTimestep(t, x, process_id);\n''',
    "Process source-term preTimestep forwarding",
)

# ---------------------------------------------------------------------------
# EmbeddedAnchor placement state.
# ---------------------------------------------------------------------------
header = root / "ProcessLib/BoundaryConditionAndSourceTerm/EmbeddedAnchor.h"
replace_once(
    header,
    '''    void integrate(const double t, GlobalVector const& x, GlobalVector& b,\n                   GlobalMatrix* jac) const override;\n\nprivate:\n''',
    '''    void preTimestep(double const t, GlobalVector const& x) override;\n\n    void integrate(const double t, GlobalVector const& x, GlobalVector& b,\n                   GlobalMatrix* jac) const override;\n\nprivate:\n''',
    "EmbeddedAnchor preTimestep override",
)
replace_once(
    header,
    '''    MeshLib::PropertyVector<double> const* anchor_stiffness_ = nullptr;\n''',
    '''    MeshLib::PropertyVector<double> const* anchor_stiffness_ = nullptr;\n\n    // Optional staged-construction placement state. Absence preserves legacy\n    // behaviour. Presence freezes each anchor's stress-free reference at the\n    // preTimestep lifecycle boundary when it becomes active.\n    MeshLib::PropertyVector<double> const* activation_time_ = nullptr;\n    std::vector<Eigen::Vector<double, 2 * GlobalDim>> birth_local_x_;\n    std::vector<bool> birth_reference_captured_;\n''',
    "EmbeddedAnchor placement-state members",
)

cpp = root / "ProcessLib/BoundaryConditionAndSourceTerm/EmbeddedAnchor.cpp"
replace_once(
    cpp,
    '''    std::string_view const anchor_stiffness_string = "anchor_stiffness";\n    anchor_stiffness_ =\n        st_mesh_.getProperties().template getPropertyVector<double>(\n            anchor_stiffness_string);\n}\n''',
    '''    std::string_view const anchor_stiffness_string = "anchor_stiffness";\n    anchor_stiffness_ =\n        st_mesh_.getProperties().template getPropertyVector<double>(\n            anchor_stiffness_string);\n\n    if (st_mesh_.getProperties().hasPropertyVector("activation_time"))\n    {\n        activation_time_ =\n            st_mesh_.getProperties().template getPropertyVector<double>(\n                "activation_time");\n        birth_local_x_.resize(st_mesh_.getNumberOfElements());\n        birth_reference_captured_.assign(st_mesh_.getNumberOfElements(), false);\n        INFO("EmbeddedAnchor staged-construction lifecycle enabled for {:d} "\n             "anchor element(s).",\n             st_mesh_.getNumberOfElements());\n    }\n}\n''',
    "EmbeddedAnchor activation_time initialization",
)

# Insert the lifecycle implementation immediately before integrate().
replace_once(
    cpp,
    '''template <int GlobalDim>\nvoid EmbeddedAnchor<GlobalDim>::integrate(const double /*t*/,\n                                          GlobalVector const& x,\n''',
    '''template <int GlobalDim>\nvoid EmbeddedAnchor<GlobalDim>::preTimestep(double const t,\n                                            GlobalVector const& x)\n{\n    if (!activation_time_)\n    {\n        return;\n    }\n\n    for (MeshLib::Element const* const anchor_element : st_mesh_.getElements())\n    {\n        auto const anchor_element_id = anchor_element->getID();\n        if (birth_reference_captured_[anchor_element_id] ||\n            t < (*activation_time_)[anchor_element_id])\n        {\n            continue;\n        }\n\n        std::vector<GlobalIndexType> global_indices;\n        Eigen::Vector<double, 2 * GlobalDim> local_x;\n        std::vector<Eigen::RowVectorXd> shape_matrices;\n        std::array<std::size_t, 2> nodes_per_element{};\n        ParameterLib::SpatialPosition pos;\n        getShapeMatricesAndGlobalIndicesAndDisplacements(\n            anchor_element, nodes_per_element, shape_matrices, global_indices,\n            local_x, x, pos);\n\n        birth_local_x_[anchor_element_id] = local_x;\n        birth_reference_captured_[anchor_element_id] = true;\n        INFO("EmbeddedAnchor stress-free birth reference captured from "\n             "preTimestep converged state for anchor {:d} at t = {:g}; full "\n             "physical stiffness active.",\n             anchor_element_id, t);\n    }\n}\n\ntemplate <int GlobalDim>\nvoid EmbeddedAnchor<GlobalDim>::integrate(const double t,\n                                          GlobalVector const& x,\n''',
    "EmbeddedAnchor preTimestep implementation",
)

replace_once(
    cpp,
    '''        auto const anchor_element_id = anchor_element->getID();\n        std::vector<GlobalIndexType> global_indices;\n''',
    '''        auto const anchor_element_id = anchor_element->getID();\n\n        if (activation_time_ && t < (*activation_time_)[anchor_element_id])\n        {\n            continue;\n        }\n        if (activation_time_ && !birth_reference_captured_[anchor_element_id])\n        {\n            OGS_FATAL("EmbeddedAnchor {:d} reached assembly at t={:g} without "\n                      "a preTimestep birth reference. Refusing to infer the "\n                      "placement state from a Newton trial iterate.",\n                      anchor_element_id, t);\n        }\n\n        std::vector<GlobalIndexType> global_indices;\n''',
    "EmbeddedAnchor activation guard",
)

# Replace the geometry/strain block. For staged anchors the natural vector and
# natural length are the actual birth configuration, not the undeformed mesh.
replace_once(
    cpp,
    '''        auto node_coords = [anchor_element](int const i)\n        { return anchor_element->getNode(i)->asEigenVector3d(); };\n        GlobalDimVector const l_original =\n            (node_coords(1) - node_coords(0)).template head<GlobalDim>();\n        double const l_original_norm = l_original.norm();\n\n        // Displacement in the two nodes.\n        auto u = [&local_x](int const i)\n        { return local_x(nodeLocalIndices<GlobalDim>(i)); };\n        GlobalDimVector const l = l_original + u(1) - u(0);\n\n        double const K = (*cross_sectional_area_)[anchor_element_id] *\n''',
    '''        auto node_coords = [anchor_element](int const i)\n        { return anchor_element->getNode(i)->asEigenVector3d(); };\n        GlobalDimVector const l_original =\n            (node_coords(1) - node_coords(0)).template head<GlobalDim>();\n\n        auto u = [&local_x](int const i)\n        { return local_x(nodeLocalIndices<GlobalDim>(i)); };\n        GlobalDimVector const l = l_original + u(1) - u(0);\n\n        GlobalDimVector l_reference = l_original;\n        if (activation_time_)\n        {\n            auto const& birth_x = birth_local_x_[anchor_element_id];\n            auto u_birth = [&birth_x](int const i)\n            { return birth_x(nodeLocalIndices<GlobalDim>(i)); };\n            l_reference += u_birth(1) - u_birth(0);\n        }\n        double const l_reference_norm = l_reference.norm();\n\n        double const K = (*cross_sectional_area_)[anchor_element_id] *\n''',
    "EmbeddedAnchor birth reference geometry",
)
replace_once(
    cpp,
    '''        double const strain = (l.norm() - l_original_norm) / l_original_norm;\n\n        GlobalDimVector const f_friction =\n            residual_force * l_original / l_original_norm;\n        GlobalDimVector const f_elastic =\n            l_original / l_original_norm * (initial_force + K * strain);\n''',
    '''        double const strain =\n            (l.norm() - l_reference_norm) / l_reference_norm;\n\n        GlobalDimVector const f_friction =\n            residual_force * l_reference / l_reference_norm;\n        GlobalDimVector const f_elastic =\n            l_reference / l_reference_norm * (initial_force + K * strain);\n''',
    "EmbeddedAnchor stress-free strain definition",
)
replace_once(
    cpp,
    '''        GlobalDimMatrix const Df_elastic = l_original / l_original_norm * K *\n                                           l.transpose() / l.norm() /\n                                           l_original_norm;\n''',
    '''        GlobalDimMatrix const Df_elastic =\n            l_reference / l_reference_norm * K * l.transpose() / l.norm() /\n            l_reference_norm;\n''',
    "EmbeddedAnchor staged tangent reference",
)

cpp.write_text(cpp.read_text(encoding="utf-8"), encoding="utf-8")
print("Applied Phase C Anchor C0 preTimestep stress-free-birth lifecycle")
