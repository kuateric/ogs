// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#include "MechanicalInterfaceGlobalAssembly.h"

#include <limits>
#include <stdexcept>
#include <vector>

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

void scatterPairContribution(GlobalPairContribution const& contribution,
                             GlobalVector& residual,
                             GlobalMatrix& jacobian)
{
    auto const indices = checkedIndices(contribution.global_indices);

    std::vector<double> local_residual(contribution.pair.residual.begin(),
                                       contribution.pair.residual.end());
    residual.add(indices, local_residual);

    for (std::size_t i = 0; i < indices.size(); ++i)
    {
        for (std::size_t j = 0; j < indices.size(); ++j)
        {
            jacobian.add(indices[i], indices[j],
                         contribution.pair.jacobian[i * indices.size() + j]);
        }
    }
}
}  // namespace ProcessLib::MechanicalInterface
