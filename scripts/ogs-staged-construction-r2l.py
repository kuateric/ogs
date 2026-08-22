#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
header = root / "ProcessLib/StagedConstruction/MechanicalRemovalTransition.h"
text = header.read_text(encoding="utf-8")

old = '''    std::vector<std::size_t> const& dofIDs() const { return _dof_ids; }
    std::vector<double> const& retainedForce() const { return _retained_force; }

    std::vector<double> forceAt(double const lambda) const
'''
new = '''    std::vector<std::size_t> const& dofIDs() const { return _dof_ids; }
    std::vector<double> const& retainedForce() const { return _retained_force; }

    /// Set the construction-continuation coordinate for controlled release.
    /// This coordinate is deliberately independent of physical simulation time.
    /// R2 permits monotonic externally controlled release; R3 will add adaptive
    /// advancement/cutback and transactional rollback around this state.
    void setReleaseCoordinate(double const lambda)
    {
        if (lambda < _release_coordinate || lambda > 1.0)
        {
            throw std::out_of_range(
                "Mechanical removal release coordinate must advance monotonically in [0, 1].");
        }
        _release_coordinate = lambda;
    }

    double releaseCoordinate() const { return _release_coordinate; }

    std::vector<double> currentForce() const
    {
        return forceAt(_release_coordinate);
    }

    bool isFullyReleased() const { return _release_coordinate == 1.0; }

    std::vector<double> forceAt(double const lambda) const
'''
if text.count(old) != 1:
    raise RuntimeError("Unexpected MechanicalRemovalTransition public API layout")
text = text.replace(old, new)

old_private = '''    std::vector<std::size_t> _dof_ids;
    std::vector<double> _retained_force;
'''
new_private = '''    std::vector<std::size_t> _dof_ids;
    std::vector<double> _retained_force;
    double _release_coordinate = 0.0;
'''
if text.count(old_private) != 1:
    raise RuntimeError("Unexpected MechanicalRemovalTransition private layout")
text = text.replace(old_private, new_private)
header.write_text(text, encoding="utf-8")

cpp = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = cpp.read_text(encoding="utf-8")
old_injection = '''        b.add(global_indices, transition.forceAt(0.0));
'''
new_injection = '''        b.add(global_indices, transition.currentForce());
'''
if text.count(old_injection) != 1:
    raise RuntimeError("Unexpected R2K retained-force injection layout")
cpp.write_text(text.replace(old_injection, new_injection), encoding="utf-8")

print("Applied OGS Staged Construction R2L controlled release coordinate")
