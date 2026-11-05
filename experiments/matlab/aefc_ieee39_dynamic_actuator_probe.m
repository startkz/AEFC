function aefc_ieee39_dynamic_actuator_probe
% Phase-B plant calibration: inject bounded Pref test pulses into the four
% causally validated native governor channels and record actual governor /
% turbine signals. This is a deterministic actuator calibration, not an
% AEFC-FRL policy evaluation.
assert(~verLessThan('matlab','24.2'),'AEFC:ReleaseTooOld','MATLAB R2024b or later is required.');

repo=pwd; resDir=fullfile(repo,'results','ieee39_r2024b');
outDir=fullfile(resDir,'dynamic_actuator_probe');
if ~exist(outDir,'dir'), mkdir(outDir); end
mapPath=fullfile(resDir,'interface_mapping.json');
assert(exist(mapPath,'file')==2,'AEFC:MappingMissing','Validated interface_mapping.json is missing.');
m=jsondecode(fileread(mapPath));
assert(m.validated && numel(m.control_edges)==4 && numel(m.observation_edges)==4, ...
    'AEFC:MappingInvalid','Expected the validated four-channel Pref/speed mapping.');

[model,~]=aefc_ieee39_load_official;
blocks=find_system(model,'LookUnderMasks','all','FollowLinks','on','Type','Block');
controlledKeys=cellstr(string(m.control_generator_keys));
assert(numel(controlledKeys)==4,'AEFC:ControlCount','Expected four controlled generator keys.');

% Record actual model solver settings and all machine inertia/rating values.
solver=struct;
for key={'Solver','SolverType','FixedStep','MaxStep','StopTime','RelTol','AbsTol'}
    try, solver.(matlab.lang.makeValidName(key{1}))=get_param(model,key{1}); catch, end
end
machineParams=extractMachineParameters(blocks,model);

channels=repmat(struct('generator_key','','pref_source_block','','pref_destination_block','', ...
    'governor_delta_y_block','','turbine_tm_block','','governor_speed_block','', ...
    'pref_base_value','','governor_saturation',struct,'turbine_saturation',struct, ...
    'governor_gains',struct,'test_pulse_start_s',0,'test_pulse_end_s',0, ...
    'raw_workspace','','rate_workspace','','limited_workspace','','pref_workspace','', ...
    'delta_y_workspace','','tm_workspace','','w_workspace',''),4,1);

for i=1:4
    key=controlledKeys{i};
    edge=m.control_edges(i);
    src=edge.src_block; dst=edge.dst_block;
    assert(getSimulinkBlockHandle(src)>0 && getSimulinkBlockHandle(dst)>0, ...
        'AEFC:ControlBlockMissing','Missing validated Pref edge for %s.',key);
    parent=get_param(src,'Parent');
    assert(strcmp(parent,get_param(dst,'Parent')),'AEFC:CrossHierarchy','Pref edge crosses hierarchy for %s.',key);
    makeEditable(parent);
    srcPH=get_param(src,'PortHandles'); dstPH=get_param(dst,'PortHandles');
    sp=srcPH.Outport(edge.src_port); dp=dstPH.Inport(edge.dst_port);

    % A 0.02-p.u. raw request is amplitude-limited to 0.01 p.u. and
    % rate-limited to 0.02 p.u./s before it is added to the native Pref.
    % Each channel receives one non-overlapping 0.5-s pulse before the
    % documented Bus-16 fault at 5 s.
    t0=0.2+1.1*(i-1); t1=t0+0.7;
    base=sprintf('AEFC_DYN_ACT_%02d_',i);
    pos=get_param(src,'Position'); x=pos(3)+70; y=pos(2);
    up=[parent '/' base 'STEP_UP']; down=[parent '/' base 'STEP_DOWN'];
    raw=[parent '/' base 'RAW_SUM']; rate=[parent '/' base 'RATE_LIMIT'];
    amp=[parent '/' base 'AMP_LIMIT']; prefSum=[parent '/' base 'PREF_SUM'];
    add_block('simulink/Sources/Step',up,'Time',num2str(t0,'%.17g'), ...
        'Before','0','After','0.02','SampleTime','0', ...
        'Position',[x y x+55 y+28]);
    add_block('simulink/Sources/Step',down,'Time',num2str(t1,'%.17g'), ...
        'Before','0','After','-0.02','SampleTime','0', ...
        'Position',[x y+42 x+55 y+70]);
    add_block('simulink/Math Operations/Sum',raw,'Inputs','++', ...
        'Position',[x+85 y+10 x+115 y+55]);
    add_block('simulink/Discontinuities/Rate Limiter',rate, ...
        'RisingSlewLimit','0.02','FallingSlewLimit','-0.02', ...
        'InitialCondition','0','Position',[x+150 y+10 x+205 y+55]);
    add_block('simulink/Discontinuities/Saturation',amp, ...
        'UpperLimit','0.01','LowerLimit','-0.01', ...
        'Position',[x+240 y+10 x+290 y+55]);
    add_block('simulink/Math Operations/Sum',prefSum,'Inputs','++', ...
        'Position',[x+330 y+10 x+360 y+55]);

    rawPH=get_param(raw,'PortHandles'); upPH=get_param(up,'PortHandles');
    downPH=get_param(down,'PortHandles'); ratePH=get_param(rate,'PortHandles');
    ampPH=get_param(amp,'PortHandles'); prefPH=get_param(prefSum,'PortHandles');
    delete_line(parent,sp,dp);
    add_line(parent,upPH.Outport,rawPH.Inport(1),'autorouting','on');
    add_line(parent,downPH.Outport,rawPH.Inport(2),'autorouting','on');
    add_line(parent,rawPH.Outport,ratePH.Inport,'autorouting','on');
    add_line(parent,ratePH.Outport,ampPH.Inport,'autorouting','on');
    add_line(parent,sp,prefPH.Inport(1),'autorouting','on');
    add_line(parent,ampPH.Outport,prefPH.Inport(2),'autorouting','on');
    add_line(parent,prefPH.Outport,dp,'autorouting','on');

    % Tap the true governor actuator state, turbine mechanical-torque signal,
    % local speed, raw request, limited request and actual Pref.
    deltaBlock=findGenBlock(blocks,model,key,'/Governor/delta_y');
    tmBlock=findGenBlock(blocks,model,key,'/Non-reheat turbine/Tm');
    wBlock=findGenBlock(blocks,model,key,'/Governor/w');
    assert(~isempty(deltaBlock) && ~isempty(tmBlock) && ~isempty(wBlock), ...
        'AEFC:ActuatorSignalMissing','Missing delta_y/Tm/w signal for %s.',key);
    deltaParent=get_param(deltaBlock,'Parent'); tmParent=get_param(tmBlock,'Parent');
    makeEditable(deltaParent); makeEditable(tmParent);
    deltaSrc=sourceForOutportBlock(deltaBlock);
    tmSrc=sourceForOutportBlock(tmBlock);
    wPH=get_param(wBlock,'PortHandles'); wSrc=wPH.Outport(1);

    names=struct('raw',sprintf('AEFC_ACT_RAW_%02d',i), ...
        'rate',sprintf('AEFC_ACT_RATE_%02d',i), ...
        'limited',sprintf('AEFC_ACT_LIMITED_%02d',i), ...
        'pref',sprintf('AEFC_ACT_PREF_%02d',i), ...
        'delta_y',sprintf('AEFC_ACT_DELTA_Y_%02d',i), ...
        'tm',sprintf('AEFC_ACT_TM_%02d',i), ...
        'w',sprintf('AEFC_ACT_W_%02d',i));
    addWorkspaceSink(parent,rawPH.Outport,names.raw,[x+380 y x+500 y+28]);
    addWorkspaceSink(parent,ratePH.Outport,names.rate,[x+380 y+35 x+500 y+63]);
    addWorkspaceSink(parent,ampPH.Outport,names.limited,[x+380 y+70 x+500 y+98]);
    addWorkspaceSink(parent,prefPH.Outport,names.pref,[x+380 y+105 x+500 y+133]);
    addWorkspaceSink(deltaParent,deltaSrc,names.delta_y,[20 20 145 48]);
    addWorkspaceSink(tmParent,tmSrc,names.tm,[20 60 145 88]);
    addWorkspaceSink(get_param(wBlock,'Parent'),wSrc,names.w,[20 100 145 128]);

    channels(i).generator_key=key;
    channels(i).pref_source_block=src;
    channels(i).pref_destination_block=dst;
    channels(i).governor_delta_y_block=deltaBlock;
    channels(i).turbine_tm_block=tmBlock;
    channels(i).governor_speed_block=wBlock;
    channels(i).pref_base_value=constantPrefValue(blocks,model,key);
    channels(i).test_pulse_start_s=t0;
    channels(i).test_pulse_end_s=t1;
    channels(i).raw_workspace=names.raw;
    channels(i).rate_workspace=names.rate;
    channels(i).limited_workspace=names.limited;
    channels(i).pref_workspace=names.pref;
    channels(i).delta_y_workspace=names.delta_y;
    channels(i).tm_workspace=names.tm;
    channels(i).w_workspace=names.w;
    channels(i).governor_saturation=findSaturationInfo(blocks,model,key,'/Governor/Integrator');
    channels(i).turbine_saturation=findSaturationInfo(blocks,model,key,'/Non-reheat turbine/Integrator');
    channels(i).governor_gains=findGainInfo(blocks,model,key);
end

% Inventory the existing fault component and the physical protection library.
fault=find_system(model,'LookUnderMasks','all','FollowLinks','on','Name','Fault (Three-Phase)');
assert(numel(fault)==1,'AEFC:FaultBlock','Expected one native Fault (Three-Phase) block.');
faultInfo=maskInfo(fault{1});
faultInfo.path=fault{1};
faultInfo.port_handles=portSummary(fault{1});
faultInfo.external_fault_visibility_test=probeFaultExternalPorts(model,fault{1});

load16=find_system(model,'LookUnderMasks','all','FollowLinks','on','Name','Load16');
assert(numel(load16)==1,'AEFC:Load16','Expected one Load16 block.');
loadInfo=struct; loadInfo.path=load16{1}; loadInfo.mask=maskInfo(load16{1});
loadInfo.port_handles=portSummary(load16{1});
loadInfo.physical_neighbors=physicalNeighbors(load16{1});

libraryInfo=discoverProtectionLibrary;
existingProtection=find_system(model,'LookUnderMasks','all','FollowLinks','on', ...
    'RegExp','on','Name','.*(Breaker|Relay|Switch).*');
existingProtection=existingProtection(:)';

% Run the native 20-s fault scenario with four sequential, rate- and
% amplitude-limited Pref test pulses.
simIn=Simulink.SimulationInput(model);
simIn=simIn.setModelParameter('StopTime','20','ReturnWorkspaceOutputs','on','SignalLogging','off');
simOut=sim(simIn);

tRef=[];
actRows=repmat(struct('time_s',0,'channel',0,'generator_key','','raw_request_pu',0, ...
    'rate_limited_request_pu',0,'amplitude_limited_request_pu',0,'pref_actual_pu',0, ...
    'governor_actuator_delta_y_pu',0,'turbine_torque_tm_pu',0,'rotor_speed_pu',0, ...
    'derived_mechanical_power_pu',0),0,1);
metrics=repmat(struct('generator_key','','pulse_start_s',0,'pulse_end_s',0, ...
    'max_abs_raw_request_pu',0,'max_abs_limited_request_pu',0, ...
    'max_abs_limited_slew_pu_per_s',0,'max_abs_delta_y_pu',0, ...
    'max_abs_delta_y_slew_pu_per_s',0,'max_abs_tm_pu',0, ...
    'max_abs_tm_slew_pu_per_s',0,'derived_pm_peak_pu',0, ...
    'pref_amplitude_bound_pu',0.01,'pref_slew_bound_pu_per_s',0.02),4,1);

for i=1:4
    c=channels(i);
    [t,raw]=getTimeseries(simOut,c.raw_workspace);
    [t2,rate]=getTimeseries(simOut,c.rate_workspace);
    [t3,limited]=getTimeseries(simOut,c.limited_workspace);
    [t4,pref]=getTimeseries(simOut,c.pref_workspace);
    [t5,dy]=getTimeseries(simOut,c.delta_y_workspace);
    [t6,tm]=getTimeseries(simOut,c.tm_workspace);
    [t7,w]=getTimeseries(simOut,c.w_workspace);
    assertAligned(t,t2,t3,t4,t5,t6,t7);
    if isempty(tRef), tRef=t; else
        assert(numel(tRef)==numel(t) && max(abs(tRef-t))<1e-8, ...
            'AEFC:ActuatorTimeAlignment','Actuator traces not aligned.');
    end
    raw=raw(:); rate=rate(:); limited=limited(:); pref=pref(:);
    dy=dy(:); tm=tm(:); w=w(:);
    dt=median(diff(t));
    dlim=gradient(limited,t); ddy=gradient(dy,t); dtm=gradient(tm,t);
    pm=tm.*w; % pu mechanical power = pu torque times pu speed.
    for k=1:numel(t)
        actRows(end+1,1)=struct('time_s',t(k),'channel',i,'generator_key',c.generator_key, ...
            'raw_request_pu',raw(k),'rate_limited_request_pu',rate(k), ...
            'amplitude_limited_request_pu',limited(k),'pref_actual_pu',pref(k), ...
            'governor_actuator_delta_y_pu',dy(k),'turbine_torque_tm_pu',tm(k), ...
            'rotor_speed_pu',w(k),'derived_mechanical_power_pu',pm(k)); %#ok<AGROW>
    end
    win=t>=c.test_pulse_start_s & t<=c.test_pulse_end_s+0.5;
    metrics(i).generator_key=c.generator_key;
    metrics(i).pulse_start_s=c.test_pulse_start_s;
    metrics(i).pulse_end_s=c.test_pulse_end_s;
    metrics(i).max_abs_raw_request_pu=max(abs(raw(win)));
    metrics(i).max_abs_limited_request_pu=max(abs(limited(win)));
    metrics(i).max_abs_limited_slew_pu_per_s=max(abs(dlim(win)));
    metrics(i).max_abs_delta_y_pu=max(abs(dy(win)));
    metrics(i).max_abs_delta_y_slew_pu_per_s=max(abs(ddy(win)));
    metrics(i).max_abs_tm_pu=max(abs(tm(win)));
    metrics(i).max_abs_tm_slew_pu_per_s=max(abs(dtm(win)));
    metrics(i).derived_pm_peak_pu=max(abs(pm(win)));
end

writeTable(fullfile(outDir,'actuator_probe_timeseries.csv'),actRows);
summary=struct('study','IoTJ IEEE39 dynamic actuator calibration', ...
    'status','deterministic actuator probe; not AEFC-FRL policy evidence', ...
    'model',model,'matlab_release',version('-release'),'stop_time_s',20, ...
    'sample_interval_s',median(diff(tRef)),'solver',solver, ...
    'control_mapping',m.control_generator_keys,'command_amplitude_limit_pu',0.01, ...
    'command_slew_limit_pu_per_s',0.02,'raw_test_request_pu',0.02, ...
    'test_pulse_schedule_s',[[channels.test_pulse_start_s]' [channels.test_pulse_end_s]'], ...
    'machine_parameters',machineParams,'channels',channels,'metrics',metrics, ...
    'fault_component',faultInfo,'load16',loadInfo,'protection_library',libraryInfo, ...
    'existing_relay_breaker_blocks',{existingProtection}, ...
    'evidence_gates',struct('actual_governor_delta_y_recorded',true, ...
      'turbine_tm_recorded',true,'command_amplitude_and_slew_measured',true, ...
      'relay_controlled_breaker_operation',false,'iotj_aefc_frl_policy_connected',false));
writejson(fullfile(outDir,'dynamic_actuator_probe_summary.json'),summary);

fig=figure('Visible','off','Color','w','Position',[100 100 1200 900]);
tiledlayout(4,1,'TileSpacing','compact');
for i=1:4
    c=channels(i);
    [tt,raw]=getTimeseries(simOut,c.raw_workspace);
    [~,limited]=getTimeseries(simOut,c.limited_workspace);
    [~,dy]=getTimeseries(simOut,c.delta_y_workspace);
    [~,tm]=getTimeseries(simOut,c.tm_workspace);
    nexttile; hold on;
    plot(tt,raw(:),'--','LineWidth',0.8);
    plot(tt,limited(:),'-','LineWidth',1.2);
    plot(tt,dy(:),'-','LineWidth',0.9);
    plot(tt,tm(:),'-','LineWidth',0.9);
    xline(c.test_pulse_start_s,':k'); xline(c.test_pulse_end_s,'--k');
    xline(5.0,':r');
    ylabel(c.generator_key,'Interpreter','none');
    grid on;
    if i==1, title('Pref test request, limited command, governor state and turbine torque'); end
    if i==4, xlabel('Time (s)'); end
end
exportgraphics(fig,fullfile(outDir,'Fig_Actuator_Command_Governor_Turbine.png'),'Resolution',300);
close(fig);

manifest=struct('source_commit',getenv('GITHUB_SHA'),'matlab_release',version('-release'), ...
    'summary_sha256',sha256File(fullfile(outDir,'dynamic_actuator_probe_summary.json')), ...
    'timeseries_sha256',sha256File(fullfile(outDir,'actuator_probe_timeseries.csv')));
writejson(fullfile(outDir,'manifest.json'),manifest);
close_system(model,0);
end

function info=extractMachineParameters(blocks,model)
info=repmat(struct('generator_key','','H_s',NaN,'S_rated_MW',NaN,'H_times_S_MWs',NaN,'block_path',''),0,1);
for i=1:numel(blocks)
    b=blocks{i};
    if ~contains(b,[model '/Generators/Gen']) || ~contains(safeget(b,'MaskType'),'Machine Mechanical')
        continue;
    end
    key=generatorKey(b); mi=maskInfo(b); m=mi.values;
    if ~isfield(m,'H') || ~isfield(m,'SRated'), continue; end
    h=str2double(m.H); s=str2double(m.SRated);
    info(end+1,1)=struct('generator_key',key,'H_s',h,'S_rated_MW',s, ...
        'H_times_S_MWs',h*s,'block_path',b); %#ok<AGROW>
end
end

function s=findSaturationInfo(blocks,model,key,marker)
s=repmat(struct('path','','upper_limit','','lower_limit','','sample_time',''),0,1);
for i=1:numel(blocks)
    b=blocks{i};
    if ~contains(b,[model '/Generators/' key]) || ~contains(b,marker) || ~contains(safeget(b,'Name'),'Saturation')
        continue;
    end
    z=struct('path',b,'upper_limit',safeget(b,'UpperLimit'), ...
        'lower_limit',safeget(b,'LowerLimit'),'sample_time',safeget(b,'SampleTime'));
    s(end+1,1)=z; %#ok<AGROW>
end
end

function s=findGainInfo(blocks,model,key)
s=repmat(struct('path','','name','','gain',''),0,1);
for i=1:numel(blocks)
    b=blocks{i};
    if ~contains(b,[model '/Generators/' key]) || ~strcmp(safeget(b,'BlockType'),'Gain'), continue; end
    if hasAny(lower(b),{'/1/tg','/1/droop','/1/tch'})
        s(end+1,1)=struct('path',b,'name',safeget(b,'Name'),'gain',safeget(b,'Gain')); %#ok<AGROW>
    end
end
end

function v=constantPrefValue(blocks,model,key)
v='';
for i=1:numel(blocks)
    b=blocks{i};
    if contains(b,[model '/Generators/' key]) && endsWith(b,'/Pref') && strcmp(safeget(b,'BlockType'),'Constant')
        v=safeget(b,'Value'); return;
    end
end
end

function b=findGenBlock(blocks,model,key,suffix)
b='';
for i=1:numel(blocks)
    x=blocks{i};
    if contains(x,[model '/Generators/' key]) && endsWith(strrep(x,char(10),''),suffix)
        b=x; return;
    end
end
end

function source=sourceForOutportBlock(block)
ph=get_param(block,'PortHandles');
assert(~isempty(ph.Inport),'AEFC:OutportNoInput','Outport block has no input: %s.',block);
lh=get_param(ph.Inport(1),'Line');
assert(~isempty(lh) && all(lh~=-1),'AEFC:OutportNoLine','No signal line at %s.',block);
source=get_param(lh,'SrcPortHandle');
source=source(1);
end

function addWorkspaceSink(parent,sourcePort,varName,pos)
sink=[parent '/' varName '_TOWS'];
if getSimulinkBlockHandle(sink)>0, delete_block(sink); end
add_block('simulink/Sinks/To Workspace',sink,'VariableName',varName, ...
    'SaveFormat','Timeseries','Position',pos);
ph=get_param(sink,'PortHandles');
add_line(parent,sourcePort,ph.Inport,'autorouting','on');
end

function assertAligned(t,varargin)
for i=1:numel(varargin)
    tt=varargin{i};
    assert(numel(tt)==numel(t) && max(abs(tt(:)-t(:)))<1e-8, ...
        'AEFC:ActuatorTimeAlignment','Signal time bases differ.');
end
end

function [t,d]=getTimeseries(simOut,name)
v=simOut.get(name);
assert(~isempty(v),'AEFC:ActuatorTraceMissing','Missing SimulationOutput variable %s.',name);
if isa(v,'timeseries'), t=v.Time; d=v.Data;
elseif isa(v,'Simulink.SimulationData.Signal'), t=v.Values.Time; d=v.Values.Data;
else, error('AEFC:ActuatorOutputFormat','Unsupported output %s: %s.',name,class(v)); end
t=double(t(:)); d=double(squeeze(d));
end

function info=maskInfo(block)
info=struct('names',{{}},'prompts',{{}},'values',struct,'styles',{{}},'enables',{{}},'dialog_parameters',{{}});
try, info.names=get_param(block,'MaskNames'); catch, end
try, info.prompts=get_param(block,'MaskPrompts'); catch, end
try, info.styles=get_param(block,'MaskStyles'); catch, end
try, info.enables=get_param(block,'MaskEnables'); catch, end
try
    names=info.names; vals=get_param(block,'MaskValues');
    if ischar(names), names={names}; end
    if ischar(vals), vals={vals}; end
    for i=1:min(numel(names),numel(vals))
        info.values.(matlab.lang.makeValidName(names{i}))=vals{i};
    end
catch
end
try
    dp=get_param(block,'DialogParameters'); fn=fieldnames(dp);
    info.dialog_parameters=fn;
catch
end
end

function info=probeFaultExternalPorts(model,fault)
info=struct('attempted',true,'external_fault_error','','measurement_error','', ...
    'before_ports',portSummary(fault),'after_ports',struct);
oldExternal=safeget(fault,'enable_external_fault');
oldMeasurement=safeget(fault,'exposemeasurement');
try
    set_param(fault,'enable_external_fault','ee.enum.external_fault.visible');
    set_param(fault,'exposemeasurement','ee.enum.exposemeasurement.visible');
    set_param(model,'SimulationCommand','update');
    info.after_ports=portSummary(fault);
catch ME
    info.external_fault_error=ME.message;
    try
        set_param(fault,'enable_external_fault',oldExternal);
        set_param(fault,'exposemeasurement',oldMeasurement);
        set_param(model,'SimulationCommand','update');
    catch
    end
end
try
    set_param(fault,'enable_external_fault',oldExternal);
    set_param(fault,'exposemeasurement',oldMeasurement);
    set_param(model,'SimulationCommand','update');
catch ME
    info.measurement_error=ME.message;
end
end

function p=portSummary(block)
ph=get_param(block,'PortHandles'); p=struct;
fn=fieldnames(ph);
for i=1:numel(fn)
    try
        v=ph.(fn{i}); p.(fn{i})=numel(v);
    catch
    end
end
end

function n=physicalNeighbors(block)
n=repmat(struct('port_type','','port_index',0,'line_handle',-1,'neighbors',{{}}),0,1);
ph=get_param(block,'PortHandles'); fn=fieldnames(ph);
for i=1:numel(fn)
    if ~any(strcmp(fn{i},{'LConn','RConn','ConnectionPort','PMIOPort'})), continue; end
    hs=ph.(fn{i});
    for j=1:numel(hs)
        z=struct('port_type',fn{i},'port_index',j,'line_handle',-1,'neighbors',{{}});
        try
            lh=get_param(hs(j),'Line'); z.line_handle=lh;
            if ~isempty(lh) && all(lh~=-1)
                handles=[get_param(lh,'SrcPortHandle') get_param(lh,'DstPortHandle')];
                for k=1:numel(handles)
                    if handles(k)<=0 || handles(k)==hs(j), continue; end
                    try
                        parent=get_param(handles(k),'Parent');
                        z.neighbors{end+1}=getfullname(parent); %#ok<AGROW>
                    catch
                    end
                end
            end
        catch
        end
        n(end+1,1)=z; %#ok<AGROW>
    end
end
end

function lib=discoverProtectionLibrary
lib=struct('ee_lib_loaded',false,'circuit_breaker_three_phase',{{}}, ...
    'voltage_sensor_candidates',{{}},'current_sensor_candidates',{{}}, ...
    'other_breaker_candidates',{{}});
try
    load_system('ee_lib'); lib.ee_lib_loaded=true;
    lib.circuit_breaker_three_phase=findNames('ee_lib',{'Circuit Breaker (Three-Phase)','Three-Phase Circuit Breaker'});
    lib.voltage_sensor_candidates=findNames('ee_lib',{'Voltage Sensor (Three-Phase)','Voltage Sensor'});
    lib.current_sensor_candidates=findNames('ee_lib',{'Current Sensor (Three-Phase)','Current Sensor'});
    lib.other_breaker_candidates=findNames('ee_lib',{'Circuit Breaker','Breaker'});
catch ME
    lib.error=ME.message;
end
end

function found=findNames(lib,names)
found={};
for i=1:numel(names)
    try
        z=find_system(lib,'LookUnderMasks','all','FollowLinks','on','Name',names{i});
        found=[found z(:)']; %#ok<AGROW>
    catch
    end
end
found=unique(found,'stable');
end

function writeTable(path,rows)
fid=fopen(path,'w'); assert(fid>0,'AEFC:IO','Cannot write %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
keys=fieldnames(rows);
for i=1:numel(keys), if i>1, fprintf(fid,','); end, fprintf(fid,'%s',keys{i}); end
fprintf(fid,'\n');
for r=1:numel(rows)
    for i=1:numel(keys)
        if i>1, fprintf(fid,','); end
        v=rows(r).(keys{i});
        if isnumeric(v), fprintf(fid,'%.10g',v);
        else, fprintf(fid,'" %s"',strrep(char(v),'"','""')); end
    end
    fprintf(fid,'\n');
end
end

function writejson(path,obj)
fid=fopen(path,'w'); assert(fid>0,'AEFC:IO','Cannot write %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(obj,'PrettyPrint',true),'char'); fwrite(fid,sprintf('\n'),'char');
end

function h=sha256File(path)
fid=fopen(path,'r'); assert(fid>0,'AEFC:IO','Cannot hash %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
b=fread(fid,inf,'*uint8');
md=java.security.MessageDigest.getInstance('SHA-256'); md.update(b);
d=typecast(md.digest(),'uint8'); h=lower(reshape(dec2hex(d,2).',1,[]));
end

function g=generatorKey(path)
tok=regexp(path,'Generators/(Gen\d+@Bus\d+)','tokens','once');
if isempty(tok), g=''; else, g=tok{1}; end
end

function tf=hasAny(txt,terms)
tf=false;
for k=1:numel(terms)
    if contains(txt,lower(terms{k})), tf=true; return; end
end
end

function makeEditable(block)
try
    if strcmp(get_param(block,'LinkStatus'),'resolved'), set_param(block,'LinkStatus','inactive'); end
catch
end
end

function v=safeget(block,param)
try
    v=get_param(block,param);
    if isstring(v), v=char(v); end
catch
    v='';
end
end
