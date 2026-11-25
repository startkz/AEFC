function [est,status,diagnostic] = aefc_native_interval_observer(prior,model,u_previous,y,opts)
% Robust interval observer (linear discrete state abstraction).
% If the full physical state of an underlying nonlinear/DAE IEEE39 system
% is *not* covered by a verified affine interval abstraction, status=-90
% and coverage_verified=false. Never infer full state from simulator xout.
%
% Certified conditional recurrence:
%   x+ = A*x + B*(u+a) + c + w, |a|<=a_bound, |w|<=w_bound
%   y+ = H*x+ + v, |v|<=sensor_error
% Propagate [center +/- radius] by |A|, |B|, then intersect with sensor
% slabs using outward interval operations, preserving all feasible x+.
% MATLAB FP roundoff is not directed; add certified rounding inflation
% before relying on floating-point proof outside synthetic test.
est=struct('center',[],'error',[],'coverage_verified',false);
status=-90;
diagnostic=struct('consistent',false,'n_measurements',0,'max_width',inf, ...
    'proof_scope','CONDITIONAL VERIFIED DISCRETE AFFINE MODEL ONLY', ...
    'full_ieee39_network_certified',false);
if ~isstruct(prior) || ~isstruct(model) || ...
        ~isfield(prior,'coverage_verified') || ~logical(prior.coverage_verified) || ...
        ~isfield(model,'full_state_dynamics_verified') || ...
        ~logical(model.full_state_dynamics_verified) || ...
        ~isfield(model,'measurement_map_verified') || ...
        ~logical(model.measurement_map_verified)
    return;
end
needed={'A','B','c','w_bound','input_attack_bound','H','sensor_error'};
for k=1:numel(needed)
    if ~isfield(model,needed{k}),status=-91;return;end
end
if ~isfield(prior,'center') || ~isfield(prior,'error'),status=-91;return;end
x=double(prior.center(:));e=double(prior.error(:));
A=double(model.A);B=double(model.B);c=double(model.c(:));
w=double(model.w_bound(:));atk=double(model.input_attack_bound(:));
H=double(model.H);v=double(model.sensor_error(:));
u=double(u_previous(:));y=double(y(:));
n=numel(x);m=numel(u);p=numel(y);
if ~isequal(size(A),[n n]) || ~isequal(size(B),[n m]) || ...
        ~isequal(size(H),[p n]) || ...
        any([numel(e),numel(c),numel(w)]~=n) || ...
        numel(atk)~=m || numel(v)~=p || ...
        any(~isfinite([x;e;A(:);B(:);H(:);c;w;atk;v;u;y])) || ...
        any(e<0) || any(w<0) || any(atk<0) || any(v<0)
    status=-92;return;
end
center=A*x+B*u+c;
radius=abs(A)*e+abs(B)*atk+w;
if isstruct(opts) && isfield(opts,'roundoff_inflation')
    inflate=double(opts.roundoff_inflation);
    if ~isscalar(inflate) || ~isfinite(inflate) || inflate<0,status=-92;return;end
    radius=radius+inflate;
end
low=center-radius;high=center+radius;
passes=3;
if isstruct(opts) && isfield(opts,'max_passes')
    passes=max(1,min(12,round(double(opts.max_passes))));
end
for iter=1:passes
    for i=1:p
        row=H(i,:);
        % Compute y feasibility on current interval.
        mn=sum(max(row,0)'.*low+min(row,0)'.*high);
        mx=sum(max(row,0)'.*high+min(row,0)'.*low);
        if mn>y(i)+v(i)+1e-10 || mx<y(i)-v(i)-1e-10
            status=-93;return; % inconsistent model/measurement -> fail closed
        end
        for j=1:n
            a=row(j);
            if abs(a)<=1e-15,continue;end
            r=row;r(j)=0;
            othersMin=sum(max(r,0)'.*low+min(r,0)'.*high);
            othersMax=sum(max(r,0)'.*high+min(r,0)'.*low);
            if a>0
                lo=(y(i)-v(i)-othersMax)/a;
                hi=(y(i)+v(i)-othersMin)/a;
            else
                lo=(y(i)+v(i)-othersMin)/a;
                hi=(y(i)-v(i)-othersMax)/a;
            end
            low(j)=max(low(j),lo);
            high(j)=min(high(j),hi);
            if low(j)>high(j)+1e-10
                status=-93;return;
            end
        end
    end
end
if any(low>high) || any(~isfinite([low;high]))
    status=-93;return;
end
est.center=(low+high)/2;
est.error=(high-low)/2;
est.coverage_verified=true;
diagnostic.consistent=true;
diagnostic.n_measurements=p;
diagnostic.max_width=max(high-low);
status=1;
end
