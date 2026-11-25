function aefc_ieee39_local_observability_probe_v6
% Validation-aware LOCAL state/output observability diagnostic on the true
% official R2024b plant copy. It cannot prove globally robust nonlinear
% DAE observability/reachability or verified full-state safety.
repo=pwd;res=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(res,'dir'),mkdir(res);end
info=struct('model','IEEE39BusSystem_AEFCUnpriv', ...
    'online_physical_measurements',4, ...
    'all_generators_offline_speed_monitored',10, ...
    'full_network_observer_verified',false, ...
    'index_one_DAE_validated',false, ...
    'bounded_nonlinear_model_residual_verified',false, ...
    'guaranteed_intersample_tube',false, ...
    'status','NOT_STARTED');
try
    model='IEEE39BusSystem_AEFCUnpriv';
    fp=fullfile(repo,'results','ieee39_r2024b',[model '.slx']);
    if exist(fp,'file')~=2,aefc_ieee39_build_unprivileged;end
    load_system(fp);
    info.load_initial_state_before=get_param(model,'LoadInitialState');
    info.initial_state_parameter_before=get_param(model,'InitialState');
    info.solver=get_param(model,'Solver');
    set_param(model,'LoadInitialState','off');
    info.load_initial_state_after=get_param(model,'LoadInitialState');
    info.scd_license=license('test','Simulink_Control_Design');
    if ~info.scd_license
        info.status='NO_SIMULINK_CONTROL_DESIGN_LICENSE';
    else
        % Four physically independent Pref correction channels are the
        % DEMUX's four scalar output signals (previous v2 incorrectly
        % sampled one port of this multi-channel signal).
        % The four Goto blocks are at model root. Their single input ports
        % carry the four shield corrections into the physical Pref sum blocks.
        % Using the Goto inputs avoids invalid internal masked-subsystem ports.
        for kk=1:4
            gotoPath=[model sprintf('/AEFC_USHIELD_GOTO_%02d',kk)];
            assert(strcmp(getSimParam(gotoPath,'BlockType'),'Goto'),'AEFC:LinearizationInputPath', ...
                'Expected native shield Goto block %d',kk);
            ph=get_param(gotoPath,'PortHandles');
            assert(numel(ph.Inport)==1,'AEFC:LinearizationInputPort', ...
                'Expected one correction input port on Goto %d',kk);
            io(kk)=linio(gotoPath,1,'input');
        end
        % One ten-dimensional physical rotor-speed output mux.
        io(5)=linio([model '/AEFC_GENALL_MUX'],1,'output');
        times=[0.10,0.35];
        attempts=struct('time',{},'status',{},'identifier',{},'error_message',{}, ...
            'full_model_state_dimension',{},'physical_input_channels',{}, ...
            'observed_speed_channels',{},'finite_linearization',{}, ...
            'local_observability_rank',{},'local_controllability_rank',{}, ...
            'rank_tolerance',{},'controllability_rank_tolerance',{}, ...
            'observability_sigma_min',{},'observability_sigma_max',{}, ...
            'observability_relative_sigma_min',{},'controllability_relative_sigma_min',{}, ...
            'global_full_state_observable',{});
        for k=1:numel(times)
            e=struct('time',times(k),'status','NOT_RUN','identifier','', ...
                'error_message','','full_model_state_dimension',0, ...
                'physical_input_channels',0,'observed_speed_channels',0, ...
                'finite_linearization',false,'local_observability_rank',0,'local_controllability_rank',0, ...
            'rank_tolerance','', 'controllability_rank_tolerance','', ...
            'observability_sigma_min',NaN,'observability_sigma_max',NaN, ...
            'observability_relative_sigma_min',NaN,'controllability_relative_sigma_min',NaN, ...
            'global_full_state_observable',false);
            try
                ss=linearize(model,io,times(k));
                [A,B,C,D]=ssdata(ss);
                e.full_model_state_dimension=size(A,1);
                e.physical_input_channels=size(B,2);
                e.observed_speed_channels=size(C,1);
                e.finite_linearization=all(isfinite(A),'all') && ...
                    all(isfinite(B),'all') && all(isfinite(C),'all');
                if e.finite_linearization && e.physical_input_channels==4 && ...
                   e.observed_speed_channels==10
                    e.status='LOCAL_DIAGNOSTIC_ONLY';
                    if size(A,1)>0 && size(A,1)<=400
                        O=obsv(A,C);
                        singulars=svd(O,'econ');
                        tol=max(size(O))*eps(max(singulars));
                        e.local_observability_rank=sum(singulars>tol);
                        e.rank_tolerance=num2str(tol,'%.17g');
                        e.observability_sigma_min=min(singulars);
                        e.observability_sigma_max=max(singulars);
                        e.observability_relative_sigma_min=min(singulars)/max(max(singulars),realmin);
                        Co=ctrb(A,B);
                        cs=svd(Co,'econ');
                        ctol=max(size(Co))*eps(max(cs));
                        e.local_controllability_rank=sum(cs>ctol);
                        e.controllability_rank_tolerance=num2str(ctol,'%.17g');
                        e.controllability_relative_sigma_min=min(cs)/max(max(cs),realmin);
                    end
                    % Rank equality on one linearization is not a robust
                    % nonlinear/DAE observability or bounded-error proof.
                    e.global_full_state_observable=false;
                    save(fullfile(res,sprintf('native_local_abc_t%02d.mat',k)), ...
                        'A','B','C','D','-v7.3');
                else
                    e.status='FAILED_FINITE_OR_DIMENSION_CHECK';
                end
            catch ME
                e.status='NATIVE_LINEARIZATION_FAILED';
                e.identifier=ME.identifier;
                e.error_message=ME.message;
            end
            attempts(end+1)=e; %#ok<AGROW>
        end
        info.attempts=attempts;
        info.status='DIAGNOSTIC_ATTEMPTS_COMPLETED';
        info.linearization_input_definition='AEFC_USHIELD_GOTO_01..04 input port 1 (the actual four shield Pref correction signals before routing to Pref sums)';
        info.linearization_output_definition='AEFC_GENALL_MUX output port 1 (ten physical generator rotor-speed channels)';
        info.output_file='native_local_observability_probe_v6.json';
    end
catch ME
    info.status='DIAGNOSTIC_SETUP_FAILED';
    info.error_id=ME.identifier;
    info.error_message=ME.message;
end
out=fullfile(res,'native_local_observability_probe_v6.json');
fid=fopen(out,'w');assert(fid>0);
fwrite(fid,jsonencode(info,'PrettyPrint',true));fwrite(fid,sprintf('\n'));fclose(fid);
try,close_system('IEEE39BusSystem_AEFCUnpriv',0);catch,end
fprintf('Native observability diagnostic %s; no full-state certificate.\\n',info.status);
end
