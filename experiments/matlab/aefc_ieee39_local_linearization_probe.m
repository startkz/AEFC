function aefc_ieee39_local_linearization_probe
% Research-only operating-point *LOCAL* linearization of the actual native
% IEEE39 Simulink plant, for observability/model-identification diagnosis.
% A local A,B,C matrix is NEVER proof of a globally valid uncertain
% reachability tube, physical sensor integrity, or full IEEE39 safety.
repo=pwd;
path=fullfile(repo,'results','ieee39_fullstate_p0');
if ~exist(path,'dir'),mkdir(path);end
info=struct('model','IEEE39BusSystem_AEFCUnpriv',...
    'requires','Simulink Control Design and valid physical operating point', ...
    'linearization_is_complete_reachability_certificate',false, ...
    'full_ieee39_safety_certified',false, ...
    'all_ten_generator_speed_observed',true);
info.scd_license=license('test','Simulink_Control_Design');
info.linmod_available=exist('linmod','file')==2;
info.linearize_available=exist('linearize','file')==2;
info.linio_available=exist('linio','file')==2;
try
    cfg=jsondecode(fileread(fullfile(repo,'configs','ieee39_unpriv_r1.json')));
    model=char(cfg.model);
    fp=fullfile(repo,'results','ieee39_r2024b',[model '.slx']);
    if exist(fp,'file')~=2,aefc_ieee39_build_unprivileged;end
    load_system(fp);
    set_param([model '/AEFC_NATIVE_CONTROLLER'],'MethodCode','8', ...
        'ExploratoryMode','false');
    set_param([model '/AEFC_NATIVE_ATTACK_SOURCE'],'ScenarioCode','1', ...
        'Seed','0');
    if ~(info.scd_license && info.linearize_available && info.linio_available)
        info.status='LINEARIZATION_TOOLBOX_UNAVAILABLE';
    else
        % This is a local numerical linearization, not a rigorous model
        % inclusion proof. The port locations are physically connected to
        % four Pref corrections and ten real rotor speed signals.
        io(1)=linio([model '/AEFC_SHIELD_DEMUX'],1,'input');
        io(2)=linio([model '/AEFC_GENALL_MUX'],1,'output');
        sy=linearize(model,io,0);
        [A,B,C,D]=ssdata(sy);
        info.state_dim=size(A,1);
        info.control_port_dim=size(B,2);
        info.sensed_machine_speed_dim=size(C,1);
        info.dynamical_discrete_or_continuous=sy.Ts;
        info.A_is_finite=all(isfinite(A(:)));
        info.B_is_finite=all(isfinite(B(:)));
        info.C_is_finite=all(isfinite(C(:)));
        info.native_physical_model_linearization_only=true;
        if all([size(B,2)==4,size(C,1)==10,info.A_is_finite,...
                info.B_is_finite,info.C_is_finite])
            save(fullfile(path,'native_ieee39_local_linearization.mat'), ...
                'A','B','C','D','-v7.3');
            info.status='LOCAL_LINEARIZATION_OBTAINED_NOT_CERTIFIED';
        else
            info.status='LINEARIZATION_DIMENSION_OR_NUMERIC_MISMATCH';
        end
    end
catch ME
    info.status='LINEARIZATION_PROBE_FAILED';
    info.error_id=ME.identifier;
    info.error_message=ME.message;
end
fp=fullfile(path,'native_linearization_probe.json');
fid=fopen(fp,'w');assert(fid>0);
fwrite(fid,jsonencode(info,'PrettyPrint',true));fwrite(fid,sprintf('\n'));fclose(fid);
try,close_system('IEEE39BusSystem_AEFCUnpriv',0);catch,end
fprintf('Native local linearization probe: %s; NO full-state safety guarantee.\\n',info.status);
end
