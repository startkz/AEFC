function [ok,margin,status] = aefc_native_hold_reachability(est,model,command)
% Conditional conservative continuous intersample envelope.
%
% If |dx_j/dt|<=F_j has been PROVEN for every state, every admissible
% disturbance/attack, and every s in [0,h] under the issued command,
%   x_j(t+s) in [xhat_j-e_j-h*F_j, xhat_j+e_j+h*F_j].
% The box must be inside the entire physical safe set. Pointwise discrete
% next-state inclusion alone does not imply this.
ok=false;margin=NaN;status=-90;
if ~isstruct(est) || ~isfield(est,'coverage_verified') || ...
   ~logical(est.coverage_verified) || ...
   ~isstruct(model) || ...
   ~isfield(model,'intersample_reachability_verified') || ...
   ~logical(model.intersample_reachability_verified) || ...
   ~isfield(model,'intersample_derivative_bounds_verified') || ...
   ~logical(model.intersample_derivative_bounds_verified)
    return;
end
fields={'hold_interval_seconds','intersample_derivative_bound', ...
        'safe_lower','safe_upper','input_lower','input_upper',...
        'input_attack_bound'};
for i=1:numel(fields)
    if ~isfield(model,fields{i}),status=-91;return;end
end
x=double(est.center(:));e=double(est.error(:));
f=double(model.intersample_derivative_bound(:));
lo=double(model.safe_lower(:));hi=double(model.safe_upper(:));
ul=double(model.input_lower(:));uh=double(model.input_upper(:));
a=double(model.input_attack_bound(:));
u=double(command(:)); h=double(model.hold_interval_seconds);
n=numel(x);m=numel(u);
if numel(e)~=n || numel(f)~=n || numel(lo)~=n || numel(hi)~=n || ...
        numel(a)~=m || numel(ul)~=m || numel(uh)~=m || ...
        ~isscalar(h) || h<=0 || ...
        any(~isfinite([x;e;f;lo;hi;ul;uh;a;u;h])) || ...
        any(e<0) || any(f<0) || any(a<0)
    status=-92;return;
end
if any(u-a<ul) || any(u+a>uh)
    status=-94;return;
end
lower=x-e-h*f;
upper=x+e+h*f;
margin=min([lower-lo;hi-upper]);
if margin<-1e-10
    status=-93;return;
end
ok=true;status=1;
end
