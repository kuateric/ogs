#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()

header = root / "ProcessLib/VectorMatrixAssembler.h"
text = header.read_text(encoding="utf-8")

if '#include <functional>\n' not in text:
    text = text.replace('#include <vector>\n', '#include <functional>\n#include <vector>\n')

anchor = '''    void assembleWithJacobian(
        std::size_t const mesh_item_id,
        LocalAssemblerInterface& local_assembler,
        std::vector<NumLib::LocalToGlobalIndexMap const*> const& dof_tables,
        const double t, double const dt, std::vector<GlobalVector*> const& x,
        std::vector<GlobalVector*> const& x_prev, int const process_id,
        GlobalVector* b, GlobalMatrix* Jac);
'''
addition = anchor + '''
    using LocalResidualObserver =
        std::function<void(std::size_t, std::vector<double> const&)>;

    /// Optional observer of the exact local residual vector produced by the
    /// regular OGS assembly path.  Staged construction uses this to retain the
    /// converged pre-removal element action without re-integrating stresses or
    /// mutating constitutive state.  With no observer installed assembly is
    /// bit-for-bit behavior-neutral.
    void setLocalResidualObserver(LocalResidualObserver observer)
    {
        _local_residual_observer = std::move(observer);
    }
'''
if anchor not in text:
    raise RuntimeError("Unexpected VectorMatrixAssembler.h public layout")
text = text.replace(anchor, addition)

member_anchor = '''    Assembly::LocalMatrixOutput _local_output;
};
'''
member = '''    Assembly::LocalMatrixOutput _local_output;
    LocalResidualObserver _local_residual_observer;
};
'''
if member_anchor not in text:
    raise RuntimeError("Unexpected VectorMatrixAssembler.h member layout")
text = text.replace(member_anchor, member)
header.write_text(text, encoding="utf-8")

cpp = root / "ProcessLib/VectorMatrixAssembler.cpp"
text = cpp.read_text(encoding="utf-8")

needle_assemble = '''    _local_output(t, process_id, mesh_item_id, _local_M_data, _local_K_data,
                  _local_b_data);
}
'''
replacement_assemble = '''    if (_local_residual_observer && !_local_b_data.empty())
    {
        _local_residual_observer(mesh_item_id, _local_b_data);
    }

    _local_output(t, process_id, mesh_item_id, _local_M_data, _local_K_data,
                  _local_b_data);
}
'''
if text.count(needle_assemble) != 1:
    raise RuntimeError("Unexpected VectorMatrixAssembler::assemble tail")
text = text.replace(needle_assemble, replacement_assemble)

needle_jac = '''    _local_output(t, process_id, mesh_item_id, _local_b_data, _local_Jac_data);
}
'''
replacement_jac = '''    if (_local_residual_observer && !_local_b_data.empty())
    {
        _local_residual_observer(mesh_item_id, _local_b_data);
    }

    _local_output(t, process_id, mesh_item_id, _local_b_data, _local_Jac_data);
}
'''
if text.count(needle_jac) != 1:
    raise RuntimeError("Unexpected VectorMatrixAssembler::assembleWithJacobian tail")
text = text.replace(needle_jac, replacement_jac)
cpp.write_text(text, encoding="utf-8")

process_h = root / "ProcessLib/Process.h"
text = process_h.read_text(encoding="utf-8")
protected_anchor = '''    std::vector<NumLib::LocalToGlobalIndexMap const*> getDOFTables(
        int const number_of_processes) const;
'''
protected_addition = protected_anchor + '''

    /// Installs a behavior-neutral observer for element-local residual vectors
    /// produced by the regular assembly.  This is intentionally process-level
    /// plumbing; only processes that opt in pay any storage/capture cost.
    void setLocalResidualObserver(
        VectorMatrixAssembler::LocalResidualObserver observer)
    {
        _global_assembler.setLocalResidualObserver(std::move(observer));
    }
'''
if protected_anchor not in text:
    raise RuntimeError("Unexpected Process.h protected layout")
text = text.replace(protected_anchor, protected_addition)
process_h.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction R2H local residual observer plumbing")
