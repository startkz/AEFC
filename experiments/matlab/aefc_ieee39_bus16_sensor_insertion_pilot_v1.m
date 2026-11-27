function aefc_ieee39_bus16_sensor_insertion_pilot_v1
% Insert one three-phase line-voltage sensor at Bus16_1 and one series
% current sensor at B16-B17 terminal 1. Compare routed sensor signals with
% native Simscape logs. This is a measurement-path pilot, not certification.
repo=pwd;
p=jsondecode(fileread(fullfile(repo,'configs','ieee39_native_fault_recovery_protocol_r1.json')));
loc=jsondecode(fileread(fullfile(repo,'configs','ieee39_native_fault_recovery_protocol_r1_location_addendum.json')));
model=char(p.model);modelPath=fullfile(repo,'results','ieee39_r2024b',[model '.slx']);
if exist(modelPath,'file')~=2,aefc_ieee39_build_stress;end
load_system(modelPath);
grid=[model '/Grid'];ctrl=[model '/AEFC_NATIVE_CONTROLLER'];harness=[model '/AEFC_NATIVE_ATTACK_SOURCE'];
fault=[grid '/Fault (Three-Phase)'];
assert(strcmp(char(get_param(fault,'enable_temporal_fault')),'1'));
assert(endsWith(char(loc.fault.physical_bus_section),'/Bus16_1') || strcmp(char(loc.fault.physical_bus_section),'Bus16_1'));
assert(endsWith(char(loc.fault.connected_transmission_line),'/B16 to B17') || strcmp(char(loc.fault.connected_transmission_line),'B16 to B17'));
assert(abs(str2double(get_param(fault,'fault_start_time'))-5.0)<1e-9);
assert(abs(str2double(get_param(fault,'fault_duration'))-0.1)<1e-9);
set_param(ctrl,'MethodCode','7','ExploratoryMode','false');
set_param(harness,'ScenarioCode','1','Seed','80','AttackScale','1','StressAmplitude','0');
try,set_param(model,'FastRestart','off');catch,end

% Native sensor library blocks. Ports were independently confirmed by
% a successful connection test against the PS-Simulink Converter.
lineVoltageLib=['ee_lib/Sensors &' newline 'Transducers/Line Voltage Sensor' newline '(Three-Phase)'];
currentSensorLib=['ee_lib/Sensors &' newline 'Transducers/Current Sensor' newline '(Three-Phase)'];
ps2slLib=['nesl_utility/PS-Simulink' newline 'Converter'];
vSensor=[grid '/AEFC_BUS16_LINE_VOLTAGE_SENSOR'];
iSensor=[grid '/AEFC_B16_B17_CURRENT_SENSOR'];
vConv=[grid '/AEFC_BUS16_V_PS2SL'];
iConv=[grid '/AEFC_B16_B17_I_PS2SL'];
vToWs=[grid '/AEFC_BUS16_V_TOWS'];
iToWs=[grid '/AEFC_B16_B17_I_TOWS'];
paths={vSensor,iSensor,vConv,iConv,vToWs,iToWs};
for k=1:numel(paths),if getSimulinkBlockHandle(paths{k})>0,delete_block(paths{k});end,end
add_block(lineVoltageLib,vSensor,'Position',[950 180 1100 240]);
add_block(currentSensorLib,iSensor,'Position',[950 360 1100 430]);
add_block(ps2slLib,vConv,'Position',[1180 180 1320 230]);
add_block(ps2slLib,iConv,'Position',[1180 360 1320 410]);
add_block('simulink/Sinks/To Workspace',vToWs,'VariableName','AEFC_BUS16_V_SENSOR', ...
 'SaveFormat','Structure With Time','MaxDataPoints','inf','Decimation','1', ...
 'Position',[1400 180 1540 220]);
add_block('simulink/Sinks/To Workspace',iToWs,'VariableName','AEFC_B16_B17_I_SENSOR', ...
 'SaveFormat','Structure With Time','MaxDataPoints','inf','Decimation','1', ...
 'Position',[1400 360 1540 400]);

% Verified physical endpoints: Bus16_1/RConn1 <-> B16 to B17/LConn1.
busPorts=get_param([grid '/Bus16_1'],'PortHandles');
linePorts=get_param([grid '/B16 to B17'],'PortHandles');
busR=busPorts.RConn(1);lineL=linePorts.LConn(1);
busLineSet=double(get_param(busR,'Line'));
try,busLineSet=[busLineSet;double(get_param(busLineSet(1),'LineParent'))];catch,end
try
    lineChildren=get_param(busLineSet(1),'LineChildren');
    busLineSet=[busLineSet;double(lineChildren(:))];
catch
end
busLineSet=unique(busLineSet(isfinite(busLineSet)&busLineSet>0));
lineLHandle=double(get_param(lineL,'Line'));
assert(~isempty(busLineSet)&&lineLHandle>0,'AEFC:SensorPilotConnection','Bus16_1/RConn1 or B16-B17/LConn1 is not physically connected');
assert(any(abs(busLineSet-lineLHandle)<1e-6),'AEFC:SensorPilotConnection','B16-B17/LConn1 is not a branch of the Bus16_1/RConn1 composite connection');
assert(faultConnectedToBus(fault,[grid '/Bus16_1']),'AEFC:SensorPilotFault','Fault is not connected to Bus16_1 before insertion');

% Remove only the Bus16_1-to-line branch. Bus16_1/RConn1 is a composite node
% also connected to the native fault; deleting the whole line handle would
% risk removing the fault branch.
delete_line(lineLHandle);
vPorts=get_param(vSensor,'PortHandles');
iPorts=get_param(iSensor,'PortHandles');
vC=get_param(vConv,'PortHandles');iC=get_param(iConv,'PortHandles');
vW=get_param(vToWs,'PortHandles');iW=get_param(iToWs,'PortHandles');
assert(isfield(vPorts,'LConn')&&isfield(vPorts,'RConn')&&numel(vPorts.RConn)>=1);
assert(isfield(iPorts,'LConn')&&isfield(iPorts,'RConn')&&numel(iPorts.RConn)>=2);
% Current sensor: LConn1/RConn2 are conserving ports; RConn1 is PS output.
add_line(grid,busR,iPorts.LConn(1),'autorouting','on');
add_line(grid,iPorts.RConn(2),lineL,'autorouting','on');
assert(get_param(busR,'Line')>0 && get_param(lineL,'Line')>0,'AEFC:SensorPilotSeries','Current sensor did not reconnect both series endpoints');
assert(faultConnectedToBus(fault,[grid '/Bus16_1']),'AEFC:SensorPilotFault','Fault branch was lost during current-sensor insertion');
% Line-voltage sensor is a one-port shunt sensor at the Bus16_1 node.
add_line(grid,busR,vPorts.LConn(1),'autorouting','on');
% PS outputs to PS-Simulink Converter inputs.
add_line(grid,vPorts.RConn(1),vC.LConn(1),'autorouting','on');
add_line(grid,iPorts.RConn(1),iC.LConn(1),'autorouting','on');
% Converted Simulink signals to To Workspace sinks.
add_line(grid,vC.Outport(1),vW.Inport(1),'autorouting','on');
add_line(grid,iC.Outport(1),iW.Inport(1),'autorouting','on');

set_param(model,'SimscapeLogType','all','SimscapeLogName','AEFC_BUS16_SENSOR_PILOT_SIMLOG');
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
sensorV=readWorkspaceSeries(out,'AEFC_BUS16_V_SENSOR');
sensorI=readWorkspaceSeries(out,'AEFC_B16_B17_I_SENSOR');
assert(numel(sensorV.time_s)>=2&&numel(sensorI.time_s)>=2,'AEFC:SensorPilotSamples','Missing routed sensor samples');

logNode=[];
try,logNode=out.get('AEFC_BUS16_SENSOR_PILOT_SIMLOG');catch,end
if ~isa(logNode,'simscape.logging.Node')
 try,logNode=simscape.logging.getSimulationLog(model);catch,end
end
assert(isa(logNode,'simscape.logging.Node'),'AEFC:SensorPilotLog','Missing native Simscape log.');
busRows=struct('path',{},'bus_section',{},'unit',{},'time_s',{},'values_real',{},'values_imag',{});
speedRows=struct('path',{},'generator',{},'unit',{},'time_s',{},'values_real',{},'values_imag',{});
lineRows=struct('path',{},'component',{},'terminal',{},'unit',{},'time_s',{},'values_real',{},'values_imag',{});
stack={logNode};paths2={model};head=1;visited=0;maxNodes=100000;maxDepth=28;
while head<=numel(stack)&&visited<maxNodes
 nd=stack{head};parent=paths2{head};head=head+1;visited=visited+1;
 if numel(strsplit(parent,'/'))>maxDepth,continue;end
 names=properties(nd);
 for j=1:numel(names)
  key=names{j};child=[];
  try,child=nd.(key);catch,end
  if isa(child,'simscape.logging.Node')
   stack{end+1}=child;paths2{end+1}=[parent '/' key]; %#ok<AGROW>
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
   vr=real(vv);vi=imag(vv);
   if strcmp(key,'Vt')
    tok=regexp(parent,'/Grid/(Bus[0-9]+(?:_[0-9]+)?)$','tokens','once');
    if ~isempty(tok)
     busRows(end+1)=struct('path',[parent '/' key],'bus_section',tok{1}, ...
      'unit',unit,'time_s',tt(:)','values_real',vr,'values_imag',vi); %#ok<AGROW>
     continue
    end
   end
   if strcmp(key,'w')
    tok=regexp(parent,'/Generators/(Gen[0-9]+@Bus[0-9]+)/Governor$','tokens','once');
    if ~isempty(tok)
     speedRows(end+1)=struct('path',[parent '/' key],'generator',tok{1}, ...
      'unit',unit,'time_s',tt(:)','values_real',vr,'values_imag',vi); %#ok<AGROW>
     continue
    end
   end
   if strcmp(key,'instantaneous')
    tok=regexp(parent,'/Grid/B16 to B17/phase_splitter([12])/I$','tokens','once');
    if ~isempty(tok)&&strcmp(unit,'A')
     lineRows(end+1)=struct('path',[parent '/' key],'component','B16 to B17', ...
      'terminal',str2double(tok{1}),'unit',unit,'time_s',tt(:)', ...
      'values_real',vr,'values_imag',vi); %#ok<AGROW>
    end
   end
  end
 end
end
assert(numel(busRows)==41,'AEFC:SensorPilotBusCoverage','Expected 41 bus Vt series, got %d',numel(busRows));
assert(numel(speedRows)==10,'AEFC:SensorPilotSpeedCoverage','Expected 10 generator speed series, got %d',numel(speedRows));
assert(numel(lineRows)==2,'AEFC:SensorPilotLineCoverage','Expected two B16-B17 terminal current series, got %d',numel(lineRows));
info=struct();
info.model=model;info.release='MATLAB R2024b';info.method='AEFC-Full';info.seed=80;
info.fault_start_s=5.0;info.fault_duration_s=0.1;info.stop_time_s=double(p.stop_time_s);
info.sensor_topology=struct('bus_voltage_sensor','Line Voltage Sensor (Three-Phase)', ...
 'bus_voltage_sensor_physical_port','LConn1','bus_voltage_sensor_ps_output','RConn1', ...
 'current_sensor','Current Sensor (Three-Phase)','current_sensor_series_ports',{{'LConn1','RConn2'}}, ...
 'current_sensor_ps_output','RConn1','current_sensor_inserted_between', ...
 'Bus16_1/RConn1 and B16 to B17/LConn1');
info.converter_output_units=struct('voltage',safeParam(vConv,'OutputSignalUnit'), ...
 'current',safeParam(iConv,'OutputSignalUnit'));
info.sensor_voltage_series=sensorV;info.sensor_current_series=sensorI;
info.bus_voltage_series=busRows;info.generator_speed_series=speedRows;
info.line_terminal_current_series=lineRows;
info.simscape_nodes_visited=visited;
info.interpretation=['Single-point sensor insertion pilot. Sensor outputs are compared to offline Simscape logs ' ...
 'and the no-sensor ten-seed baseline in an independent audit. This is not a full-grid sensor or safety certificate.'];
outDir=fullfile(repo,'results','ieee39_safety_mapping');if ~exist(outDir,'dir'),mkdir(outDir);end
fp=fullfile(outDir,'native_ieee39_bus16_sensor_insertion_pilot_v1.json');
fid=fopen(fp,'w');assert(fid>0,'AEFC:SensorPilotIO','Cannot write sensor pilot artifact');
fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Sensor insertion pilot captured: %d bus Vt, %d generator speeds, %d line current series.\n', ...
 numel(busRows),numel(speedRows),numel(lineRows));
try,set_param(model,'FastRestart','off');catch,end
try,close_system(model,0);catch,end
end

function s=readWorkspaceSeries(out,name)
x=out.get(name);t=[];v=[];
if isa(x,'timeseries')
 t=double(x.Time(:));v=double(x.Data);
elseif isstruct(x)&&isfield(x,'time')&&isfield(x,'signals')
 t=double(x.time(:));sig=x.signals;
 if numel(sig)==1
  v=double(sig.values);
 else
  cols=cell(1,numel(sig));
  for k=1:numel(sig),cols{k}=double(sig(k).values);end
  v=cat(2,cols{:});
 end
else
 error('AEFC:SensorPilotWorkspace','Unsupported workspace signal type %s',class(x));
end
if size(v,1)~=numel(t)&&size(v,2)==numel(t),v=v.';end
assert(size(v,1)==numel(t),'AEFC:SensorPilotWorkspaceShape','Signal %s has inconsistent time/data dimensions',name);
s=struct('time_s',t(:)','values_real',real(v),'values_imag',imag(v),'class',class(x));
end
function tf=faultConnectedToBus(fault,busPath)
tf=false;
try
 pc=get_param(fault,'PortConnectivity');
 busHandle=get_param(busPath,'Handle');
 for k=1:numel(pc)
  hs=[pc(k).SrcBlock(:);pc(k).DstBlock(:)];
  if any(hs==busHandle),tf=true;return;end
 end
catch
end
end
function x=safeParam(h,n)
try,x=get_param(h,n);catch,x='';end
end
