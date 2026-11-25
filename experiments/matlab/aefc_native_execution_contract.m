function [u,status,margin,work,proxyAuthorized] = aefc_native_execution_contract(z,proposal,fallback,Bn,cfg,strictMode)
% Explicit *four-speed surrogate* affine constraint checker for native IEEE39.
% No full-state certificate can be obtained from four speed measurements,
% an unbounded full-state estimation error, and a local finite-difference B.
% Returned positive status means ONLY proxy feasibility, NEVER full-state CBF.
% With strictMode=true, do not release an uncertified recovery correction.
% Does not certify default original power-system governor behavior.
z=double(z(:)); proposal=double(proposal(:)); fallback=double(fallback(:)); Bn=double(Bn);
u=zeros(4,1);status=-10;margin=NaN;work=0;proxyAuthorized=false;
if ~isequal(size(Bn),[4 4]) || numel(z)~=4 || numel(proposal)~=4 || ...
        numel(fallback)~=4 || any(~isfinite([z;proposal;fallback;Bn(:)]))
    status=-11;return;
end
if ~isfield(cfg,'native_contract')
    status=-12;return;
end
c=cfg.native_contract;
if ~isfield(c,'state_measurement_error_normalized') || ...
        ~isfield(c,'surrogate_prediction_residual') || ...
        ~isfield(c,'post_shield_attack_upper')
    status=-12;return;
end
% These are *candidate surrogate budgets*, not validated IEEE39 coverage.
err=double(c.state_measurement_error_normalized);
residual=double(c.surrogate_prediction_residual);
post=double(c.post_shield_attack_upper);
ub=double(cfg.action_limit)-post;
if ~(isfinite(err)&&isfinite(residual)&&isfinite(post)&&err>=0&&residual>=0&&post>=0&&ub>=0)
    status=-12;return;
end
sigma=(err+residual)*ones(4,1)+sum(abs(Bn),2)*post;
safe=max(0,double(cfg.normalized_safe_limit)-double(cfg.shield_reserve));
if any(abs(z)+err>safe+1e-10)
    status=-13;return; % current observable box outside inner admissible proxy
end
A=[Bn;-Bn;eye(4);-eye(4)];
b=[safe*ones(4,1)-sigma-z;safe*ones(4,1)-sigma+z; ...
   ub*ones(4,1);ub*ones(4,1)];
tol=1e-9; bestStatus=-10;
trial=[min(max(proposal,-ub),ub),min(max(fallback,-ub),ub),zeros(4,1)];
for k=1:3
    v=trial(:,k);work=work+1;
    if max(A*v-b)<=tol
        u=v;bestStatus=k;break
    end
end
if bestStatus<0
    % Cyclic halfspace projection, followed by a non-negotiable hard check.
    v=trial(:,1);
    for it=1:150
        for k=1:size(A,1)
            vdiff=A(k,:)*v-b(k);
            if vdiff>0
                v=v-(vdiff/(sum(A(k,:).^2)+1e-18))*A(k,:)';
            end
        end
        work=work+1;
        if max(A*v-b)<=tol
            u=v;bestStatus=4;break
        end
    end
end
if bestStatus<0
    u=zeros(4,1);status=-10;return;
end
margin=min(b-A*u);
proxyAuthorized=true;
if strictMode
    % Full-state observation and validated nonlinear reachability absent.
    % Releasing a correction would misrepresent the theorem assumptions.
    u=zeros(4,1);status=-30;return;
end
% In diagnostic mode allow surrogate-screened exploratory corrections.
% These are *not* certified full IEEE39, even if margin>0.
status=bestStatus;
end
