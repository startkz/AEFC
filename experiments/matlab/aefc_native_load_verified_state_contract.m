function [model,initialSet,status] = aefc_native_load_verified_state_contract(cfg)
% Load a REVIEWED native IEEE39 full-state envelope from immutable artifacts.
% Current repository deliberately does NOT ship such an artifact; until it
% exists all extra Pref control is blocked in strict certification mode.
% A MAT file or a JSON flag alone is NOT a physical proof: the referenced
% validation must independently establish every model/sensor/tube premise.
model=struct('full_network_variables_covered',false, ...
    'safety_predicates_all_covered',false, ...
    'full_state_dynamics_verified',false, ...
    'measurement_map_verified',false, ...
    'intersample_reachability_verified',false, ...
    'intersample_derivative_bounds_verified',false, ...
    'verified_emergency_policy',false);
initialSet=struct('center',[],'error',[],'coverage_verified',false);
status=-310;
if ~isstruct(cfg) || ~isfield(cfg,'fullstate_certificate_path')
    return;
end
path=char(cfg.fullstate_certificate_path);
if isempty(path) || exist(path,'file')~=2
    return;
end
try
    cert=jsondecode(fileread(path));
    if ~isfield(cert,'online_state_estimator') || ...
       ~logical(cert.online_state_estimator.coverage_verified) || ...
       ~logical(cert.sampled_reachable_tube.validated) || ...
       ~logical(cert.intersample_reachable_tube.validated) || ...
       ~logical(cert.backup.emergency_actuator_authority_verified) || ...
       ~logical(cert.backup.fallback_reachable_set_feasible) || ...
       ~logical(cert.backup.deadline_and_solver_timeout_verified) || ...
       ~logical(cert.backup.original_governors_independently_certified)
        status=-311;return;
    end
    preds=cert.required_predicates;
    if ~all(strcmp({preds.status},'verified'))
        status=-312;return;
    end
    if ~isfield(cert,'verified_native_mat_file') || ...
       isempty(cert.verified_native_mat_file) || ...
       ~isfield(cert,'verified_native_mat_sha256') || ...
       isempty(cert.verified_native_mat_sha256)
        status=-313;return;
    end
    p=char(cert.verified_native_mat_file);
    if exist(p,'file')~=2,status=-314;return;end
    fid=fopen(p,'rb');assert(fid>0);data=fread(fid,inf,'*uint8');fclose(fid);
    md=java.security.MessageDigest.getInstance('SHA-256');
    md.update(data);digest=typecast(md.digest(),'uint8');
    sha=lower(reshape(dec2hex(digest,2).',1,[]));
    if ~strcmp(sha,char(cert.verified_native_mat_sha256))
        status=-315;return;
    end
    obj=load(p,'model','initialSet');
    if ~isfield(obj,'model') || ~isfield(obj,'initialSet')
        status=-316;return;
    end
    mdl=obj.model;initial=obj.initialSet;
    names={'full_network_variables_covered','safety_predicates_all_covered', ...
        'full_state_dynamics_verified','measurement_map_verified', ...
        'intersample_reachability_verified','intersample_derivative_bounds_verified', ...
        'verified_emergency_policy'};
    for i=1:numel(names)
        if ~isfield(mdl,names{i}) || ~logical(mdl.(names{i}))
            status=-317;return;
        end
    end
    if ~isstruct(initial) || ~isfield(initial,'coverage_verified') || ...
        ~logical(initial.coverage_verified) || ...
        ~isfield(initial,'center') || ~isfield(initial,'error')
        status=-318;return;
    end
    n=numel(initial.center);m=double(cfg.actuation_channels);
    if ~isfield(mdl,'H') || ~isfield(mdl,'B') || ...
        ~isequal(size(mdl.H),[double(cfg.observation_channels) n]) || ...
        ~isequal(size(mdl.B),[n m])
        status=-319;return;
    end
    model=mdl;initialSet=initial;status=1;
catch
    model=struct('full_network_variables_covered',false, ...
        'safety_predicates_all_covered',false);
    initialSet=struct('center',[],'error',[],'coverage_verified',false);
    status=-320;
end
end
