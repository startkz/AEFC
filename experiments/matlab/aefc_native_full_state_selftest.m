function aefc_native_full_state_selftest
% Deterministic validation of conditional *synthetic affine* robust contract.
% Deliberately NOT an IEEE39 plant certificate or nonlinear model proof.
rng(20261125);
est=struct('center',[0.10;-0.08], 'error',[0.015;0.02], ...
    'coverage_verified',true);
mdl=struct('A',[0.98 0.01;0.01 0.97], 'B',[0.3 0.02;0.01 0.26],...
    'c',[0;0], 'w_bound',[0.01;0.015], ...
    'input_attack_bound',[0.02;0.02], ...
    'safe_lower',[-0.5;-0.5], 'safe_upper',[0.5;0.5], ...
    'input_lower',[-0.3;-0.3], 'input_upper',[0.3;0.3], ...
    'full_state_dynamics_verified',true);
[u,status,margin,~]=aefc_native_full_state_contract(est,mdl,[0.1;-0.1],[0;0],struct('strict',true));
assert(status>0 && margin>=-1e-10,'AEFC:FullStateTest','Synthetic feasible contract failed');
for k=1:500
    xt=est.center+est.error.*(2*rand(2,1)-1);
    attack=mdl.input_attack_bound.*(2*rand(2,1)-1);
    w=mdl.w_bound.*(2*rand(2,1)-1);
    xn=mdl.A*xt+mdl.B*(u+attack)+mdl.c+w;
    assert(all(xn>=mdl.safe_lower-1e-9) && all(xn<=mdl.safe_upper+1e-9), ...
        'AEFC:FullStateTest','Robust affine enclosure fails for held test point');
end
est.coverage_verified=false;
[~,status]=aefc_native_full_state_contract(est,mdl,[0;0],[0;0],struct('strict',true));
assert(status==-90,'AEFC:FullStateTest','No-coverage model must fail closed');
est.coverage_verified=true;
mdl.full_state_dynamics_verified=false;
[~,status]=aefc_native_full_state_contract(est,mdl,[0;0],[0;0],struct('strict',true));
assert(status==-90,'AEFC:FullStateTest','Unverified dynamics must fail closed');
fprintf('AFFINE FULL-STATE SELFTEST PASS (synthetic two-state only; IEEE39 unverified)\\n');
end
