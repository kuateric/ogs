// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#include <gtest/gtest.h>

#include "ProcessLib/SmallDeformation/ElementActivationState.h"

TEST(ProcessLibSmallDeformation, ElementActivationStateDefaultActive)
{
    ProcessLib::SmallDeformation::ElementActivationState state;
    EXPECT_TRUE(state.isActive(0));
    EXPECT_TRUE(state.isActive(123));
}

TEST(ProcessLibSmallDeformation, ElementActivationStateRejectRetry)
{
    ProcessLib::SmallDeformation::ElementActivationState state;
    state.initialize({1, 1, 0});
    EXPECT_TRUE(state.isActive(0));
    EXPECT_FALSE(state.isActive(2));

    state.setCandidate({0, 1, 1});
    EXPECT_FALSE(state.candidateIsActive(0));
    EXPECT_TRUE(state.isActive(0));  // accepted state unchanged during trial

    state.rollback();
    EXPECT_TRUE(state.candidateIsActive(0));
    EXPECT_FALSE(state.candidateIsActive(2));

    state.setCandidate({0, 1, 1});
    state.commit();
    EXPECT_FALSE(state.isActive(0));
    EXPECT_TRUE(state.isActive(2));
}
