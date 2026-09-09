// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#include "MechanicalInterfaceSmallDeformationRuntime.h"

#include <algorithm>
#include <limits>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

#include "BaseLib/Logging.h"
#include "MechanicalInterfaceProcessDofMapper.h"

namespace ProcessLib::MechanicalInterface
{
namespace
{
std::vector<GlobalIndexType> checkedIndices(
    std::array<std::size_t, 4> const& indices)
{
    std::vector<GlobalIndexType> result;
    result.reserve(indices.size());
    for (auto const i : indices)
    {
        if (i > static_cast<std::size_t>(
                    std::numeric_limits<GlobalIndexType>::max()))
        {
            throw std::overflow_error(
                "Mechanical-interface global index exceeds OGS index range.");
        }
        result.push_back(static_cast<GlobalIndexType>(i));
    }
    return result;
}
}  // namespace

std::vector<SmallDeformationRuntimePair> resolve2DPendingPairsToProcessDofs(
    std::vector<SmallDeformationPendingPair> const& pending_pairs,
    std::size_t const mesh_id,
    NumLib::LocalToGlobalIndexMap const& process_dof_table,
    int const displacement_variable_id)
{
    std::vector<SmallDeformationRuntimePair> result;
    result.reserve(pending_pairs.size());

    for (auto const& pending : pending_pairs)
    {
        SmallDeformationRuntimePair pair;
        pair.pair_id = pending.pair_id;
        pair.global_indices = map2DPairToProcessDofs(
            mesh_id, pending.side_a_node_id, pending.side_b_node_id,
            process_dof_table, displacement_variable_id);
        pair.normal = pending.normal;
        pair.initial_normal_gap = pending.initial_normal_gap;
        pair.interface_material_id = pending.interface_material_id;
        result.push_back(std::move(pair));
    }

    return result;
}

MechanicalInterfaceSmallDeformationRuntime::
    MechanicalInterfaceSmallDeformationRuntime(
        std::vector<SmallDeformationRuntimePair> pairs,
        std::vector<SmallDeformationInterfaceMaterial> materials)
    : pairs_(std::move(pairs)),
      materials_(std::move(materials)),
      state_manager_(pairs_.size()),
      lifecycle_(state_manager_)
{
    // Explicit .prj pairs bypass the geometric PairRegistry, therefore the
    // runtime must independently enforce the same two-field topology invariant:
    // every physical side node participates exactly once, Side A and Side B are
    // disjoint, and one pair never maps a node onto itself. Otherwise identical
    // interface contributions could be assembled more than once.
    std::set<std::array<std::size_t, 2>> side_a_dofs;
    std::set<std::array<std::size_t, 2>> side_b_dofs;

    for (std::size_t i = 0; i < pairs_.size(); ++i)
    {
        if (pairs_[i].pair_id != i)
        {
            throw std::invalid_argument(
                "Mechanical-interface runtime pair ids must be contiguous and "
                "match storage order.");
        }

        auto const& indices = pairs_[i].global_indices;
        std::array<std::size_t, 2> const side_a{{indices[0], indices[1]}};
        std::array<std::size_t, 2> const side_b{{indices[2], indices[3]}};

        if (side_a == side_b)
        {
            throw std::invalid_argument(
                "Mechanical-interface pair must connect two distinct process "
                "nodes (two-field topology).");
        }
        if (!side_a_dofs.insert(side_a).second)
        {
            throw std::invalid_argument(
                "Mechanical-interface Side A process node is referenced by "
                "more than one pair.");
        }
        if (!side_b_dofs.insert(side_b).second)
        {
            throw std::invalid_argument(
                "Mechanical-interface Side B process node is referenced by "
                "more than one pair.");
        }
    }

    for (auto const& side_a : side_a_dofs)
    {
        if (side_b_dofs.contains(side_a))
        {
            throw std::invalid_argument(
                "Mechanical-interface Side A and Side B process node sets must "
                "be disjoint for the two-field topology.");
        }
    }

    for (std::size_t i = 0; i < materials_.size(); ++i)
    {
        auto const id = materials_[i].material_id;
        auto const duplicate = std::find_if(
            materials_.begin() + static_cast<std::ptrdiff_t>(i + 1),
            materials_.end(), [id](auto const& material) {
                return material.material_id == id;
            });
        if (duplicate != materials_.end())
        {
            throw std::invalid_argument(
                "Mechanical-interface material ids must be unique.");
        }
    }

    for (auto const& pair : pairs_)
    {
        (void)parametersForMaterial(pair.interface_material_id);
    }
}

Parameters const&
MechanicalInterfaceSmallDeformationRuntime::parametersForMaterial(
    std::size_t const material_id) const
{
    auto const it = std::find_if(
        materials_.begin(), materials_.end(),
        [material_id](auto const& material) {
            return material.material_id == material_id;
        });
    if (it == materials_.end())
    {
        throw std::invalid_argument(
            "Mechanical-interface pair references an unknown material id.");
    }
    return it->parameters;
}

void MechanicalInterfaceSmallDeformationRuntime::assembleWithJacobian(
    GlobalVector const& x, GlobalVector& b, GlobalMatrix& jacobian)
{
    // Canonical OGS does not provide a process-specific reject callback for
    // every abandoned nonlinear attempt. Reset trial output/history view before
    // every fresh residual/Jacobian evaluation so rejected attempts cannot leak.
    lifecycle_.beginTrialAssembly();

    for (auto const& pair : pairs_)
    {
        auto const indices = checkedIndices(pair.global_indices);
        auto const u = x.get(indices);
        if (u.size() != 4)
        {
            throw std::runtime_error(
                "Mechanical-interface 2D runtime expected four displacement "
                "DOF values for one Side-A/Side-B pair.");
        }

        std::array<double, 2> const u_a{{u[0], u[1]}};
        std::array<double, 2> const u_b{{u[2], u[3]}};
        auto const& parameters =
            parametersForMaterial(pair.interface_material_id);

        auto contribution = assembleTrialGlobalPair(
            pair.pair_id, u_a, u_b, pair.normal, pair.initial_normal_gap,
            parameters, pair.global_indices, state_manager_);

        // Emit the constitutive response from the exact process-owned trial
        // evaluation. This is intentionally diagnostic-only: it does not alter
        // the residual, tangent or commit/rollback mechanics. The narrow G5
        // native gate consumes these records to prove that real .prj execution
        // exposes gap, total slip, both tractions and contact state rather than
        // only demonstrating that the hook was called.
        auto const& local = contribution.pair.local;
        INFO("OGS-STR-G5-RUNTIME pair={} gap={} slip={} normal_traction={} "
             "tangential_traction={} state={} plastic_slip={}",
             pair.pair_id, local.normal_gap, local.tangential_slip,
             local.normal_traction, local.tangential_traction,
             toString(local.state), local.updated_history.plastic_slip);

        // Generic G5 assembly returns the physical internal residual R. OGS
        // SmallDeformation assembles the Newton right-hand side b = -R while
        // retaining the positive consistent tangent dR/dx in Jac.
        for (auto& value : contribution.pair.residual)
        {
            value = -value;
        }

        scatterPairContribution(contribution, b, jacobian);
    }
}
}  // namespace ProcessLib::MechanicalInterface
