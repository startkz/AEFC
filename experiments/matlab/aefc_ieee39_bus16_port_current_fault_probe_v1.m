function aefc_ieee39_bus16_port_current_fault_probe_v1
% One-episode instrumentation probe: identify which Bus16_1 I# current
% series belongs to the physical RConn1 connected to the native Bus16_1 fault.
% This is not a new recovery-effect experiment.
repo=pwd;
p=jsondecode(fileread(fullfile(repo,'configs','ieee39_native_fault_recovery_protocol_r1.json')));
loc=jsondecode(fileread(fullfile(repo,'configs','ieee39_native_fault_recovery_protocol_r1_location_addendum.json')));
model=char(p.model);modelPath=fullfile(repo,'results','ieee39_r2024b',[model '.slx']);
if exist(modelPath,'file')~=2,aefc_ieee39_build_stress;end
load_system(modelPath);
ctrl=[model '/AEFC_NATIVE_CONTROLLER'];harness=[model '/AEFC_NATIVE_ATTACK_SOURCE'];
fault=[model '/Grid/Fault (Three-Phase)'];
assert(strcmp(char(get_param(fault,'enable_temporal_fault')),'1'));
assert(endsWith(loc.fault.physical_bus_section,'/Grid/Bus16_1'));
assert(endsWith(loc.fault.connected_transmission_line,'/Grid/B16 to B17'));
assert(abs(str2double(get_param(fault,'fault_start_time'))-5.0)<1e-9);
assert(abs(str2double(get_param(fault,'fault_duration'))-0.1)<1e-9);
set_param(ctrl,'MethodCode','7','ExploratoryMode','false');
set_param(harness,'ScenarioCode','1','Seed','80','AttackScale','1','StressAmplitude','0');
set_param(model,'SimscapeLogType','all','SimscapeLogName','AEFC_BUS16_PORT_PROBE_SIMLOG');
try,set_param(model,'SimulationCommand','update');catch,end
try,set_param(model,'FastRestart','off');catch,end
in=Simulink.SimulationInput(model);
in=in.setBlockParameter(ctrl,'MethodCode','7');
in=in.setBlockParameter(ctrl,'ExploratoryMode','0');
in=in.setBlockParameter(harness,'ScenarioCode','1');
in=in.setBlockParameter(harness,'Seed','80');
in=in.setBlockParameter(harness,'AttackScale','1');
in=in.setBlockParameter(harness,'StressAmplitude','0');
in=in.setModelParameter('StopTime',num2str(p.stop_time_s,'%.17g'),'ReturnWorkspaceOutputs','on');
out=sim(in);
logNode=[];
try,logNode=out.get('AEFC_BUS16_PORT_PROBE_SIMLOG');catch,end
if ~isa(logNode,'simscape.logging.Node')
    try,logNode=simscape.logging.getSimulationLog(model);catch,end
end
assert(isa(logNode,'simscape.logging.Node'),'AEFC:Bus16PortProbeLog','Missing native Simscape log.');

busRows=struct('path',{},'bus_section',{},'port_index',{},'unit',{},'time_s',{},'values_real',{},'values_imag',{});
lineRows=struct('path',{},'component',{},'terminal',{},'unit',{},'time_s',{},'values_real',{},'values_imag',{});
faultRows=struct('path',{},'unit',{},'time_s',{},'values_real',{},'values_imag',{});
stack={logNode};paths={model};head=1;visited=0;maxNodes=100000;maxDepth=28;
while head<=numel(stack)&&visited<maxNodes
    nd=stack{head};parent=paths{head};head=head+1;visited=visited+1;
    if numel(strsplit(parent,'/'))>maxDepth,continue;end
    names=properties(nd);
    for j=1:numel(names)
        key=names{j};child=[];
        try,child=nd.(key);catch,end
        if isa(child,'simscape.logging.Node')
            stack{end+1}=child;paths{end+1}=[parent '/' key]; %#ok<AGROW>
        elseif isa(child,'simscape.logging.Series')
            unit='';tt=[];vv=[];
            try,unit=char(child.unit);tt=double(time(child));vv=double(values(child));catch,continue;end
            if isempty(tt)||isempty(vv),continue;end
            tt=double(tt(:));vv=double(vv);
            if size(vv,1)~=numel(tt)&&size(vv,2)==numel(tt),vv=vv.';end
            if size(vv,1)~=numel(tt)||any(~isfinite(tt))|| ...
                    any(~isfinite(real(vv(:))))||any(~isfinite(imag(vv(:))))
                continue
            end
            [tt,ia]=unique(tt,'stable');vv=vv(ia,:);
            if numel(tt)<2,continue;end
            fullPath=[parent '/' key];vr=real(vv);vi=imag(vv);
            tok=regexp(parent,'/Grid/(Bus16_1|Bus17|Bus16_2)/I([0-9]+)$','tokens','once');
            if ~isempty(tok)&&strcmp(unit,'A')
                busRows(end+1)=struct('path',fullPath,'bus_section',tok{1}, ...
                    'port_index',str2double(tok{2}),'unit',unit,'time_s',tt(:)', ...
                    'values_real',vr,'values_imag',vi); %#ok<AGROW>
                continue
            end
            tok=regexp(parent,'/Grid/(B16_to_B17)/phase_splitter([12])/I/instantaneous$','tokens','once');
            if ~isempty(tok)&&strcmp(unit,'A')
                lineRows(end+1)=struct('path',fullPath,'component',tok{1}, ...
                    'terminal',str2double(tok{2}),'unit',unit,'time_s',tt(:)', ...
                    'values_real',vr,'values_imag',vi); %#ok<AGROW>
                continue
            end
            if ~isempty(regexp(parent,'/Grid/Fault_Three_Phase/I/instantaneous$','once'))&&strcmp(unit,'A')
                faultRows(end+1)=struct('path',fullPath,'unit',unit,'time_s',tt(:)', ...
                    'values_real',vr,'values_imag',vi); %#ok<AGROW>
            end
        end
    end
end
assert(numel(busRows)>=4,'AEFC:Bus16PortProbeBus','Expected four Bus16_1 I# series.');
assert(any(strcmp({busRows.bus_section},'Bus16_1')),'AEFC:Bus16PortProbeBus','Bus16_1 current series missing.');
assert(numel(lineRows)==2,'AEFC:Bus16PortProbeLine','Expected both B16-B17 terminal current vectors.');
assert(numel(faultRows)==1,'AEFC:Bus16PortProbeFault','Expected one three-phase fault current vector.');
outDir=fullfile(repo,'results','ieee39_safety_mapping');if ~exist(outDir,'dir'),mkdir(outDir);end
info=struct('model',model,'release','MATLAB R2024b','seed',80,'method','AEFC-Full', ...
    'fault_start_s',5.0,'fault_duration_s',0.1,'stop_time_s',double(p.stop_time_s), ...
    'simscape_nodes_visited',visited,'bus_port_current_series',busRows, ...
    'line_terminal_current_series',lineRows,'fault_current_series',faultRows, ...
    'interpretation',['Single-episode instrumentation probe for Bus16_1 I# to RConn1 identity. ' ...
    'It is not a recovery-effect sample and does not certify thermal or full-network safety.']);
fp=fullfile(outDir,'native_ieee39_bus16_port_current_fault_probe_v1.json');
fid=fopen(fp,'w');assert(fid>0);fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Bus16 port current probe: %d bus-port series, %d adjacent-line terminal vectors, %d fault-current vector.\n', ...
    numel(busRows),numel(lineRows),numel(faultRows));
try,set_param(model,'FastRestart','off');catch,end
try,close_system(model,0);catch,end
end
