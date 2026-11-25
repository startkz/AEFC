function [command,nextMemory,diag] = aefc_native_certified_execution_step(memory, ...
        model,previous_command,measurement,proposal,backup,options)
% Fully staged execution for a verified state-estimator plus reachability
% contract. Never reads offline Simulink state snapshots/attack labels.
% Integration specification for native IEEE39: every flag MUST be supported
% by a separately verified non-oracle state/model/hold-interval certificate.
%
% This code is NOT active as a full 39-bus safety cert until the official
% native state inventory has mapped all safety-relevant dynamic/algebraic
% states and admissible disturbances.
command=zeros(numel(proposal),1);
nextMemory=memory;
diag=struct('status',-210,'observer_status',-90,'solver_status',-90, ...
    'certified',false,'backup_executed',false,'margin',NaN, ...
    'input_authorized',false,'full_state_covered',false, ...
    'intersample_safe',false,'n_state_dimensions',0);
required={'full_network_variables_covered','safety_predicates_all_covered', ...
          'full_state_dynamics_verified','measurement_map_verified', ...
          'intersample_reachability_verified','verified_emergency_policy'};
if ~isstruct(model)
    return;
end
for k=1:numel(required)
    if ~isfield(model,required{k}) || ~logical(model.(required{k}))
        return;
    end
end
if ~isstruct(memory) || ~isfield(memory,'coverage_verified') || ...
        ~logical(memory.coverage_verified) || ...
        ~isfield(options,'roundoff_inflation') || ...
        ~(isnumeric(options.roundoff_inflation) && ...
          isscalar(options.roundoff_inflation) && ...
          isfinite(options.roundoff_inflation) && ...
          options.roundoff_inflation>0)
    diag.status=-211;return;
end
[est,ostatus,~]=aefc_native_interval_observer( ...
    memory,model,previous_command,measurement,options);
diag.observer_status=ostatus;
if ostatus~=1
    diag.status=-220;return;
end
nextMemory=est;
diag.n_state_dimensions=numel(est.center);
diag.full_state_covered=true;
[proposal_safe,solverStatus,margin,~]=aefc_native_full_state_contract( ...
    est,model,proposal,backup,options);
diag.solver_status=solverStatus;
diag.margin=margin;
if solverStatus<=0
    diag.status=-230;return;
end
command=proposal_safe;
diag.certified=true;
diag.input_authorized=true;
diag.intersample_safe=true; % externally verified tube assumption mandatory
diag.backup_executed=(solverStatus==2 || solverStatus==3);
diag.status=solverStatus;
end
