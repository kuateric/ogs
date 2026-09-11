# G5 project-scale native activation integration

Authority branch: `agent/g5-project-scale-native-activation-integration`
Parent SHA: `5470cea39521639b48d372a15d35aa2a6bde5788`
Frozen Engineering OS G5 RC: `790c22a0938f2c0b3a7e95a0dc7beff3c97683d7`

This branch is additive post-G5 project-scale integration work. It does not redefine roadmap G6 (Hydraulic Interface) and must not modify frozen G5 Mechanical Structural Interface V1 law semantics.

## Resolved native assembly boundary

`ProcessLib/SmallDeformation/SmallDeformationFEM.h`, `SmallDeformationLocalAssembler::assembleWithJacobian()` creates zero local residual/Jacobian storage before extracting `u/u_prev`, entering the integration-point loop, evaluating constitutive relations, and accumulating `B^T sigma` / `B^T C B` contributions.

Therefore an activation/deactivation assembly gate must be placed before `localDOF(local_x)`, constitutive evaluation, and any integration-point state mutation. For an inactive element the gate must return with exactly zero residual and Jacobian and no constitutive/material-history mutation.

## Time-step lifecycle contract

A converged nonlinear solution is only a candidate. Candidate capture must not commit activation reference state. Commit is permitted only at final accepted time-step handling; rejection/cutback must discard the candidate and restore the previously committed reference consistently with the native `x_prev -> x` rollback path.

## Required acceptance evidence

1. Frozen G5 law/source integrity remains byte-identical.
2. Unit/static test: inactive assembly returns exact zero residual/Jacobian and does not mutate material history.
3. Native rejection -> retry coupon: rejected converged candidate never becomes activation reference; retry accepted state does.
4. Exact native integration SHA is audited independently; implementation does not self-certify.
5. Only after 1-4 pass may the ULiège monolithic -> segmented PerfectBond -> finite-joint project-scale sequence proceed.

No automatic merge is authorized.
