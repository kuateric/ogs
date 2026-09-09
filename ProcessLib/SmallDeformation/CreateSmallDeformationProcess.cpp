// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#include "CreateSmallDeformationProcess.h"

#include <cassert>
#include <cmath>
#include <utility>

#include "MaterialLib/MPL/CreateMaterialSpatialDistributionMap.h"
#include "MaterialLib/SolidModels/CreateConstitutiveRelation.h"
#include "ParameterLib/Utils.h"
#include "ProcessLib/Output/CreateSecondaryVariables.h"
#include "ProcessLib/Utils/ProcessUtils.h"
#include "MechanicalInterfaceSmallDeformationRuntime.h"
#include "SmallDeformationProcess.h"
#include "SmallDeformationProcessData.h"

namespace ProcessLib
{
namespace SmallDeformation
{
void checkMPLProperties(
    std::map<int, std::shared_ptr<MaterialPropertyLib::Medium>> const& media)
{
    for (auto const& m : media)
    {
        checkRequiredProperties(
            m.second->phase(MaterialPropertyLib::PhaseName::Solid),
            {{MaterialPropertyLib::density}});
    }
}

template <int DisplacementDim>
std::unique_ptr<Process> createSmallDeformationProcess(
    std::string const& name,
    MeshLib::Mesh& mesh,
    std::unique_ptr<ProcessLib::AbstractJacobianAssembler>&& jacobian_assembler,
    std::vector<ProcessVariable> const& variables,
    std::vector<std::unique_ptr<ParameterLib::ParameterBase>> const& parameters,
    std::optional<ParameterLib::CoordinateSystem> const&
        local_coordinate_system,
    unsigned const integration_order,
    BaseLib::ConfigTree const& config,
    std::map<int, std::shared_ptr<MaterialPropertyLib::Medium>> const& media)
{
    //! \ogs_file_param{prj__processes__process__type}
    config.checkConfigParameter("type", "SMALL_DEFORMATION");
    DBUG("Create SmallDeformationProcess.");

    /// \section processvariablessd Process Variables

    //! \ogs_file_param{prj__processes__process__SMALL_DEFORMATION__process_variables}
    auto const pv_config = config.getConfigSubtree("process_variables");

    /// Primary process variables as they appear in the global component vector:
    auto per_process_variables = findProcessVariables(
        variables, pv_config,
        {//! \ogs_file_param_special{prj__processes__process__SMALL_DEFORMATION__process_variables__process_variable}
         "process_variable"});

    DBUG("Associate displacement with process variable '{:s}'.",
         per_process_variables.back().get().getName());

    if (per_process_variables.back().get().getNumberOfGlobalComponents() !=
        DisplacementDim)
    {
        OGS_FATAL(
            "Number of components of the process variable '{:s}' is different "
            "from the displacement dimension: got {:d}, expected {:d}",
            per_process_variables.back().get().getName(),
            per_process_variables.back().get().getNumberOfGlobalComponents(),
            DisplacementDim);
    }
    std::vector<std::vector<std::reference_wrapper<ProcessVariable>>>
        process_variables;
    process_variables.push_back(std::move(per_process_variables));

    /// \section parameterssd Process Parameters
    auto solid_constitutive_relations =
        MaterialLib::Solids::createConstitutiveRelations<DisplacementDim>(
            parameters, local_coordinate_system, materialIDs(mesh), config);

    //! \ogs_file_param{prj__processes__process__SMALL_DEFORMATION__solid_density}
    if (config.getConfigParameterOptional<std::string>("solid_density"))
    {
        OGS_FATAL(
            "The <solid_density> tag has been removed. Use <media> definitions "
            "to specify solid's density.");
    }

    Eigen::Matrix<double, DisplacementDim, 1> specific_body_force;
    {
        std::vector<double> const b =
            //! \ogs_file_param{prj__processes__process__SMALL_DEFORMATION__specific_body_force}
            config.getConfigParameter<std::vector<double>>(
                "specific_body_force");
        if (b.size() != DisplacementDim)
        {
            OGS_FATAL(
                "The size of the specific body force vector does not match the "
                "displacement dimension. Vector size is {:d}, displacement "
                "dimension is {:d}",
                b.size(), DisplacementDim);
        }

        std::copy_n(b.data(), b.size(), specific_body_force.data());
    }

    //! \ogs_file_param{prj__processes__process__SMALL_DEFORMATION__use_b_bar}
    auto const use_b_bar = config.getConfigParameter<bool>("use_b_bar", false);

    auto media_map =
        MaterialPropertyLib::createMaterialSpatialDistributionMap(media, mesh);
    DBUG(
        "Check the media properties of SmallDeformation process "
        "...");
    checkMPLProperties(media);
    DBUG("Media properties verified.");

    auto const reference_temperature = ParameterLib::findOptionalTagParameter<
        double>(
        //! \ogs_file_param_special{prj__processes__process__SMALL_DEFORMATION__reference_temperature}
        config, "reference_temperature", parameters, 1, &mesh);
    if (reference_temperature)
    {
        DBUG("Use '{:s}' as reference temperature parameter.",
             (*reference_temperature).name);
    }

    auto const initial_stress = ParameterLib::findOptionalTagParameter<double>(
        //! \ogs_file_param_special{prj__processes__process__SMALL_DEFORMATION__initial_stress}
        config, "initial_stress", parameters,
        MathLib::KelvinVector::kelvin_vector_dimensions(DisplacementDim),
        &mesh);

    auto const is_linear =
        //! \ogs_file_param{prj__processes__process__linear}
        config.getConfigParameter("linear", false);

    std::vector<ProcessLib::MechanicalInterface::SmallDeformationPendingPair>
        mechanical_interface_pending_pairs;
    std::vector<ProcessLib::MechanicalInterface::SmallDeformationInterfaceMaterial>
        mechanical_interface_materials;
    if (auto mechanical_interface_config =
            config.getConfigSubtreeOptional("mechanical_interface"))
    {
        if constexpr (DisplacementDim != 2)
        {
            OGS_FATAL(
                "G5 <mechanical_interface> V1 is available only for 2D "
                "SMALL_DEFORMATION.");
        }

        for (auto const& material_config :
             mechanical_interface_config->getConfigSubtreeList("material"))
        {
            auto const material_id =
                material_config.getConfigParameter<std::size_t>("id");
            auto const k_n = material_config.getConfigParameter<double>(
                "normal_stiffness");
            auto const k_t = material_config.getConfigParameter<double>(
                "tangential_stiffness");
            auto const mu = material_config.getConfigParameter<double>(
                "friction_coefficient");
            if (!(k_n > 0.0) || !(k_t > 0.0) || mu < 0.0)
            {
                OGS_FATAL(
                    "G5 interface material {:d}: normal/tangential stiffness "
                    "must be > 0 and friction coefficient >= 0.", material_id);
            }
            mechanical_interface_materials.push_back(
                {material_id, {k_n, k_t, mu}});
        }

        if (mechanical_interface_materials.empty())
        {
            OGS_FATAL(
                "G5 <mechanical_interface> requires at least one <material>.");
        }

        std::size_t pair_id = 0;
        for (auto const& pair_config :
             mechanical_interface_config->getConfigSubtreeList("pair"))
        {
            auto const side_a_node_id =
                pair_config.getConfigParameter<std::size_t>("side_a_node_id");
            auto const side_b_node_id =
                pair_config.getConfigParameter<std::size_t>("side_b_node_id");
            auto normal =
                pair_config.getConfigParameter<std::vector<double>>("normal");
            if (normal.size() != 2)
            {
                OGS_FATAL(
                    "G5 mechanical interface pair {:d}: <normal> must contain "
                    "exactly two components, got {:d}.",
                    pair_id, normal.size());
            }
            auto const normal_norm = std::hypot(normal[0], normal[1]);
            if (!(normal_norm > 0.0))
            {
                OGS_FATAL(
                    "G5 mechanical interface pair {:d}: <normal> must be "
                    "non-zero.", pair_id);
            }

            mechanical_interface_pending_pairs.push_back(
                {pair_id,
                 side_a_node_id,
                 side_b_node_id,
                 {normal[0] / normal_norm, normal[1] / normal_norm},
                 pair_config.getConfigParameter<double>("initial_normal_gap", 0.0),
                 pair_config.getConfigParameter<std::size_t>(
                     "interface_material_id")});
            ++pair_id;
        }

        if (mechanical_interface_pending_pairs.empty())
        {
            OGS_FATAL(
                "G5 <mechanical_interface> requires at least one <pair>.");
        }
    }

    SmallDeformationProcessData<DisplacementDim> process_data{
        materialIDs(mesh),
        std::move(media_map),
        std::move(solid_constitutive_relations),
        initial_stress,
        specific_body_force,
        reference_temperature,
        use_b_bar};

    SecondaryVariableCollection secondary_variables;

    ProcessLib::createSecondaryVariables(config, secondary_variables);

    auto process = std::make_unique<SmallDeformationProcess<DisplacementDim>>(
        std::move(name), mesh, std::move(jacobian_assembler), parameters,
        integration_order, std::move(process_variables),
        std::move(process_data), std::move(secondary_variables), is_linear);
    process->setMechanicalInterfaceConfiguration(
        std::move(mechanical_interface_pending_pairs),
        std::move(mechanical_interface_materials));
    return process;
}

template std::unique_ptr<Process> createSmallDeformationProcess<2>(
    std::string const& name,
    MeshLib::Mesh& mesh,
    std::unique_ptr<ProcessLib::AbstractJacobianAssembler>&& jacobian_assembler,
    std::vector<ProcessVariable> const& variables,
    std::vector<std::unique_ptr<ParameterLib::ParameterBase>> const& parameters,
    std::optional<ParameterLib::CoordinateSystem> const&
        local_coordinate_system,
    unsigned const integration_order,
    BaseLib::ConfigTree const& config,
    std::map<int, std::shared_ptr<MaterialPropertyLib::Medium>> const& media);

template std::unique_ptr<Process> createSmallDeformationProcess<3>(
    std::string const& name,
    MeshLib::Mesh& mesh,
    std::unique_ptr<ProcessLib::AbstractJacobianAssembler>&& jacobian_assembler,
    std::vector<ProcessVariable> const& variables,
    std::vector<std::unique_ptr<ParameterLib::ParameterBase>> const& parameters,
    std::optional<ParameterLib::CoordinateSystem> const&
        local_coordinate_system,
    unsigned const integration_order,
    BaseLib::ConfigTree const& config,
    std::map<int, std::shared_ptr<MaterialPropertyLib::Medium>> const& media);

}  // namespace SmallDeformation
}  // namespace ProcessLib
