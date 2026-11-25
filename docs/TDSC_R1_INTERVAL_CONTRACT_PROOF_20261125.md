# Conditional one-step safety contract for the TDSC-R1 hydraulic SIL

**Status:** mathematical inclusion argument for the *actual discrete six-state* `HydroPlant.step` in `run_hydro_valve_cps.py`, as implemented by `interval_step`. It is **not** a continuous-time CBF/CLF theorem, an IEEE39 system certificate, or evidence of physical PLC/hardware correctness.

## Assumptions and boundary

Let the physical state be `x=(h,q1,q2,omega,alpha1,alpha2)`. At each release step, an independent local sensor reports `y_loc` with known componentwise absolute error `eps`, so the *true* state is in `[xhat-eps,xhat+eps]`. In the simulator, the local sensor error is generated from a bounded uniform tape; a real installation would need separate integrity/coverage validation.

The physical transition is exactly the original Euler `HydroPlant.step`. Assume positive head `h>0.2`, nonnegative flows and valve openings, `0<dt/q_tau<=1`, and `0<=dt*turbine_damping/turbine_inertia<=1`. Downstream command corruption satisfies `|a^u_j|<=M`; the executed valve command is saturated to `[0,1]`. Inflow and load lie in declared bounded intervals. The simulation also draws unbounded Gaussian load/inflow noise; therefore coverage of **each realized draw** must be checked retrospectively and is not a universal stochastic guarantee.

An emitted nominal command satisfies `M<=u_j<=1-M`, so its entire corrupted interval stays inside actuator input limits. The state-safe box is the original `Config.state_lower/state_upper`.

## Interval successor construction

Denote lower and upper endpoints of a variable by subscripts `L,H`. All clip and positive square-root operations are monotone.

1. The executed input is enclosed by `u^exec_j in [u_j-M,u_j+M]`. For each valve, rate bounds are `r_L=clip((u_j-M-alpha_H)/tau_a,-rmax,rmax)` and `r_H=clip((u_j+M-alpha_L)/tau_a,-rmax,rmax)`. Thus the new opening lies in `[clip(alpha_L+dt*r_L,0,1),clip(alpha_H+dt*r_H,0,1)]`.
2. The stationary branch flow `q_ss,j=c_j alpha^+_j sqrt(max(h,0.2))` is bounded by multiplying nonnegative interval endpoints. Since `beta=dt/q_tau in (0,1]`, the actual flow `q^+_j=(1-beta)q_j+beta q_ss,j` lies in the endpoint-wise convex combination of both intervals.
3. Reservoir head `h^+=h+dt/A(q_in-sum_j q^+_j)` lies between the old head plus lower inflow minus upper flows and the old head plus upper inflow minus lower flows. The new mechanical power is enclosed by `eta*h^+*sum_j q^+_j` using the resulting nonnegative intervals.
4. Because the new-speed coefficient `1-dt*damping/inertia` is nonnegative, the turbine-speed successor `omega^+` is enclosed by the corresponding monotone affine combination of old-speed, power and load bounds.

Therefore the Cartesian product returned by `interval_step` contains every possible next state of the original discrete plant under these premises. This enclosure can be conservative; it need not be the exact reachable set.

## Conditional sampled safety proposition

**Proposition.** If the current physical state is inside the declared local-sensor uncertainty box, the box is inside the hard state-safe set, all actual disturbances/command attacks satisfy their declared bounds, the model assumptions above hold, and the supervisor releases a command only when the entire `interval_step` enclosure lies inside the safe box, then the next *sampled* physical state lies in the safe box.

**Proof.** Inclusion of the actual one-step successor in the interval enclosure follows from the four monotonicity/interval rules above. Certification encloses that entire successor interval in the physical safe box. Hence the actual successor belongs to the safe box. Iteration yields sampled-state invariance for every step in which the premises and release condition continue to hold.

**Fail-closed semantics.** If no finite candidate passes certification within the declared search budget, the software **does not release any command** and records a contract failure. This is not proof that all possible safe controls are infeasible: the command grid is finite. It does not guarantee the physical plant remains safe after a missed deadline, when control must be provided by a separately certified physical emergency system. The simulator stops that episode; it never imputes a safe continuation.

## What the reproducibility audit checks

The separate trace auditor independently recomputes sensor coverage, exogenous coverage, the original `predict_next` transition, the robust successor inclusion, the full certified margin, actuator bounds, sampled safety, and the physical recovery predicate for every released command. It cross-checks logged statuses and SHA-256 original JSONL bytes.

These checks support the above **conditional discrete mathematical contract** under the given SIL plant and explored input draws, not the stronger TDSC paper assertion about continuous-time invariance or a real IEEE39 network with uncertain full-state estimation.

## Open theoretical/experimental gap

A native IEEE39 robust CBF/CLF certificate requires validated complete state-estimation uncertainty sets, generator/actuator dynamics and attack envelopes, safe-constraint feasible QP counterparts, solver timing and backup feasibility, and hold-interval reachability. Nothing here should be silently promoted to those properties.
