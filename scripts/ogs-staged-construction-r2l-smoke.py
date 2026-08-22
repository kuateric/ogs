#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
source = root / "staged-r2l-smoke.cpp"
source.write_text(r'''#include <cmath>
#include <stdexcept>
#include <vector>

#include "ProcessLib/StagedConstruction/MechanicalRemovalTransition.h"

int main()
{
    using ProcessLib::StagedConstruction::MechanicalRemovalTransition;
    MechanicalRemovalTransition t({1, 4}, {8.0, -4.0});
    if (t.releaseCoordinate() != 0.0) return 1;
    auto f0 = t.currentForce();
    if (std::abs(f0[0] - 8.0) > 1e-14 || std::abs(f0[1] + 4.0) > 1e-14) return 2;

    t.setReleaseCoordinate(0.25);
    auto f25 = t.currentForce();
    if (std::abs(f25[0] - 6.0) > 1e-14 || std::abs(f25[1] + 3.0) > 1e-14) return 3;

    t.setReleaseCoordinate(0.75);
    auto f75 = t.currentForce();
    if (std::abs(f75[0] - 2.0) > 1e-14 || std::abs(f75[1] + 1.0) > 1e-14) return 4;

    bool rejected_backwards = false;
    try { t.setReleaseCoordinate(0.5); }
    catch (std::out_of_range const&) { rejected_backwards = true; }
    if (!rejected_backwards) return 5;

    t.setReleaseCoordinate(1.0);
    if (!t.isFullyReleased()) return 6;
    auto f1 = t.currentForce();
    if (std::abs(f1[0]) > 1e-14 || std::abs(f1[1]) > 1e-14) return 7;
    return 0;
}
''', encoding="utf-8")
print(source)
