function [u,status,margin,work] = aefc_native_full_state_contract(est,mdl,proposal,backup,opts)
% Generic DISCRETE FULL-STATE robust-affine execution contract.
% This is NOT active for native IEEE39 until its entire state and error
% coverage have been established and traceably versioned. Never infer
% coverage from a four-rotor-speed sensitivity matrix.
%
% est.center: n-by-1 measured/estimated physical state
% est.error: n-by-1 certified componentwise state-estimation error
% est.coverage_verified: externally certified full-state coverage
% mdl.A(n,n), B(n,m), c(n,1), w_bound(n,1): discrete transition
% mdl.input_attack_bound(m,1): post-shield command perturbation
% mdl.safe_lower/upper(n,1), input_lower/upper(m,1)
% mdl.full_state_dynamics_verified: externally verified model coverage
% opts.strict requires all validation flags; output status 1..3 or negative
% Completion of this function is a CONDITIONAL proof of sampled next-state
% inclusion only; hold-interval continuous safety requires an extra tube.
u=zeros(numel(proposal),1);status=-90;margin=NaN;work=0;
if nargin<5 || ~isstruct(opts),status=-91;return;end
if ~isfield(est,'coverage_verified') || ~logical(est.coverage_verified) || ...
        ~isfield(mdl,'full_state_dynamics_verified') || ...
        ~logical(mdl.full_state_dynamics_verified)
    status=-90;return; % NO state/model certificate: release forbidden
end
fieldsEst={'center','error'};
fieldsModel={'A','B','c','w_bound','input_attack_bound', ...
    'safe_lower','safe_upper','input_lower','input_upper'};
for j=1:numel(fieldsEst)
    if ~isfield(est,fieldsEst{j}),status=-92;return;end
end
for j=1:numel(fieldsModel)
    if ~isfield(mdl,fieldsModel{j}),status=-92;return;end
end
x=double(est.center(:));e=double(est.error(:));
A=double(mdl.A);B=double(mdl.B);c=double(mdl.c(:));
w=double(mdl.w_bound(:));atk=double(mdl.input_attack_bound(:));
lo=double(mdl.safe_lower(:));hi=double(mdl.safe_upper(:));
ulo=double(mdl.input_lower(:));uhi=double(mdl.input_upper(:));
proposal=double(proposal(:));backup=double(backup(:));
n=numel(x);m=numel(proposal);
if ~isequal(size(A),[n n]) || ~isequal(size(B),[n m]) || ...
        any([numel(e),numel(c),numel(w),numel(lo),numel(hi)]~=n) ||...
        any([numel(atk),numel(ulo),numel(uhi),numel(backup)]~=m) || ...
        any(~isfinite([x;e;A(:);B(:);c;w;atk;lo;hi;ulo;uhi;proposal;backup])) || ...
        any(e<0) || any(w<0) || any(atk<0) || ...
        any(lo>hi) || any(ulo>uhi)
    status=-92;return;
end
if any(x-e<lo) || any(x+e>hi)
    status=-93;return; % state-uncertainty box cannot be declared safe
end
% Exact robust box counterpart for affine next state:
% all x in [center ± error], all attack inputs ±atk, all |w|<=w_bound.
sigma=abs(A)*e+abs(B)*atk+w;
center=A*x+c;
lower=ulo+atk;upper=uhi-atk;
if any(lower>upper)
    status=-94;return;
end
P=[B;-B;eye(m);-eye(m)];
q=[hi-sigma-center;center-lo-sigma;upper;-lower];
candidate=[min(max(proposal,lower),upper), ...
           min(max(backup,lower),upper),...
           min(max(zeros(m,1),lower),upper)];
tol=1e-10;
chosen=-1;u=zeros(m,1);
for k=1:3
    v=candidate(:,k);work=work+1;
    if max(P*v-q)<=tol,u=v;chosen=k;break;end
end
if chosen<0
    % Deterministic iterative halfspace projection; accept ONLY after
    % independently verifying every robust hard inequality.
    v=candidate(:,1);
    for it=1:250
        for k=1:size(P,1)
            vdiff=P(k,:)*v-q(k);
            if vdiff>0,v=v-(vdiff/(sum(P(k,:).^2)+1e-20))*P(k,:)';end
        end
        work=work+1;
        if max(P*v-q)<=tol,u=v;chosen=4;break;end
    end
end
if chosen<0,u=zeros(m,1);status=-95;return;end
margin=min(q-P*u);
if ~(isfinite(margin) && margin>=-tol)
    u=zeros(m,1);status=-96;margin=NaN;return;
end
status=chosen;
end
