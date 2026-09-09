// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <memory>
#include <vector>

namespace MeshLib
{
class Element;
class Mesh;
class Node;
}
namespace NumLib
{
class LocalToGlobalIndexMap;
}

namespace ProcessLib::MechanicalInterface
{
/// Symmetric two-field topology for mechanical interfaces.
///
/// Unlike the frozen G4 embedded host/member topology, both sides may consist
/// of full-dimensional continuum elements. Side A and Side B are independent
/// displacement fields and neither side is privileged.
class MechanicalInterfaceDofTopology final
{
public:
    MechanicalInterfaceDofTopology(
        MeshLib::Mesh const& mesh, int displacement_dimension,
        std::vector<MeshLib::Element*> side_a_elements,
        std::vector<MeshLib::Element*> side_b_elements);

    std::vector<MeshLib::Node*> const& sideANodes() const { return side_a_nodes_; }
    std::vector<MeshLib::Node*> const& sideBNodes() const { return side_b_nodes_; }
    std::vector<MeshLib::Element*> const& sideAElements() const { return side_a_elements_; }
    std::vector<MeshLib::Element*> const& sideBElements() const { return side_b_elements_; }

    std::unique_ptr<NumLib::LocalToGlobalIndexMap> takeDofTable()
    {
        return std::move(dof_table_);
    }

private:
    void validatePartition() const;

    MeshLib::Mesh const& mesh_;
    int displacement_dimension_;
    std::vector<MeshLib::Element*> side_a_elements_;
    std::vector<MeshLib::Element*> side_b_elements_;
    std::vector<MeshLib::Node*> side_a_nodes_;
    std::vector<MeshLib::Node*> side_b_nodes_;
    std::unique_ptr<NumLib::LocalToGlobalIndexMap> dof_table_;
};
}  // namespace ProcessLib::MechanicalInterface
