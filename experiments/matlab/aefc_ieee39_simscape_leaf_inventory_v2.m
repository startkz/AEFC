function aefc_ieee39_simscape_leaf_inventory_v2
% Enumerate actual Series leaves from the native IEEE39 Simscape log.
% This corrects the earlier node-name-only inventory, which skipped the
% "series" property and therefore undercounted branch-current channels.
% Everything collected here is OFFLINE simulator evidence, not an online
% sensor map, a full DAE state decomposition, or a safety certificate.

repo=pwd;
resDir=fullfile(repo,'results','ieee39_r2024b');
outDir=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(outDir,'dir'),mkdir(outDir);end
mappingPath=fullfile(resDir,'interface_mapping.json');
assert(exist(mappingPath,'file')==2,'AEFC:LeafInventoryMapping', ...
    'Validated four-channel mapping is missing.');
mapping=jsondecode(fileread(mappingPath));
assert(isfield(mapping,'validated') && mapping.validated, ...
    'AEFC:LeafInventoryMapping','Four-speed causal mapping is not validated.');

% Build the same native IEEE39-derived plant used by the Bus16 pilot.
aefc_ieee39_build_stress;
model='IEEE39BusSystem_AEFCStress';
modelPath=fullfile(resDir,[model '.slx']);
assert(exist(modelPath,'file')==2,'AEFC:LeafInventoryModel', ...
    'Native IEEE39 stress model was not built.');
load_system(modelPath);
try,set_param(model,'FastRestart','off');catch,end
set_param(model,'SimscapeLogType','all','SimscapeLogName','AEFC_LEAF_SIMLOG');
try,set_param(model,'SimulationCommand','update');catch,end
in=Simulink.SimulationInput(model);
in=in.setModelParameter('StopTime','0.05');
in=in.setModelParameter('ReturnWorkspaceOutputs','on');
out=sim(in);

logNode=[];
try,logNode=out.get('AEFC_LEAF_SIMLOG');catch,end
if ~isa(logNode,'simscape.logging.Node')
    try,logNode=simscape.logging.getSimulationLog(model);catch,end
end
assert(isa(logNode,'simscape.logging.Node'),'AEFC:LeafInventoryLog', ...
    'Original native Simscape logging did not return a logging Node.');

bus=struct('path',{},'logical_bus',{},'section',{},'unit',{},'samples',{}, ...
    'time_start',{},'time_end',{},'minimum',{},'maximum',{},'max_abs',{});
branch=struct('path',{},'component',{},'component_type',{},'variable',{}, ...
    'unit',{},'samples',{},'time_start',{},'time_end',{},'max_abs',{});
rotor=struct('path',{},'generator',{},'unit',{},'samples',{}, ...
    'time_start',{},'time_end',{},'minimum',{},'maximum',{},'max_abs',{});
terminalVoltage=struct('path',{},'generator',{},'unit',{},'samples',{}, ...
    'time_start',{},'time_end',{},'minimum',{},'maximum',{},'max_abs',{});
otherExamples=struct('path',{},'unit',{},'samples',{});
categoryCounts=struct('bus_voltage',0,'line_phase_current',0, ...
    'transformer_winding_current',0,'rotor_angle_candidate',0, ...
    'generator_terminal_voltage_candidate',0,'other_series',0);
stack={logNode};paths={model};head=1;visited=0;maxNodes=100000;maxDepth=28;
while head<=numel(stack) && visited<maxNodes
    nd=stack{head};parent=paths{head};head=head+1;visited=visited+1;
    if numel(strsplit(parent,'/'))>maxDepth,continue;end
    names=properties(nd);
    for j=1:numel(names)
        key=names{j};child=[];
        try,child=nd.(key);catch,end
        if isa(child,'simscape.logging.Node')
            stack{end+1}=child; %#ok<AGROW>
            paths{end+1}=[parent '/' key]; %#ok<AGROW>
        elseif isa(child,'simscape.logging.Series')
            unit='';tt=[];vv=[];
            try
                unit=char(child.unit);
                tt=double(time(child));
                vv=double(values(child));
            catch
                continue
            end
            if isempty(tt) || isempty(vv),continue;end
            tt=double(tt(:));vv=double(vv);
            if ~isreal(vv),vv=abs(vv);end
            vv=double(vv(:));
            if numel(vv)~=numel(tt) || any(~isfinite(tt)) || any(~isfinite(vv))
                continue
            end
            [tt,ia]=unique(tt,'stable');vv=vv(ia);
            if numel(tt)<2,continue;end
            fullPath=[parent '/' key];
            lo=min(vv);hi=max(vv);ma=max(abs(vv));ns=numel(tt);

            % Physical bus voltage leaf. Keep logical ID and split section.
            tok=regexp(parent,'/Grid/Bus([^/]+)/Vt$','tokens','once');
            if ~isempty(tok)
                parts=strsplit(tok{1},'_');
                logicalBus=parts{1};section='';
                if numel(parts)>1,section=parts{2};end
                bus(end+1)=struct('path',fullPath,'logical_bus',logicalBus, ...
                    'section',section,'unit',unit,'samples',ns, ...
                    'time_start',tt(1),'time_end',tt(end), ...
                    'minimum',lo,'maximum',hi,'max_abs',ma); %#ok<AGROW>
                categoryCounts.bus_voltage=categoryCounts.bus_voltage+1;
                continue
            end

            % Three native phase-current leaves per transmission line.
            tok=regexp(parent,'/Grid/([^/]+)/transmission_line/(inductor_[abc])/i/amplitude$', ...
                'tokens','once');
            if ~isempty(tok) && strcmp(unit,'A')
                branch(end+1)=struct('path',fullPath,'component',tok{1}, ...
                    'component_type','transmission_line','variable', ...
                    [tok{2} '/i/amplitude'],'unit',unit,'samples',ns, ...
                    'time_start',tt(1),'time_end',tt(end),'max_abs',ma); %#ok<AGROW>
                categoryCounts.line_phase_current=categoryCounts.line_phase_current+1;
                continue
            end

            % Both native winding currents for each transformer.
            tok=regexp(parent,'/Grid/(TF_[^/]+|TF [^/]+)/(i1|i2)$','tokens','once');
            if ~isempty(tok) && strcmp(unit,'A')
                branch(end+1)=struct('path',fullPath,'component',tok{1}, ...
                    'component_type','transformer','variable',tok{2}, ...
                    'unit',unit,'samples',ns,'time_start',tt(1), ...
                    'time_end',tt(end),'max_abs',ma); %#ok<AGROW>
                categoryCounts.transformer_winding_current= ...
                    categoryCounts.transformer_winding_current+1;
                continue
            end

            % Generator rotor-angle and terminal-voltage candidates. These
            % are offline log paths until a real online measurement path and
            % its integrity/error bound are separately demonstrated.
            tok=regexp(fullPath,'/Generators/(Gen[^/]+)/Rotor_electrical_angle(?:/|$)', ...
                'tokens','once');
            if ~isempty(tok)
                rotor(end+1)=struct('path',fullPath,'generator',tok{1}, ...
                    'unit',unit,'samples',ns,'time_start',tt(1), ...
                    'time_end',tt(end),'minimum',lo,'maximum',hi,'max_abs',ma); %#ok<AGROW>
                categoryCounts.rotor_angle_candidate= ...
                    categoryCounts.rotor_angle_candidate+1;
                continue
            end
            tok=regexp(fullPath,'/Generators/(Gen[^/]+)/Terminal_voltage(?:/|$)', ...
                'tokens','once');
            if ~isempty(tok)
                terminalVoltage(end+1)=struct('path',fullPath,'generator',tok{1}, ...
                    'unit',unit,'samples',ns,'time_start',tt(1), ...
                    'time_end',tt(end),'minimum',lo,'maximum',hi,'max_abs',ma); %#ok<AGROW>
                categoryCounts.generator_terminal_voltage_candidate= ...
                    categoryCounts.generator_terminal_voltage_candidate+1;
                continue
            end
            categoryCounts.other_series=categoryCounts.other_series+1;
            if numel(otherExamples)<500
                otherExamples(end+1)=struct('path',fullPath,'unit',unit, ...
                    'samples',ns); %#ok<AGROW>
            end
        end
    end
end

logicalBuses=unique({bus.logical_bus});
lineNames=unique({branch(strcmp({branch.component_type},'transmission_line')).component});
transformerNames=unique({branch(strcmp({branch.component_type},'transformer')).component});
rotorGenerators=unique({rotor.generator});
terminalGenerators=unique({terminalVoltage.generator});

info=struct();
info.backend='MATLAB R2024b native IEEE39BusSystem_AEFCStress Simulink/Simscape';
info.scope='OFFLINE Simscape Series-leaf inventory; not online observation or certification';
info.model=model;info.simscape_log_available=true;
info.nodes_visited=visited;info.node_limit=maxNodes;
info.queue_remaining=max(0,numel(stack)-head+1);
info.truncated=(visited>=maxNodes || head<=numel(stack));
info.series_category_counts=categoryCounts;
info.logical_bus_voltage_ids=numel(logicalBuses);
info.logical_bus_ids={logicalBuses};
info.physical_bus_voltage_sections=numel(bus);
info.bus_voltage_series=bus;
info.line_component_count=numel(lineNames);
info.line_component_names={lineNames};
info.line_phase_current_series=categoryCounts.line_phase_current;
info.transformer_component_count=numel(transformerNames);
info.transformer_component_names={transformerNames};
info.transformer_winding_current_series=categoryCounts.transformer_winding_current;
info.total_branch_current_series=numel(branch);
info.branch_current_series=branch;
info.generator_rotor_angle_candidate_count=numel(rotorGenerators);
info.generator_rotor_angle_candidate_generators={rotorGenerators};
info.generator_rotor_angle_series=rotor;
info.generator_terminal_voltage_candidate_count=numel(terminalGenerators);
info.generator_terminal_voltage_candidate_generators={terminalGenerators};
info.generator_terminal_voltage_series=terminalVoltage;
info.other_series_examples=otherExamples;
info.online_controller_input_channels=4;
info.trusted_online_sensor_integrity_verified=false;
info.sensor_error_bounds_verified=0;
info.complete_DAE_state_observability_verified=false;
info.full_state_dimension_verified=false;
info.sampled_one_step_reachable_tube_verified=false;
info.continuous_intersample_tube_verified=false;
info.branch_thermal_limits_validated=false;
info.backup_governor_viability_verified=false;
info.full_network_safety_certified=false;
info.interpretation=['The leaf inventory identifies physical Simscape series actually logged by the model. ' ...
    'It does not establish that those series are available to the controller as authenticated sensors, ' ...
    'nor does it prove independent state dimension, state-estimator error coverage, DAE reachability, ' ...
    'or continuous-time safety.'];

fp=fullfile(outDir,'native_simscape_leaf_inventory_v2.json');
fid=fopen(fp,'w');assert(fid>0,'AEFC:LeafInventoryIO','Cannot save leaf inventory');
fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Native Simscape leaf inventory v2: %d bus sections, %d branch-current series, %d rotor-angle candidates; certificate=FALSE.\n', ...
    numel(bus),numel(branch),numel(rotorGenerators));
try,set_param(model,'FastRestart','off');catch,end
try,close_system(model,0);catch,end
end
