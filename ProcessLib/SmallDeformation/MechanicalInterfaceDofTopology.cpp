// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#include "MechanicalInterfaceDofTopology.h"

#include <algorithm>
#include <iterator>
#include <unordered_set>

#include "BaseLib/Error.h"
#include "MeshLib/Elements/Element.h"
#include "MeshLib/Mesh.h"
#include "MeshLib/MeshSubset.h"
#include "NumLib/DOF/LocalToGlobalIndexMap.h"

namespace ProcessLib::MechanicalInterface
{
namespace
{
std::vector<MeshLib::Node*> collectUniqueNodes(
    std::vector<MeshLib::Element*> const& elements)
{
    std::vector<MeshLib::Node*> nodes;
    std::unordered_set<std::size_t> seen;
    for (auto* const e : elements)
    {
        for (unsigned i = 0; i < e->getNumberOfNodes(); ++i)
        {
            auto* const n = e->getNode(i);
            if (seen.insert(n->getID()).second)
            {
                nodes.push_back(n);
            }
        }
    }
    std::sort(nodes.begin(), nodes.end(), [](auto const* a, auto const* b) {
        return a->getID() < b->getID();
    });
    return nodes;
}
}  // namespace

MechanicalInterfaceDofTopology::MechanicalInterfaceDofTopology(
    MeshLib::Mesh const& mesh, int const displacement_dimension,
    std::vector<MeshLib::Element*> side_a_elements,
    std::vector<MeshLib::Element*> side_b_elements)
    : mesh_(mesh),
      displacement_dimension_(displacement_dimension),
      side_a_elements_(std::move(side_a_elements)),
      side_b_elements_(std::move(side_b_elements))
{
    if (displacement_dimension_ != 2 && displacement_dimension_ != 3)
    {
        OGS_FATAL("MechanicalInterfaceDofTopology requires dimension 2 or 3.");
    }
    if (side_a_elements_.empty() || side_b_elements_.empty())
    {
        OGS_FATAL("Mechanical interface requires non-empty Side A and Side B element sets.");
    }

    for (auto* const e : side_a_elements_)
    {
        if (e->getDimension() != displacement_dimension_)
        {
            OGS_FATAL("Side A contains non-bulk element {:d}.", e->getID());
        }
    }
    for (auto* const e : side_b_elements_)
    {
        if (e->getDimension() != displacement_dimension_)
        {
            OGS_FATAL("Side B contains non-bulk element {:d}.", e->getID());
        }
    }

    side_a_nodes_ = collectUniqueNodes(side_a_elements_);
    side_b_nodes_ = collectUniqueNodes(side_b_elements_);

    MeshLib::MeshSubset const a_subset{mesh_, side_a_nodes_};
    MeshLib::MeshSubset const b_subset{mesh_, side_b_nodes_};
    std::vector<MeshLib::MeshSubset> subsets;
    std::generate_n(std::back_inserter(subsets), displacement_dimension_,
                    [&]() { return a_subset; });
    std::generate_n(std::back_inserter(subsets), displacement_dimension_,
                    [&]() { return b_subset; });

    std::vector<int> const variable_components{displacement_dimension_,
                                               displacement_dimension_};
    std::vector<std::vector<MeshLib::Element*> const*> variable_elements{
        &side_a_elements_, &side_b_elements_};
    dof_table_ = std::make_unique<NumLib::LocalToGlobalIndexMap>(
        std::move(subsets), variable_components, variable_elements,
        NumLib::ComponentOrder::BY_COMPONENT);
    validatePartition();
}

void MechanicalInterfaceDofTopology::validatePartition() const
{
    if (dof_table_->getNumberOfVariables() != 2 ||
        dof_table_->getNumberOfVariableComponents(0) != displacement_dimension_ ||
        dof_table_->getNumberOfVariableComponents(1) != displacement_dimension_)
    {
        OGS_FATAL("Invalid mechanical-interface two-field DOF table.");
    }
    for (auto const* e : side_a_elements_)
    {
        auto const ids = dof_table_->getElementVariableIDs(e->getID());
        if (ids.size() != 1 || ids.front() != 0)
        {
            OGS_FATAL("Side A element {:d} does not carry exactly field A.", e->getID());
        }
    }
    for (auto const* e : side_b_elements_)
    {
        auto const ids = dof_table_->getElementVariableIDs(e->getID());
        if (ids.size() != 1 || ids.front() != 1)
        {
            OGS_FATAL("Side B element {:d} does not carry exactly field B.", e->getID());
        }
    }
}
}  // namespace ProcessLib::MechanicalInterface
