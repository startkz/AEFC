function aefc_ieee39_offline_fullstate_inventory
% Extract offline simulation state inventory from the OFFICIAL native model.
% No simulated hidden state is exported to the online AEFC controller.
repo=pwd;
output=fullfile(repo,'results','ieee39_fullstate_p0');
if ~exist(output,'dir'),mkdir(output);end
info=struct;
info.source='MathWorks R2024b IEEE39BusSystem original Simulink simulation';
info.signal_trust='OFFLINE state logging only, not authenticated online telemetry';
info.sensor_count_online=4;
info.full_state_observability_verified=false;
info.model_reachability_verified=false;
info.full_state_safety_certificate=false;
info.timestamp_utc=char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ss''Z'''));
try
    [model,modelPath]=aefc_ieee39_load_official;
    info.model=model;info.model_path=modelPath;
    info.model_version=get_param(model,'ModelVersion');
    blocks=find_system(model,'LookUnderMasks','all','FollowLinks','on','Type','Block');
    types=cell(numel(blocks),1);
    for i=1:numel(blocks)
        try,types{i}=char(get_param(blocks{i},'BlockType'));catch,types{i}='UNKNOWN';end
    end
    info.n_model_blocks=numel(blocks);
    info.block_types=unique(types);
    % Discover physically meaningful generator speed measurement paths,
    % separate from hidden integration states; no online oracle access.
    candidates=struct('generator',{},'block',{},'port',{},'is_plausible_sensor',{});
    seen={};
    for k=1:numel(blocks)
        name='';
        try,name=char(get_param(blocks{k},'Name'));catch,end
        key=regexp(blocks{k},'Generators/(Gen[0-9]+@Bus[0-9]+)/','tokens','once');
        if isempty(key) || ~strcmp(name,'w') || ...
                ~contains(blocks{k},'Governor') || any(strcmp(seen,key{1}))
            continue;
        end
        port=0;
        try
            ph=get_param(blocks{k},'PortHandles');
            if isfield(ph,'Outport') && ~isempty(ph.Outport),port=1;end
        catch
        end
        if port<1,continue;end
        entry=struct('generator',key{1},'block',blocks{k}, ...
            'port',port,'is_plausible_sensor',true);
        candidates(end+1)=entry;
        seen{end+1}=key{1};
    end
    info.physical_rotor_speed_sensor_candidates=candidates;
    info.n_distinct_generator_speed_candidates=numel(candidates);
    info.all_generator_speed_channels_located=(numel(candidates)==10);
    info.generator_speed_sensor_integrity_established=false;
    simIn=Simulink.SimulationInput(model);
    simIn=simIn.setModelParameter('StopTime','0.10');
    simIn=simIn.setModelParameter('SaveState','on');
    simIn=simIn.setModelParameter('StateSaveName','AEFC_FULL_XOUT');
    simIn=simIn.setModelParameter('SaveFormat','Dataset');
    simIn=simIn.setModelParameter('ReturnWorkspaceOutputs','on');
    out=sim(simIn);
    x=[];
    try,x=out.get('AEFC_FULL_XOUT');catch,end
    info.xout_class=class(x);
    info.n_state_entries=0;
    info.n_scalar_dynamic_components_estimate=0;
    info.state_entries=struct('index',{},'name',{},'blockpath',{},'state_class',{}, ...
        'n_samples',{},'n_signal_components',{},'is_numeric',{});
    if isa(x,'Simulink.SimulationData.Dataset')
        info.n_state_entries=x.numElements;
        for k=1:x.numElements
            el=x.getElement(k);
            entry=struct('index',k,'name','','blockpath','', ...
                'state_class','','n_samples',0,'n_signal_components',0,'is_numeric',false);
            try,entry.name=char(el.Name);catch,end
            try,entry.blockpath=char(el.BlockPath.getBlock(1));catch,end
            try
                val=el.Values;
                entry.state_class=class(val);
                v=val.Data;
                entry.is_numeric=isnumeric(v);
                if isnumeric(v)
                    entry.n_samples=numel(val.Time);
                    if entry.n_samples>=1 && mod(numel(v),entry.n_samples)==0
                        entry.n_signal_components=numel(v)/entry.n_samples;
                    end
                end
            catch
            end
            info.state_entries(end+1)=entry;
            info.n_scalar_dynamic_components_estimate= ...
                info.n_scalar_dynamic_components_estimate+entry.n_signal_components;
        end
    end
    info.state_output_nonempty=info.n_state_entries>0;
    info.audit_status='OFFLINE_INVENTORY_ONLY';
catch ME
    info.audit_status='STATE_INVENTORY_FAILED';
    info.exception_identifier=ME.identifier;
    info.exception_message=ME.message;
end
fp=fullfile(output,'original_native_state_inventory.json');
fid=fopen(fp,'w');
assert(fid>0,'AEFC:InventoryIO','Failed to write state inventory');
fwrite(fid,jsonencode(info,'PrettyPrint',true));fwrite(fid,sprintf('\n'));fclose(fid);
fprintf('OFFLINE IEEE39 STATE INVENTORY: %s; %d dynamic components listed; complete online certificate=false\\n',...
    info.audit_status,info.n_scalar_dynamic_components_estimate);
try,close_system('IEEE39BusSystem',0);catch,end
end
