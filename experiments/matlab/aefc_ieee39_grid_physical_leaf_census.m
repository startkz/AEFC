function aefc_ieee39_grid_physical_leaf_census
% Original R2024b 39-bus model physical-node census beyond name=Voltage.
% Discover Simscape electrical leaf entries 'v','i', 'p', and base units,
% including the Grid network. Structural discovery ONLY, not authenticated
% PMU/CT/PT online sensors or nonlinear reachability verification.
repo=pwd;res=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(res,'dir'),mkdir(res);end
report=struct('status','NOT_STARTED', ...
    'official_original_model','IEEE39BusSystem', ...
    'sampling_window_seconds',0.05, ...
    'logged_leaf_paths',0, ...
    'grid_leaf_paths',0, ...
    'grid_voltage_like_leaf_paths',0, ...
    'grid_current_like_leaf_paths',0, ...
    'specific_39_bus_voltage_channels_trusted',0, ...
    'specific_branch_thermal_channels_trusted',0, ...
    'full_IEEE39_DAE_state_estimation_certified',false, ...
    'rigorous_nonlinear_reachability_certified',false, ...
    'all_entries_offline_simscape_oracle_only',true);
try
    [model,~]=aefc_ieee39_load_official;
    in=Simulink.SimulationInput(model);
    in=in.setModelParameter('StopTime','0.05');
    in=in.setModelParameter('ReturnWorkspaceOutputs','on');
    in=in.setModelParameter('SimscapeLogType','all');
    in=in.setModelParameter('SimscapeLogName','AEFC_LEAF_SIMLOG');
    out=sim(in);
    node=[];
    try,node=out.get('AEFC_LEAF_SIMLOG');catch,end
    if isempty(node)
        try,node=simscape.logging.getSimulationLog(model);catch,end
    end
    if ~isa(node,'simscape.logging.Node')
        report.status='NO_ORIGINAL_SIMSCAPE_PHYSICAL_LOG';
    else
        stack={node};paths={model};head=1;
        maxNodes=30000;maxEntries=12000;
        entry=struct('path',{},'leaf_name',{},'grid',{}, ...
            'candidate_variable',{},'series_class',{}, ...
            'unit_label',{},'trusted_online_sensor',{});
        visited=0;
        while head<=numel(stack) && visited<maxNodes
            nd=stack{head};path=paths{head};head=head+1;
            visited=visited+1;
            allProps=properties(nd);
            for j=1:numel(allProps)
                key=allProps{j};
                child=[];
                try,child=nd.(key);catch,end
                if isa(child,'simscape.logging.Node')
                    stack{end+1}=child; %#ok<AGROW>
                    paths{end+1}=[path '/' key]; %#ok<AGROW>
                elseif isa(child,'simscape.logging.Series')
                    % The physical variable is a genuine logged series.
                    % Field names are matched conservatively; no actual
                    % bus or branch sensor is inferred from naming alone.
                    leaf=lower(char(key));
                    grid=contains(path,[model '/Grid/']);
                    candidate='';
                    if any(strcmp(leaf,{'v','v_a','v_b','v_c','vabc','vrms','v_rms'}))
                        candidate='voltage_leaf';
                    elseif any(strcmp(leaf,{'i','i_a','i_b','i_c','iabc','irms','i_rms'}))
                        candidate='current_leaf';
                    elseif any(strcmp(leaf,{'p','q','s','pout','qout'}))
                        candidate='power_leaf';
                    end
                    if grid || ~isempty(candidate)
                        label='';
                        try,label=char(child.unit);catch,end
                        if numel(entry)<maxEntries
                            entry(end+1)=struct('path',[path '/' key], ...
                                'leaf_name',key,'grid',grid, ...
                                'candidate_variable',candidate, ...
                                'series_class',class(child), ...
                                'unit_label',label,'trusted_online_sensor',false); %#ok<AGROW>
                        end
                        report.logged_leaf_paths=report.logged_leaf_paths+1;
                        report.grid_leaf_paths=report.grid_leaf_paths+double(grid);
                        report.grid_voltage_like_leaf_paths=report.grid_voltage_like_leaf_paths+ ...
                            double(grid && strcmp(candidate,'voltage_leaf'));
                        report.grid_current_like_leaf_paths=report.grid_current_like_leaf_paths+ ...
                            double(grid && strcmp(candidate,'current_leaf'));
                    end
                end
            end
        end
        report.status='OFFLINE_PHYSICAL_GRID_LEAF_CENSUS_COMPLETED';
        report.truncated=visited>=maxNodes || head<=numel(stack) || ...
            numel(entry)>=maxEntries;
        report.visited_nodes=visited;report.raw_entries=entry;
    end
catch ME
    report.status='OFFLINE_PHYSICAL_GRID_LEAF_CENSUS_FAILED';
    report.error_id=ME.identifier;
    report.error_message=ME.message;
end
f=fullfile(res,'native_grid_physical_leaf_census.json');
fid=fopen(f,'w');assert(fid>0);
fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');
fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Physical grid leaf census: %s; trusted 39-bus coverage=FALSE.\\n',report.status);
try,close_system('IEEE39BusSystem',0);catch,end
end
