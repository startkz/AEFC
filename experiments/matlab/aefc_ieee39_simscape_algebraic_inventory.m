function aefc_ieee39_simscape_algebraic_inventory
% Official native IEEE39 Simscape logging probe: reveal whether bus voltages,
% branch currents and algebraic variables can be logged from the *physical*
% model. Logged solver data is OFFLINE and not a trusted online observer.
% Failure to log is an evidence gap, not proof that a variable does not exist.
repo=pwd;
outDir=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(outDir,'dir'),mkdir(outDir);end
info=struct('backend','Original official MathWorks IEEE39BusSystem', ...
    'scope','OFFLINE physical-node/DAE algebraic signal discovery', ...
    'simscape_log_available',false, ...
    'all_39_bus_voltage_online_validated',false, ...
    'all_branch_thermal_online_validated',false, ...
    'complete_DAE_state_observability_verified',false, ...
    'guaranteed_one_step_reachable_tube',false, ...
    'guaranteed_continuous_holding_tube',false, ...
    'trusted_online_sensor_integrity_verified',false, ...
    'status','NOT_STARTED');
try
    [model,~]=aefc_ieee39_load_official;
    in=Simulink.SimulationInput(model);
    in=in.setModelParameter('StopTime','0.05');
    in=in.setModelParameter('ReturnWorkspaceOutputs','on');
    in=in.setModelParameter('SimscapeLogType','all');
    in=in.setModelParameter('SimscapeLogName','AEFC_FULL_SIMLOG');
    try
        in=in.setModelParameter('SimscapeLogLimitData','on');
    catch
    end
    out=sim(in);
    node=[];
    try,node=out.get('AEFC_FULL_SIMLOG');catch,end
    if isempty(node)
        try,node=simscape.logging.getSimulationLog(model);catch,end
    end
    info.simscape_log_class=class(node);
    if isa(node,'simscape.logging.Node')
        info.simscape_log_available=true;
        q={node}; paths={'IEEE39BusSystem'};
        head=1;maxNodes=25000;maxDepth=18;
        hits=struct('path',{},'kind',{},'is_offline_only',{});
        tally=struct('bus_voltage',0,'branch_current',0, ...
            'branch_power',0,'rotor_angle',0,'misc_physical',0);
        total=0;
        while head<=numel(q) && total<maxNodes
            current=q{head};pth=paths{head};head=head+1;total=total+1;
            n=lower(pth);
            if contains(n,'voltage') || contains(n,'vabc') || ...
                    contains(n,'v_rms') || contains(n,'vrms')
                cat='bus_voltage';
            elseif contains(n,'current') || contains(n,'iabc')
                cat='branch_current';
            elseif contains(n,'active_power') || ...
                   contains(n,'power_flow') || contains(n,'pflow')
                cat='branch_power';
            elseif contains(n,'rotor') && contains(n,'angle')
                cat='rotor_angle';
            else
                cat='misc_physical';
            end
            tally.(cat)=tally.(cat)+1;
            if ~strcmp(cat,'misc_physical') && numel(hits)<4000
                hits(end+1)=struct('path',pth,'kind',cat, ...
                    'is_offline_only',true); %#ok<AGROW>
            end
            if numel(strsplit(pth,'/'))>maxDepth,continue;end
            names=properties(current);
            for i=1:numel(names)
                nm=names{i};
                if any(strcmp(nm,{'id','savable','exportable','series'}))
                    continue;
                end
                child=[];
                try,child=current.(nm);catch,end
                if isa(child,'simscape.logging.Node')
                    q{end+1}=child; %#ok<AGROW>
                    paths{end+1}=[pth '/' nm]; %#ok<AGROW>
                end
            end
        end
        info.status='OFFLINE_SIMSCAPE_LOG_INVENTORY_ONLY';
        info.number_of_nodes_inspected=total;
        info.queue_remaining=max(0,numel(q)-head+1);
        info.node_limit=maxNodes;
        info.truncated=(numel(q)>=maxNodes || head<=numel(q));
        info.potential_measurement_node_counts=tally;
        info.candidate_node_paths=hits;
    else
        info.status='SIMSCAPE_LOG_UNAVAILABLE';
        info.reason='No simscape.logging.Node object returned from original simulation';
    end
catch ME
    info.status='SIMSCAPE_DAE_INVENTORY_FAILED';
    info.error_id=ME.identifier;
    info.error_message=ME.message;
end
fp=fullfile(outDir,'native_simscape_algebraic_inventory.json');
fid=fopen(fp,'w');assert(fid>0,'AEFC:SimscapeIO','Cannot save algebraic inventory');
fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');
fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Original IEEE39 Simscape DAE inventory: %s; full-online certificate=FALSE.\\n',info.status);
try,close_system('IEEE39BusSystem',0);catch,end
end
