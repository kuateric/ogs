// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <utility>

#include "LocalAssemblerInterface.h"
#include "ProcessLib/AssemblyMixin.h"
#include "ProcessLib/Process.h"
#include "ProcessLib/SmallDeformation/MechanicalInterfaceSmallDeformationRuntime.h"
#include "RichardsMechanicsProcessData.h"

namespace ProcessLib
{
namespace RichardsMechanics
{
/// Linear kinematics poro-mechanical/biphasic (fluid-solid mixture) model.
template <int DisplacementDim>
class RichardsMechanicsProcess final
    : public Process,
      private AssemblyMixin<RichardsMechanicsProcess<DisplacementDim>>
{
    friend class AssemblyMixin<RichardsMechanicsProcess<DisplacementDim>>;

public:
    RichardsMechanicsProcess(
        std::string name, MeshLib::Mesh& mesh,
        std::unique_ptr<ProcessLib::AbstractJacobianAssembler>&& jacobian_assembler,
        std::vector<std::unique_ptr<ParameterLib::ParameterBase>> const& parameters,
        unsigned const integration_order,
        std::vector<std::vector<std::reference_wrapper<ProcessVariable>>>&& process_variables,
        RichardsMechanicsProcessData<DisplacementDim>&& process_data,
        SecondaryVariableCollection&& secondary_variables,
        bool const use_monolithic_scheme, bool const is_linear);

    bool isLinear() const override;

    MathLib::MatrixSpecifications getMatrixSpecifications(
        const int process_id) const override;

    /// Supply the same frozen G5 V1 topology/material definitions used by
    /// SmallDeformation. RichardsMechanics owns only the process integration;
    /// the G5 law, pair assembly, state manager and lifecycle remain unchanged.
    void setMechanicalInterfaceConfiguration(
        std::vector<ProcessLib::MechanicalInterface::SmallDeformationPendingPair>
            pending_pairs,
        std::vector<ProcessLib::MechanicalInterface::
                        SmallDeformationInterfaceMaterial> materials)
    {
        mechanical_interface_pending_pairs_ = std::move(pending_pairs);
        mechanical_interface_materials_ = std::move(materials);
    }

private:
    using LocalAssemblerIF = LocalAssemblerInterface<DisplacementDim>;

    void constructDofTable() override;

    void initializeConcreteProcess(
        NumLib::LocalToGlobalIndexMap const& dof_table,
        MeshLib::Mesh const& mesh,
        unsigned const integration_order) override;

    void initializeBoundaryConditions(
        std::map<int, std::shared_ptr<MaterialPropertyLib::Medium>> const& media)
        override;

    void setInitialConditionsConcreteProcess(std::vector<GlobalVector*>& x,
                                             double const t,
                                             int const process_id) override;

    void assembleConcreteProcess(const double t, double const dt,
                                 std::vector<GlobalVector*> const& x,
                                 std::vector<GlobalVector*> const& x_prev,
                                 int const process_id, GlobalMatrix& M,
                                 GlobalMatrix& K, GlobalVector& b) override;

    void assembleWithJacobianConcreteProcess(
        const double t, double const dt, std::vector<GlobalVector*> const& x,
        std::vector<GlobalVector*> const& x_prev, int const process_id,
        GlobalVector& b, GlobalMatrix& Jac) override;

    void preTimestepConcreteProcess(std::vector<GlobalVector*> const& x,
                                    double const t, double const dt,
                                    const int process_id) override;

    void postTimestepConcreteProcess(std::vector<GlobalVector*> const& x,
                                     std::vector<GlobalVector*> const& x_prev,
                                     double const t, double const dt,
                                     const int process_id) override;

    std::vector<std::vector<std::string>> initializeAssemblyOnSubmeshes(
        std::vector<std::reference_wrapper<MeshLib::Mesh>> const& meshes)
        override;

    NumLib::LocalToGlobalIndexMap const& getDOFTable(
        const int process_id) const override;

private:
    std::vector<MeshLib::Node*> base_nodes_;
    std::unique_ptr<MeshLib::MeshSubset const> mesh_subset_base_nodes_;
    RichardsMechanicsProcessData<DisplacementDim> process_data_;

    std::vector<std::unique_ptr<LocalAssemblerIF>> local_assemblers_;

    std::unique_ptr<NumLib::LocalToGlobalIndexMap>
        local_to_global_index_map_single_component_;

    std::unique_ptr<NumLib::LocalToGlobalIndexMap>
        local_to_global_index_map_with_base_nodes_;

    GlobalSparsityPattern sparsity_pattern_with_linear_element_;

    void computeSecondaryVariableConcrete(double const t, double const dt,
                                          std::vector<GlobalVector*> const& x,
                                          GlobalVector const& x_prev,
                                          int const process_id) override;

    std::tuple<NumLib::LocalToGlobalIndexMap*, bool>
    getDOFTableForExtrapolatorData() const override;

    bool hasMechanicalProcess(int const process_id) const
    {
        return _use_monolithic_scheme || process_id == 1;
    }

    std::vector<ProcessLib::MechanicalInterface::SmallDeformationPendingPair>
        mechanical_interface_pending_pairs_;
    std::vector<ProcessLib::MechanicalInterface::
                    SmallDeformationInterfaceMaterial>
        mechanical_interface_materials_;
    std::unique_ptr<ProcessLib::MechanicalInterface::
                        MechanicalInterfaceSmallDeformationRuntime>
        mechanical_interface_runtime_;
};

extern template class RichardsMechanicsProcess<2>;
extern template class RichardsMechanicsProcess<3>;

}  // namespace RichardsMechanics
}  // namespace ProcessLib
