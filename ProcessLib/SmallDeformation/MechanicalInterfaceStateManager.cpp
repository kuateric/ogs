// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#include "MechanicalInterfaceStateManager.h"

#include <stdexcept>
#include <utility>

namespace ProcessLib::MechanicalInterface
{
MechanicalInterfaceStateManager::MechanicalInterfaceStateManager(
    std::size_t const number_of_pairs)
    : committed_history_(number_of_pairs), trial_response_(number_of_pairs)
{
    rollbackTimeStep();
}

void MechanicalInterfaceStateManager::checkPairId(
    std::size_t const pair_id) const
{
    if (pair_id >= size())
    {
        throw std::out_of_range("Mechanical interface pair id out of range.");
    }
}

History const& MechanicalInterfaceStateManager::committedHistory(
    std::size_t const pair_id) const
{
    checkPairId(pair_id);
    return committed_history_[pair_id];
}

Response const& MechanicalInterfaceStateManager::trialResponse(
    std::size_t const pair_id) const
{
    checkPairId(pair_id);
    return trial_response_[pair_id];
}

void MechanicalInterfaceStateManager::setTrialResponse(
    std::size_t const pair_id, Response response)
{
    checkPairId(pair_id);
    trial_response_[pair_id] = std::move(response);
}

void MechanicalInterfaceStateManager::commitTimeStep()
{
    for (std::size_t pair_id = 0; pair_id < size(); ++pair_id)
    {
        committed_history_[pair_id] =
            trial_response_[pair_id].updated_history;
    }
}

void MechanicalInterfaceStateManager::rollbackTimeStep()
{
    for (std::size_t pair_id = 0; pair_id < size(); ++pair_id)
    {
        trial_response_[pair_id] = Response{};
        trial_response_[pair_id].updated_history = committed_history_[pair_id];
    }
}
}  // namespace ProcessLib::MechanicalInterface
