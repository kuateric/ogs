// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#include "RichardsMechanicsProcess.h"

#include <cassert>

#include "MeshLib/Elements/Utils.h"
#include "MeshLib/Utils/getOrCreateMeshProperty.h"
#include "NumLib/DOF/ComputeSparsityPattern.h"
#include "ProcessLib/Deformation/SolidMaterialInternalToSecondaryVariables.h"
#include "ProcessLib/Reflection/ReflectionForExtrapolation.h"
#include "ProcessLib/Reflection/ReflectionForIPWriters.h"
#include "ProcessLib/Utils/CreateLocalAssemblersTaylorHood.h"
#include "ProcessLib/Utils/SetIPDataInitialConditions.h"
#include "RichardsMechanicsFEM.h"
#include "RichardsMechanicsProcessData.h"

namespace ProcessLib
{
namespace RichardsMechanics
{
template <int DisplacementDim>
RichardsMechanicsProcess<DisplacementDim>::RichardsMechanicsProcess(
    std::string name, MeshLib::Mesh& mesh,
    std::unique_ptr<ProcessLib::AbstractJacobianAssembler>&& jacobian_assembler,
    std::vector<std::unique_ptr<ParameterLib::ParameterBase>> const& parameters,
    unsigned const integration_order,
    std::vector<std::vector<std::reference_wrapper<ProcessVariable>>>&&
        process_variables,
    RichardsMechanicsProcessData<DisplacementDim>&& process_data,
    SecondaryVariableCollection&& secondary_variables,
    bool const use_monolithic_scheme, bool const is_linear)
    : Process(std::move(name), mesh, std::move(jacobian_assembler), parameters,
              integration_order, std::move(process_variables),
              std::move(secondary_variables), use_monolithic_scheme),
      AssemblyMixin<RichardsMechanicsProcess<DisplacementDim>>{
          *_jacobian_assembler, is_linear, use_monolithic_scheme},
      process_data_(std::move(process_data))
{
    this->_jacobian_assembler->setNonDeformationComponentIDs({0});
    ProcessLib::Reflection::addReflectedIntegrationPointWriters<
        DisplacementDim>(LocalAssemblerIF::getReflectionDataForOutput(),
                         _integration_point_writer, integration_order,
                         local_assemblers_);
}

template <int DisplacementDim>
bool RichardsMechanicsProcess<DisplacementDim>::isLinear() const
{
    return AssemblyMixin<RichardsMechanicsProcess<DisplacementDim>>::isLinear();
}

template <int DisplacementDim>
MathLib::MatrixSpecifications RichardsMechanicsProcess<DisplacementDim>::getMatrixSpecifications(const int process_id) const
{
    if (_use_monolithic_scheme || process_id == 1)
    {
        auto const& l = *_local_to_global_index_map;
        return {l.dofSizeWithoutGhosts(), l.dofSizeWithoutGhosts(), &l.getGhostIndices(), &this->_sparsity_pattern};
    }
    auto const& l = *local_to_global_index_map_with_base_nodes_;
    return {l.dofSizeWithoutGhosts(), l.dofSizeWithoutGhosts(), &l.getGhostIndices(), &sparsity_pattern_with_linear_element_};
}

template <int DisplacementDim>
void RichardsMechanicsProcess<DisplacementDim>::constructDofTable()
{
    _mesh_subset_all_nodes = std::make_unique<MeshLib::MeshSubset>(_mesh, _mesh.getNodes());
    base_nodes_ = MeshLib::getBaseNodes(_mesh.getElements());
    mesh_subset_base_nodes_ = std::make_unique<MeshLib::MeshSubset>(_mesh, base_nodes_);
    std::vector<MeshLib::MeshSubset> single{*_mesh_subset_all_nodes};
    local_to_global_index_map_single_component_ = std::make_unique<NumLib::LocalToGlobalIndexMap>(std::move(single), NumLib::ComponentOrder::BY_LOCATION);
    if (_use_monolithic_scheme)
    {
        std::vector<MeshLib::MeshSubset> subsets{*mesh_subset_base_nodes_};
        std::generate_n(std::back_inserter(subsets), getProcessVariables(0)[1].get().getNumberOfGlobalComponents(), [&]() { return *_mesh_subset_all_nodes; });
        _local_to_global_index_map = std::make_unique<NumLib::LocalToGlobalIndexMap>(std::move(subsets), std::vector<int>{1, DisplacementDim}, NumLib::ComponentOrder::BY_LOCATION);
    }
    else
    {
        std::vector<MeshLib::MeshSubset> subsets;
        std::generate_n(std::back_inserter(subsets), getProcessVariables(1)[0].get().getNumberOfGlobalComponents(), [&]() { return *_mesh_subset_all_nodes; });
        _local_to_global_index_map = std::make_unique<NumLib::LocalToGlobalIndexMap>(std::move(subsets), std::vector<int>{DisplacementDim}, NumLib::ComponentOrder::BY_LOCATION);
        std::vector<MeshLib::MeshSubset> base{*mesh_subset_base_nodes_};
        local_to_global_index_map_with_base_nodes_ = std::make_unique<NumLib::LocalToGlobalIndexMap>(std::move(base), NumLib::ComponentOrder::BY_LOCATION);
        sparsity_pattern_with_linear_element_ = NumLib::computeSparsityPattern(*local_to_global_index_map_with_base_nodes_, _mesh);
    }
}

template <int DisplacementDim>
void RichardsMechanicsProcess<DisplacementDim>::initializeConcreteProcess(NumLib::LocalToGlobalIndexMap const& dof_table, MeshLib::Mesh const& mesh, unsigned const integration_order)
{
    ProcessLib::createLocalAssemblersHM<DisplacementDim, RichardsMechanicsLocalAssembler>(mesh.getElements(), dof_table, local_assemblers_, NumLib::IntegrationOrder{integration_order}, mesh.isAxiallySymmetric(), process_data_);
    if (!mechanical_interface_pending_pairs_.empty())
    {
        if constexpr (DisplacementDim == 2)
        {
            int const displacement_variable_id = _use_monolithic_scheme ? 1 : 0;
            auto pairs = ProcessLib::MechanicalInterface::resolve2DPendingPairsToProcessDofs(mechanical_interface_pending_pairs_, mesh.getID(), dof_table, displacement_variable_id);
            mechanical_interface_runtime_ = std::make_unique<ProcessLib::MechanicalInterface::MechanicalInterfaceSmallDeformationRuntime>(std::move(pairs), mechanical_interface_materials_);
        }
        else
        {
            OGS_FATAL("G5 mechanical interface V1 currently supports only 2D RichardsMechanics.");
        }
    }
    ProcessLib::Reflection::addReflectedSecondaryVariables<DisplacementDim>(LocalAssemblerIF::getReflectionDataForOutput(), _secondary_variables, getExtrapolator(), local_assemblers_);
    auto add_secondary_variable = [&](std::string const& name, int const n, auto f) { _secondary_variables.addSecondaryVariable(name, makeExtrapolator(n, getExtrapolator(), local_assemblers_, std::move(f))); };
    ProcessLib::Deformation::solidMaterialInternalToSecondaryVariables<LocalAssemblerIF>(process_data_.solid_materials, add_secondary_variable);
    ProcessLib::Deformation::solidMaterialInternalVariablesToIntegrationPointWriter(process_data_.solid_materials, local_assemblers_, _integration_point_writer, integration_order);
    process_data_.element_saturation = MeshLib::getOrCreateMeshProperty<double>(const_cast<MeshLib::Mesh&>(mesh), "saturation_avg", MeshLib::MeshItemType::Cell, 1);
    process_data_.element_porosity = MeshLib::getOrCreateMeshProperty<double>(const_cast<MeshLib::Mesh&>(mesh), "porosity_avg", MeshLib::MeshItemType::Cell, 1);
    process_data_.element_stresses = MeshLib::getOrCreateMeshProperty<double>(const_cast<MeshLib::Mesh&>(mesh), "stress_avg", MeshLib::MeshItemType::Cell, MathLib::KelvinVector::KelvinVectorType<DisplacementDim>::RowsAtCompileTime);
    process_data_.pressure_interpolated = MeshLib::getOrCreateMeshProperty<double>(const_cast<MeshLib::Mesh&>(mesh), "pressure_interpolated", MeshLib::MeshItemType::Node, 1);
    setIPDataInitialConditions(_integration_point_writer, mesh.getProperties(), local_assemblers_);
    GlobalExecutor::executeMemberOnDereferenced(&LocalAssemblerIF::initialize, local_assemblers_, *_local_to_global_index_map);
}

template <int DisplacementDim>
void RichardsMechanicsProcess<DisplacementDim>::initializeBoundaryConditions(std::map<int, std::shared_ptr<MaterialPropertyLib::Medium>> const& media)
{
    if (_use_monolithic_scheme) { initializeProcessBoundaryConditionsAndSourceTerms(*_local_to_global_index_map, 0, media); return; }
    initializeProcessBoundaryConditionsAndSourceTerms(*local_to_global_index_map_with_base_nodes_, 0, media);
    initializeProcessBoundaryConditionsAndSourceTerms(*_local_to_global_index_map, 1, media);
}

template <int DisplacementDim>
void RichardsMechanicsProcess<DisplacementDim>::setInitialConditionsConcreteProcess(std::vector<GlobalVector*>& x, double const t, int const process_id)
{
    if (process_id != 0) return;
    GlobalExecutor::executeSelectedMemberOnDereferenced(&LocalAssemblerIF::setInitialConditions, local_assemblers_, getActiveElementIDs(), getDOFTables(x.size()), x, t, process_id);
}

template <int DisplacementDim>
void RichardsMechanicsProcess<DisplacementDim>::assembleConcreteProcess(const double t, double const dt, std::vector<GlobalVector*> const& x, std::vector<GlobalVector*> const& x_prev, int const process_id, GlobalMatrix& M, GlobalMatrix& K, GlobalVector& b)
{ AssemblyMixin<RichardsMechanicsProcess<DisplacementDim>>::assemble(t, dt, x, x_prev, process_id, M, K, b); }

template <int DisplacementDim>
void RichardsMechanicsProcess<DisplacementDim>::assembleWithJacobianConcreteProcess(const double t, double const dt, std::vector<GlobalVector*> const& x, std::vector<GlobalVector*> const& x_prev, int const process_id, GlobalVector& b, GlobalMatrix& Jac)
{
    AssemblyMixin<RichardsMechanicsProcess<DisplacementDim>>::assembleWithJacobian(t, dt, x, x_prev, process_id, b, Jac);
    if (mechanical_interface_runtime_ && hasMechanicalProcess(process_id))
        mechanical_interface_runtime_->assembleWithJacobian(*x[process_id], b, Jac);
}

template <int DisplacementDim>
void RichardsMechanicsProcess<DisplacementDim>::preTimestepConcreteProcess(std::vector<GlobalVector*> const& x, double const t, double const dt, const int process_id)
{
    GlobalExecutor::executeSelectedMemberOnDereferenced(&LocalAssemblerIF::preTimestep, local_assemblers_, getActiveElementIDs(), *_local_to_global_index_map, *x[process_id], t, dt);
    AssemblyMixin<RichardsMechanicsProcess<DisplacementDim>>::updateActiveElements();
}

template <int DisplacementDim>
void RichardsMechanicsProcess<DisplacementDim>::postTimestepConcreteProcess(std::vector<GlobalVector*> const& x, std::vector<GlobalVector*> const& x_prev, double const t, double const dt, const int process_id)
{
    if (!hasMechanicalProcess(process_id)) return;
    GlobalExecutor::executeSelectedMemberOnDereferenced(&LocalAssemblerIF::postTimestep, local_assemblers_, getActiveElementIDs(), getDOFTables(x.size()), x, x_prev, t, dt, process_id);
    if (mechanical_interface_runtime_) mechanical_interface_runtime_->acceptTimeStep();
}

template <int DisplacementDim>
std::vector<std::vector<std::string>> RichardsMechanicsProcess<DisplacementDim>::initializeAssemblyOnSubmeshes(std::vector<std::reference_wrapper<MeshLib::Mesh>> const& meshes)
{
    std::vector<std::vector<std::string>> names{{"MassFlowRate", "NodalForces"}};
    AssemblyMixin<RichardsMechanicsProcess<DisplacementDim>>::initializeAssemblyOnSubmeshes(meshes, names); return names;
}

template <int DisplacementDim>
void RichardsMechanicsProcess<DisplacementDim>::computeSecondaryVariableConcrete(const double t, const double dt, std::vector<GlobalVector*> const& x, GlobalVector const& x_prev, int const process_id)
{
    if (process_id != 0) return;
    GlobalExecutor::executeSelectedMemberOnDereferenced(&LocalAssemblerIF::computeSecondaryVariable, local_assemblers_, getActiveElementIDs(), getDOFTables(x.size()), t, dt, x, x_prev, process_id);
}

template <int DisplacementDim>
std::tuple<NumLib::LocalToGlobalIndexMap*, bool> RichardsMechanicsProcess<DisplacementDim>::getDOFTableForExtrapolatorData() const
{ return std::make_tuple(local_to_global_index_map_single_component_.get(), false); }

template <int DisplacementDim>
NumLib::LocalToGlobalIndexMap const& RichardsMechanicsProcess<DisplacementDim>::getDOFTable(const int process_id) const
{ return hasMechanicalProcess(process_id) ? *_local_to_global_index_map : *local_to_global_index_map_with_base_nodes_; }

template class RichardsMechanicsProcess<2>;
template class RichardsMechanicsProcess<3>;
}
}
