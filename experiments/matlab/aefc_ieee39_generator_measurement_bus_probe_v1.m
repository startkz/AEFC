function aefc_ieee39_generator_measurement_bus_probe_v1
% Tap the existing top-level Generators measurement bus and inspect the
% runtime bus schema. The controller and physical network are not modified.
repo=pwd;resDir=fullfile(repo,'results','ieee39_r2024b');
outDir=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(outDir,'dir'),mkdir(outDir);end
aefc_ieee39_build_stress;
model='IEEE39BusSystem_AEFCStress';load_system(fullfile(resDir,[model '.slx']));
sink=[model '/AEFC_GEN_MEAS_BUS_TOWS'];
if getSimulinkBlockHandle(sink)>0,delete_block(sink);end
add_block('simulink/Sinks/To Workspace',sink,'VariableName','AEFC_GEN_MEAS_BUS', ...
 'SaveFormat','Structure With Time','MaxDataPoints','inf','Decimation','1', ...
 'Position',[950 120 1100 160]);
% Branch the already existing Generators output line to a workspace sink.
add_line(model,'Generators/1','AEFC_GEN_MEAS_BUS_TOWS/1','autorouting','on');
in=Simulink.SimulationInput(model);
in=in.setModelParameter('StopTime','0.10','ReturnWorkspaceOutputs','on');
out=sim(in);
bus=[];
try,bus=out.get('AEFC_GEN_MEAS_BUS');catch ME
 error('AEFC:GenBusProbeOutput','Cannot retrieve generator bus: %s',ME.message);
end
summary=summarizeValue(bus,'root');
info=struct();info.model=model;info.stop_time_s=0.10;
info.generator_bus_runtime_class=class(bus);
info.generator_bus_summary=summary;
info.generator_bus_channel_count=NaN;
info.generator_bus_first_sample_values=[];
info.generator_bus_last_sample_values=[];
info.generator_bus_time_s=[];
try
 if isstruct(bus)&&isfield(bus,'time')&&isfield(bus,'signals')&&isfield(bus.signals,'values')
  vv=double(bus.signals.values);tt=double(bus.time(:));
  if size(vv,1)~=numel(tt)&&size(vv,2)==numel(tt),vv=vv.';end
  info.generator_bus_channel_count=size(vv,2);
  info.generator_bus_first_sample_values=vv(1,:);
  info.generator_bus_last_sample_values=vv(end,:);
  info.generator_bus_time_s=[tt(1),tt(end)];
 end
catch
end
info.bus_object_name='';
info.bus_object_elements=struct([]);
info.bus_object_error='';
try
 bi=Simulink.Bus.createObject(model,[model '/Generators']);
 info.bus_object_name=bi.busName;
 bo=evalin('base',bi.busName);
 info.bus_object_elements=extractBusElements(bo,0);
catch ME
 info.bus_object_error=ME.message;
end
info.interpretation=['The runtime probe records the existing Generators subsystem signal bus. ' ...
 'It is a model-level measurement bus and not an independently authenticated field sensor stream.'];
fp=fullfile(outDir,'native_ieee39_generator_measurement_bus_probe_v1.json');
fid=fopen(fp,'w');assert(fid>0,'AEFC:GenBusProbeIO','Cannot write bus probe summary');
fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Generator measurement bus runtime probe completed; class=%s.\n',class(bus));
try,close_system(model,0);catch,end
end

function out=extractBusElements(busObj,depth)
out=struct('name',{},'data_type',{},'dimensions',{},'unit',{},'description',{},'nested',{},'error',{});
if depth>4,return;end
try
 els=busObj.Elements;
 for k=1:numel(els)
  e=els(k);nested=struct([]);
  dt=safeText(e.DataType);
  if startsWith(dt,'Bus:')
   nm=strtrim(extractAfter(dt,'Bus:'));
   try,nested=extractBusElements(evalin('base',nm),depth+1);catch,end
  end
  out(end+1)=struct('name',safeText(e.Name),'data_type',dt, ...
   'dimensions',safeText(e.Dimensions),'unit',safeText(e.Unit), ...
   'description',safeText(e.Description),'nested',nested,'error',''); %#ok<AGROW>
 end
catch ME
 out=struct('name','','data_type','','dimensions','','unit','','description','', ...
  'nested',struct([]),'error',ME.message);
end
end

function out=summarizeValue(v,path)
out=struct('path',path,'class',class(v),'size',size(v),'field_names',{{}}, ...
 'sample_count',NaN,'time_range',[],'children',{{}},'numeric_preview',[]);
if isstruct(v)
 fn=fieldnames(v);out.field_names=fn;children=cell(size(fn));
 for k=1:numel(fn)
  try,children{k}=summarizeValue(v(1).(fn{k}),[path '.' fn{k}]);catch,children{k}=struct('path',[path '.' fn{k}],'error','read_failed');end
 end
 out.children=children;
 if isfield(v,'time') && isnumeric(v(1).time)
  t=double(v(1).time(:));out.sample_count=numel(t);
  if ~isempty(t),out.time_range=[min(t),max(t)];end
 end
 if isfield(v,'signals')
  try
   s=v(1).signals;
   if isstruct(s)
    for j=1:numel(s)
     if isfield(s(j),'values')&&isnumeric(s(j).values)
      out.children{end+1}=summarizeValue(s(j).values,[path '.signals(' num2str(j) ').values']); %#ok<AGROW>
      if isfield(s(j),'label'),out.children{end}.signal_label=safeText(s(j).label);end
      if isfield(s(j),'dimensions'),out.children{end}.dimensions=s(j).dimensions;end
     end
    end
   end
  catch
  end
 end
elseif isnumeric(v)
 out.numeric_preview=double(v(1:min(numel(v),12)));
end
end
function x=safeText(v)
if ischar(v),x=v;elseif isstring(v),x=char(v);elseif isnumeric(v),x=mat2str(v);else,try,x=char(v);catch,x='';end,end
end
