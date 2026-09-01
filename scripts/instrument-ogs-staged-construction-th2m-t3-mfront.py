#!/usr/bin/env python3
from pathlib import Path

# TH2M-T3 CI-only instrumentation mirrors the already-authoritative T2D
# MFront/MGIS probes, but emits T3-specific evidence labels. It does not change
# constitutive behaviour, state initialization semantics, tolerances, time
# stepping, or the physical TH2M operator.
p = Path('MaterialLib/SolidModels/MFront/MFrontGeneric.h')
text = p.read_text(encoding='utf-8')

alloc = """    createMaterialStateVariables() const
    {
        return std::make_unique<MaterialStateVariablesMFront<DisplacementDim>>(
            equivalent_plastic_strain_offset_, _behaviour);
    }"""
alloc_probe = """    createMaterialStateVariables() const
    {
        INFO(\"TH2M-T3 MFront/MGIS fresh BehaviourData allocation\");
        return std::make_unique<MaterialStateVariablesMFront<DisplacementDim>>(
            equivalent_plastic_strain_offset_, _behaviour);
    }"""
if text.count(alloc) != 1:
    raise RuntimeError('canonical MFront state-allocation anchor changed')
text = text.replace(alloc, alloc_probe, 1)

init = """        auto& state =
            static_cast<MaterialStateVariablesMFront<DisplacementDim>&>(
                material_state_variables);

        auto const& ivs = getInternalVariables();"""
init_probe = """        auto& state =
            static_cast<MaterialStateVariablesMFront<DisplacementDim>&>(
                material_state_variables);
        INFO(\"TH2M-T3 MFront/MGIS virgin state initializer at t = {:g}\", t);

        auto const& ivs = getInternalVariables();"""
if text.count(init) != 1:
    raise RuntimeError('canonical MFront initializer anchor changed')
text = text.replace(init, init_probe, 1)

p.write_text(text, encoding='utf-8')

# R3 diagnostic only: trace the physical gravity contribution where canonical
# TH2M adds it to the mechanical local right-hand side. Abaqus progressive
# activation applies element loads when an element becomes active; this probe
# checks whether the equivalent full-operator load path is present here before
# any global Dirichlet elimination. No residual or tangent is modified.
p = Path('ProcessLib/TH2M/TH2MFEM-impl.h')
text = p.read_text(encoding='utf-8')
anchor = """        fU.noalias() -=
            (Bu.transpose() * current_state.eff_stress_data.sigma_eff -
             N_u_op(Nu).transpose() * ip_cv.volumetric_body_force()) *
            w;
"""
probe = """        fU.noalias() -=
            (Bu.transpose() * current_state.eff_stress_data.sigma_eff -
             N_u_op(Nu).transpose() * ip_cv.volumetric_body_force()) *
            w;
        INFO(\"TH2M-T3 loaded assembly element {:d} t={:g} body_force_norm={:.17g} fU_norm={:.17g}\",
             this->element_.getID(), t,
             ip_cv.volumetric_body_force().norm(), fU.norm());
"""
count = text.count(anchor)
if count == 0:
    raise RuntimeError('canonical TH2M mechanical body-force assembly anchor changed')
# The implementation contains the same physical term in more than one assembly
# path. Instrument all occurrences so the runtime itself identifies which path
# the selected Jacobian assembler executes.
text = text.replace(anchor, probe)
p.write_text(text, encoding='utf-8')

# T3G diagnostic only: observe the global Newton right-hand side immediately
# after canonical TH2M AssemblyMixin assembly returns. Process-level boundary
# conditions are applied by the nonlinear-solver path after this callback, so
# this distinguishes loss during local-to-global assembly from later
# constraint/solver elimination. norm2() is read-only; no vector or Jacobian
# entry is changed.
p = Path('ProcessLib/TH2M/TH2MProcess.cpp')
text = p.read_text(encoding='utf-8')
anchor = """    AssemblyMixin<TH2MProcess<DisplacementDim>>::assembleWithJacobian(
        t, dt, x, x_prev, process_id, b, Jac);
"""
probe = """    AssemblyMixin<TH2MProcess<DisplacementDim>>::assembleWithJacobian(
        t, dt, x, x_prev, process_id, b, Jac);
    INFO(\"TH2M-T3G global Newton RHS before BC t={:g} norm2={:.17g}\",
         t, MathLib::LinAlg::norm2(b));
"""
if text.count(anchor) != 1:
    raise RuntimeError('canonical TH2M global Jacobian assembly anchor changed')
text = text.replace(anchor, probe, 1)
p.write_text(text, encoding='utf-8')

# T3H diagnostic only: follow the Newton residual across the canonical
# Dirichlet application and into the linear-solver update. These are read-only
# norm probes. They do not change the residual, Jacobian, known-solution set,
# linear solve, convergence criterion, or any physical/numerical parameter.
p = Path('NumLib/ODESolver/NonlinearSolver.cpp')
text = p.read_text(encoding='utf-8')
pre_bc = """        minus_delta_x.setZero();

        timer_dirichlet.start();
        sys.applyKnownSolutionsNewton(J, res, *x[process_id], minus_delta_x);
        time_dirichlet += timer_dirichlet.elapsed();
        INFO(\"[time] Applying Dirichlet BCs took {:g} s.\", time_dirichlet);
"""
pre_bc_probe = """        minus_delta_x.setZero();

        INFO(\"TH2M-T3H Newton residual before BC iteration={:d} norm2={:.17g}\",
             iteration, LinAlg::norm2(res));
        timer_dirichlet.start();
        sys.applyKnownSolutionsNewton(J, res, *x[process_id], minus_delta_x);
        time_dirichlet += timer_dirichlet.elapsed();
        INFO(\"TH2M-T3H Newton residual after BC iteration={:d} norm2={:.17g}\",
             iteration, LinAlg::norm2(res));
        INFO(\"TH2M-T3H prescribed minus_delta_x after BC iteration={:d} norm2={:.17g}\",
             iteration, LinAlg::norm2(minus_delta_x));
        INFO(\"[time] Applying Dirichlet BCs took {:g} s.\", time_dirichlet);
"""
if text.count(pre_bc) != 1:
    raise RuntimeError('canonical Newton Dirichlet anchor changed')
text = text.replace(pre_bc, pre_bc_probe, 1)

post_solve = """#endif
        INFO(\"[time] Linear solver took {:g} s.\", time_linear_solver.elapsed());

        if (!iteration_succeeded)
"""
post_solve_probe = """#endif
        INFO(\"TH2M-T3H Newton minus_delta_x after solve iteration={:d} norm2={:.17g}\",
             iteration, LinAlg::norm2(minus_delta_x));
        INFO(\"[time] Linear solver took {:g} s.\", time_linear_solver.elapsed());

        if (!iteration_succeeded)
"""
if text.count(post_solve) != 1:
    raise RuntimeError('canonical Newton linear-solve anchor changed')
text = text.replace(post_solve, post_solve_probe, 1)
p.write_text(text, encoding='utf-8')
