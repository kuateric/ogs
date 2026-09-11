// SPDX-License-Identifier: BSD-3-Clause

#include "G5ProjectScaleActivationGate.h"

#include <cassert>

int main()
{
    using ProcessLib::SmallDeformation::G5ProjectScale::assembleElement;
    static_assert(assembleElement(true));
    static_assert(!assembleElement(false));
    assert(assembleElement(true));
    assert(!assembleElement(false));
    return 0;
}
