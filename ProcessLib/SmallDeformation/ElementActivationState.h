// SPDX-FileCopyrightText: Copyright (c) OpenGeoSys Community (opengeosys.org)
// SPDX-License-Identifier: BSD-3-Clause

#pragma once

#include <cstddef>
#include <vector>

namespace ProcessLib::SmallDeformation
{
/// Accepted/candidate element activation state for staged SmallDeformation.
///
/// Default construction is behavior preserving: when no explicit state is
/// configured all elements are active. Candidate changes are isolated from the
/// accepted state until commit(), so nonlinear rejection/cutback can rollback
/// without changing the accepted staging reference.
class ElementActivationState
{
public:
    bool isActive(std::size_t const element_id) const
    {
        return accepted_.empty() || accepted_[element_id] != 0;
    }

    bool candidateIsActive(std::size_t const element_id) const
    {
        return candidate_.empty() ? isActive(element_id)
                                  : candidate_[element_id] != 0;
    }

    void initialize(std::vector<unsigned char> active)
    {
        accepted_ = std::move(active);
        candidate_ = accepted_;
    }

    void setCandidate(std::vector<unsigned char> active)
    {
        candidate_ = std::move(active);
    }

    void commit()
    {
        if (!candidate_.empty())
        {
            accepted_ = candidate_;
        }
    }

    void rollback() { candidate_ = accepted_; }

private:
    std::vector<unsigned char> accepted_;
    std::vector<unsigned char> candidate_;
};
}  // namespace ProcessLib::SmallDeformation
