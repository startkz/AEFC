function aefc_ieee39_sensor_port_compatibility_probe_v1
% Test which ports of candidate three-phase Simscape sensors connect to a
% native PS-Simulink Converter. No IEEE39 network is modified.
outDir=fullfile(pwd,'results','ieee39_safety_mapping');
if ~exist(outDir,'dir'),mkdir(outDir);end
load_system('ee_lib');load_system('nesl_utility');
model='AEFC_IEEE39_SensorPortProbe';
if bdIsLoaded(model),close_system(model,0);end
new_system(model);open_system(model);
sensors={ ...
 'ee_lib/Sensors &', ...
};
% Exact library paths include embedded newlines in subsystem names.
sensors={ ...
 ['ee_lib/Sensors &' newline 'Transducers/Current Sensor' newline '(Three-Phase)'], ...
 ['ee_lib/Sensors &' newline 'Transducers/Phase Voltage Sensor' newline '(Three-Phase)'], ...
 ['ee_lib/Sensors &' newline 'Transducers/Line Voltage Sensor' newline '(Three-Phase)'], ...
 ['ee_lib/Sensors &' newline 'Transducers/Current and Voltage' newline 'Sensor (Three-Phase)'], ...
 ['ee_lib/Sensors &' newline 'Transducers/Voltage Sensor'], ...
 ['ee_lib/Sensors &' newline 'Transducers/Current Sensor']};
records=struct('library_path',{},'block_added',{},'port_handles',{}, ...
 'candidate_ps_connections',{},'connected_ps_port',{},'connection_error',{}, ...
 'mask_type',{},'dialog_parameters',{});
for k=1:numel(sensors)
 rec=struct('library_path',sensors{k},'block_added',false,'port_handles',struct([]), ...
  'candidate_ps_connections',struct([]),'connected_ps_port',struct(), ...
  'connection_error','','mask_type','','dialog_parameters',struct([]));
 try
  sb=[model '/Sensor' num2str(k)];
  cb=[model '/PS2SL' num2str(k)];
  add_block(sensors{k},sb,'Position',[80 40+100*k 260 100+100*k]);
  add_block('nesl_utility/PS-Simulink' newline 'Converter',cb, ...
   'Position',[420 60+100*k 580 100+100*k]);
  rec.block_added=true;rec.mask_type=safeText(safeParam(sb,'MaskType'));
  rec.port_handles=portSummary(sb);
  rec.dialog_parameters=dialogSummary(sb);
  cph=get_param(cb,'PortHandles');
  psIn=cph.LConn(1);
  ports=get_param(sb,'PortHandles');fields=fieldnames(ports);
  tries=struct('field',{},'port_number',{},'success',{},'error',{});
  for f=1:numel(fields)
   hs=ports.(fields{f});
   for j=1:numel(hs)
    h=hs(j);ok=false;err='';
    try
     ln=add_line(model,h,psIn,'autorouting','on');
     ok=true;
     rec.connected_ps_port=struct('field',fields{f},'port_number',j,'line_handle',double(ln));
     try,delete_line(ln);catch,end
    catch ME,err=ME.message;end
    tries(end+1)=struct('field',fields{f},'port_number',j,'success',ok,'error',err); %#ok<AGROW>
   end
  end
  rec.candidate_ps_connections=tries;
 catch ME
  rec.connection_error=ME.message;
 end
 records(end+1)=rec; %#ok<AGROW>
end
info=struct();info.model=model;info.sensor_candidates=records;
info.interpretation=['A successful port-to-PS-Simulink Converter connection identifies a physical-signal output. ' ...
 'The probe does not connect electrical conserving ports to an IEEE39 network or validate sensor accuracy.'];
fp=fullfile(outDir,'native_ieee39_sensor_port_compatibility_probe_v1.json');
fid=fopen(fp,'w');assert(fid>0,'AEFC:SensorProbeIO','Cannot write sensor compatibility probe');
fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
try,close_system(model,0);catch,end
fprintf('Sensor compatibility probe completed for %d candidate blocks.\n',numel(records));
end

function out=portSummary(block)
out=struct('field',{},'port_number',{},'port_type',{});
ph=get_param(block,'PortHandles');fields=fieldnames(ph);
for i=1:numel(fields)
 hs=ph.(fields{i});
 for j=1:numel(hs)
  out(end+1)=struct('field',fields{i},'port_number',j, ...
   'port_type',safeText(safeParam(hs(j),'PortType'))); %#ok<AGROW>
 end
end
end
function out=dialogSummary(block)
out=struct('name',{},'prompt',{},'value',{});
try
 p=get_param(block,'DialogParameters');names=fieldnames(p);
 for i=1:numel(names)
  n=names{i};pr='';v='';
  try,pr=safeText(p.(n).Prompt);catch,end
  try,v=safeText(get_param(block,n));catch,end
  out(end+1)=struct('name',n,'prompt',pr,'value',v); %#ok<AGROW>
 end
catch
end
end
function x=safeParam(h,n)
try,x=get_param(h,n);catch,x='';end
end
function x=safeText(v)
if ischar(v),x=v;elseif isstring(v),x=char(v);elseif isnumeric(v),x=mat2str(v);else,try,x=char(v);catch,x='';end,end
end
