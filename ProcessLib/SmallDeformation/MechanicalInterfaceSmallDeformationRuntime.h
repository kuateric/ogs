// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <array>
#include <cstddef>
#include <vector>

#include "MechanicalInterfaceProcessLifecycle.h"
#include "MechanicalInterfaceStatefulPairAssembly.h"

namespace NumLib
{
class LocalToGlobalIndexMap;
}

namespace ProcessLib::MechanicalInterface
{
/// Constitutive definition referenced by interface pairs.
///
/// This is deliberately separate from pair topology and process DOF mapping.
/// A later MFront-backed law can replace/extend this record without changing
/// initializeConcreteProcess() or the Side-A/Side-B mapping lifecycle.
struct SmallDeformationInterfaceMaterial
{
    std::size_t material_id = 0;
    Parameters parameters{};
};

/// Geometry/topology known before OGS creates its process DOF table.
///
/// Keep node ids here instead of prematurely manufacturing global indices in
/// CreateSmallDeformationProcess(). Constitutive data are referenced only by
/// interface_material_id; the pair itself does not own a material law.
struct SmallDeformationPendingPair
{
    std::size_t pair_id = 0;
    std::size_t side_a_node_id = 0;
    std::size_t side_b_node_id = 0;
    std::array<double, 2> normal{};
    double initial_normal_gap = 0.0;
    std::size_t interface_material_id = 0;
};

/// Fully mapped 2D interface pair consumed by the SmallDeformation runtime.
/// Pair creation/topology remains independent of the constitutive law so the
/// same pair definition can later be reused by RichardsMechanics/TRM.
struct SmallDeformationRuntimePair
{
    std::size_t pair_id = 0;
    std::array<std::size_t, 4> global_indices{};  // [A_x,A_y,B_x,B_y]
    std::array<double, 2> normal{};
    double initial_normal_gap = 0.0;
    std::size_t interface_material_id = 0;
};

/// Resolve pre-DOF interface topology against the owning process' actual
/// displacement table. This function is intentionally material-agnostic and is
/// called only from process initialization, never from the XML factory.
std::vector<SmallDeformationRuntimePair> resolve2DPendingPairsToProcessDofs(
    std::vector<SmallDeformationPendingPair> const& pending_pairs,
    std::size_t mesh_id,
    NumLib::LocalToGlobalIndexMap const& process_dof_table,
    int displacement_variable_id = 0);

/// Process-facing G5 bridge for canonical OGS SmallDeformation.
///
/// The ordinary bulk SmallDeformation assembly remains authoritative. This
/// bridge is invoked afterwards and contributes only the interface residual and
/// consistent Jacobian. Material lookup occurs here, after topology/DOF
/// resolution, so initializeConcreteProcess() remains constitutive-law agnostic.
class MechanicalInterfaceSmallDeformationRuntime final
{
public:
    MechanicalInterfaceSmallDeformationRuntime(
        std::vector<SmallDeformationRuntimePair> pairs,
        std::vector<SmallDeformationInterfaceMaterial> materials);

    void assembleWithJacobian(GlobalVector const& x, GlobalVector& b,
                              GlobalMatrix& jacobian);

    /// Call only from SmallDeformation's accepted post-timestep path.
    void acceptTimeStep() { lifecycle_.acceptTimeStep(); }

    /// Optional explicit rejection hook where a caller can signal rejection.
    void rejectTimeStep() { lifecycle_.rejectTimeStep(); }

    MechanicalInterfaceStateManager const& stateManager() const
    {
        return state_manager_;
    }

private:
    Parameters const& parametersForMaterial(std::size_t material_id) const;

    std::vector<SmallDeformationRuntimePair> pairs_;
    std::vector<SmallDeformationInterfaceMaterial> materials_;
    MechanicalInterfaceStateManager state_manager_;
    MechanicalInterfaceProcessLifecycle lifecycle_;
};
}  // namespace ProcessLib::MechanicalInterface
