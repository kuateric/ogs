#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

# The SmallDeformation process uses AssemblyMixin, whose active assembly path is
# ParallelVectorMatrixAssembler (PVMA), not Process::_global_assembler.  R2H's
# first observer hook therefore compiled but never saw runtime element residuals.
# Wire the same behavior-neutral observer into PVMA, with serialization around
# the callback because element assembly can run on several OpenMP threads.

h = root / "ProcessLib/Assembly/ParallelVectorMatrixAssembler.h"
text = h.read_text(encoding="utf-8")
if '#include <functional>\n' not in text:
    text = text.replace('#pragma once\n\n', '#pragma once\n\n#include <functional>\n#include <mutex>\n#include <vector>\n\n')

public_anchor = '''    explicit ParallelVectorMatrixAssembler(
        AbstractJacobianAssembler& jacobian_assembler);
'''
public_add = public_anchor + '''
    using LocalResidualObserver =
        std::function<void(std::size_t, std::vector<double> const&)>;

    void setLocalResidualObserver(LocalResidualObserver observer)
    {
        local_residual_observer_ = std::move(observer);
    }
'''
if public_anchor not in text:
    raise RuntimeError("Unexpected ParallelVectorMatrixAssembler public layout")
if 'using LocalResidualObserver =' not in text:
    text = text.replace(public_anchor, public_add)

private_anchor = '''    int const num_threads_;
};
'''
private_add = '''    int const num_threads_;

    LocalResidualObserver local_residual_observer_;
    std::mutex local_residual_observer_mutex_;
};
'''
if private_anchor not in text:
    raise RuntimeError("Unexpected ParallelVectorMatrixAssembler private layout")
if 'local_residual_observer_mutex_' not in text:
    text = text.replace(private_anchor, private_add)
h.write_text(text, encoding="utf-8")

cpp = root / "ProcessLib/Assembly/ParallelVectorMatrixAssembler.cpp"
text = cpp.read_text(encoding="utf-8")

mono_output = '''        auto local_matrix_output = [&](std::ptrdiff_t element_id)
        {
            local_matrix_output_(t, process_id, element_id, local_M_data,
                                 local_K_data, local_b_data);
        };
'''
mono_repl = '''        auto local_matrix_output = [&](std::ptrdiff_t element_id)
        {
            if (local_residual_observer_ && !local_b_data.empty())
            {
                std::lock_guard lock(local_residual_observer_mutex_);
                local_residual_observer_(element_id, local_b_data);
            }
            local_matrix_output_(t, process_id, element_id, local_M_data,
                                 local_K_data, local_b_data);
        };
'''
if text.count(mono_output) != 1:
    raise RuntimeError("Unexpected PVMA assemble local output layout")
text = text.replace(mono_output, mono_repl)

jac_output = '''        auto local_matrix_output = [&](std::ptrdiff_t element_id)
        {
            local_matrix_output_(t, process_id, element_id, local_b_data,
                                 local_Jac_data);
        };
'''
jac_repl = '''        auto local_matrix_output = [&](std::ptrdiff_t element_id)
        {
            if (local_residual_observer_ && !local_b_data.empty())
            {
                std::lock_guard lock(local_residual_observer_mutex_);
                local_residual_observer_(element_id, local_b_data);
            }
            local_matrix_output_(t, process_id, element_id, local_b_data,
                                 local_Jac_data);
        };
'''
if text.count(jac_output) != 1:
    raise RuntimeError("Unexpected PVMA Jacobian local output layout")
text = text.replace(jac_output, jac_repl)
cpp.write_text(text, encoding="utf-8")

mixin = root / "ProcessLib/AssemblyMixin.h"
text = mixin.read_text(encoding="utf-8")
anchor = '''    void updateActiveElements()
    {
        AssemblyMixinBase::updateActiveElements(derived());
    }
'''
addition = anchor + '''

    void setAssemblyLocalResidualObserver(
        Assembly::ParallelVectorMatrixAssembler::LocalResidualObserver observer)
    {
        pvma_.setLocalResidualObserver(std::move(observer));
    }
'''
if anchor not in text:
    raise RuntimeError("Unexpected AssemblyMixin updateActiveElements layout")
if 'setAssemblyLocalResidualObserver' not in text:
    text = text.replace(anchor, addition)
mixin.write_text(text, encoding="utf-8")

sd = root / "ProcessLib/SmallDeformation/SmallDeformationProcess.cpp"
text = sd.read_text(encoding="utf-8")
old = '''    this->setLocalResidualObserver(
'''
new = '''    this->setAssemblyLocalResidualObserver(
'''
if text.count(old) != 1:
    raise RuntimeError("Expected exactly one SmallDeformation residual observer hookup")
text = text.replace(old, new)
sd.write_text(text, encoding="utf-8")

print("Applied R2K-F01: residual observer wired to active AssemblyMixin/PVMA path")
