function aefc_ieee39_mapping_probe
% Validate native IEEE39 observation/actuation candidates on a disposable
% copy of the official MathWorks model. Headless GitHub runners do not
% reliably expose line signal logging as logsout for this example, so the
% probe uses explicit To Workspace sinks with ReturnWorkspaceOutputs=on.
repo=pwd;
resDir=fullfile(repo,'results','ieee39_r2024b');
discPath=fullfile(resDir,'interface_discovery.json');
assert(exist(discPath,'file')==2,'AEFC:DiscoveryMissing','Run interface discovery first.');
disc=jsondecode(fileread(discPath));

nObs=4; nAct=4;
obs=pickUnique(disc.observation_edges,nObs,'observation');
ctrl=pickUnique(disc.control_edges,nAct,'control');
assert(numel(obs)>=nObs,'AEFC:ObservationMapping','Need at least %d distinct observation edges; found %d.',nObs,numel(obs));
assert(numel(ctrl)>=nAct,'AEFC:ControlMapping','Need at least %d distinct control edges; found %d.',nAct,numel(ctrl));

[original,sourcePath]=aefc_ieee39_load_official;
probeModel='IEEE39BusSystem_AEFCProbe';
probePath=fullfile(resDir,[probeModel '.slx']);
if bdIsLoaded(original), close_system(original,0); end
if bdIsLoaded(probeModel), close_system(probeModel,0); end
if exist(probePath,'file')==2, delete(probePath); end
[okCopy,msg]=copyfile(sourcePath,probePath,'f');
assert(okCopy,'AEFC:ProbeCopy','Could not copy official IEEE39 model: %s',msg);
load_system(probePath);
assert(bdIsLoaded(probeModel),'AEFC:ProbeLoad','Probe model did not load as %s.',probeModel);
try, set_param(probeModel,'ReturnWorkspaceOutputs','on'); catch, end
try, set_param(probeModel,'SignalLogging','off'); catch, end

obsNames=cell(nObs,1);
for i=1:nObs
    src=translatePath(obs(i).src_block,original,probeModel);
    parent=get_param(src,'Parent'); makeEditable(parent);
    ph=get_param(src,'PortHandles');
    assert(numel(ph.Outport)>=obs(i).src_port,'AEFC:ObservationPort','Missing observation port on %s',src);
    sp=ph.Outport(obs(i).src_port);
    obsNames{i}=sprintf('AEFC_PROBE_OBS_%02d',i);
    tw=[parent sprintf('/AEFC_PROBE_TOWS_%02d',i)];
    if getSimulinkBlockHandle(tw)>0, delete_block(tw); end
    pos=get_param(src,'Position'); x=pos(3)+80; y=pos(2)+25*i;
    add_block('simulink/Sinks/To Workspace',tw,'VariableName',obsNames{i},'SaveFormat','Timeseries','Position',[x y x+105 y+30]);
    twPH=get_param(tw,'PortHandles'); add_line(parent,sp,twPH.Inport,'autorouting','on');
end

injBlocks=cell(nAct,1);
for j=1:nAct
    src=translatePath(ctrl(j).src_block,original,probeModel);
    dst=translatePath(ctrl(j).dst_block,original,probeModel);
    parent=get_param(src,'Parent');
    assert(strcmp(parent,get_param(dst,'Parent')),'AEFC:CrossHierarchy','Control edge crosses hierarchy: %s -> %s',src,dst);
    makeEditable(parent);
    srcPH=get_param(src,'PortHandles'); dstPH=get_param(dst,'PortHandles');
    assert(numel(srcPH.Outport)>=ctrl(j).src_port,'AEFC:ControlSourcePort','Missing source port on %s',src);
    assert(numel(dstPH.Inport)>=ctrl(j).dst_port,'AEFC:ControlDestPort','Missing destination port on %s',dst);
    sp=srcPH.Outport(ctrl(j).src_port); dp=dstPH.Inport(ctrl(j).dst_port);
    pos=get_param(dst,'Position'); x=max(10,pos(1)-150); y=pos(2)+25*(j-1);
    sumPath=[parent sprintf('/AEFC_PROBE_SUM_%02d',j)]; cPath=[parent sprintf('/AEFC_PROBE_INJ_%02d',j)];
    if getSimulinkBlockHandle(sumPath)>0, delete_block(sumPath); end
    if getSimulinkBlockHandle(cPath)>0, delete_block(cPath); end
    add_block('simulink/Math Operations/Sum',sumPath,'Inputs','++','Position',[x y x+35 y+35]);
    add_block('simulink/Sources/Constant',cPath,'Value','0','Position',[x-100 y+45 x-55 y+75]);
    sumPH=get_param(sumPath,'PortHandles'); cPH=get_param(cPath,'PortHandles');
    delete_line(parent,sp,dp);
    add_line(parent,sp,sumPH.Inport(1),'autorouting','on');
    add_line(parent,cPH.Outport,sumPH.Inport(2),'autorouting','on');
    add_line(parent,sumPH.Outport,dp,'autorouting','on');
    injBlocks{j}=cPath;
end
save_system(probeModel);

probeStop=0.30; epsilon=1e-3;
for j=1:nAct, set_param(injBlocks{j},'Value','0'); end
fastRestart=false;
try, set_param(probeModel,'FastRestart','on'); fastRestart=true; catch, end
y0=runAndRead(probeModel,probeStop,obsNames);
B=nan(nObs,nAct); ok=false(1,nAct); err=cell(1,nAct);
for j=1:nAct
    for q=1:nAct, set_param(injBlocks{q},'Value','0'); end
    set_param(injBlocks{j},'Value',num2str(epsilon,'%.17g'));
    try
        y1=runAndRead(probeModel,probeStop,obsNames);
        B(:,j)=(y1-y0)/epsilon;
        ok(j)=all(isfinite(B(:,j))) && norm(B(:,j),2)>1e-7;
        if ~ok(j), err{j}='finite response below 1e-7 norm'; end
    catch ME
        err{j}=[ME.identifier ': ' ME.message];
    end
end
if fastRestart, try, set_param(probeModel,'FastRestart','off'); catch, end, end
Bfinite=B; Bfinite(~isfinite(Bfinite))=0; rankB=rank(Bfinite);

mapping=struct;
mapping.model='IEEE39BusSystem'; mapping.release=version('-release');
mapping.mapping_type='native_r2024b_causal_probe';
mapping.observation_edges=obs; mapping.control_edges=ctrl;
mapping.observation_workspace_names=obsNames;
mapping.observation_transform='real scalar; complex native signals are mapped to magnitude';
mapping.baseline_observation=y0(:)'; mapping.probe_stop_time=probeStop; mapping.probe_epsilon=epsilon;
mapping.sensitivity_matrix=B; mapping.control_valid=ok; mapping.control_errors=err;
mapping.sensitivity_rank=rankB; mapping.fast_restart=fastRestart;
mapping.validated=all(ok) && rankB>=min(2,min(size(B)));
mapping.validation_rule='Each selected actuator must cause a finite nontrivial response in explicit native IEEE39 observations; sensitivity matrix rank must be at least two.';
mapping.probe_model_file=strrep(probePath,[repo filesep],'');
writejson(fullfile(resDir,'interface_mapping.json'),mapping);
status=struct('validated',mapping.validated,'valid_controls',sum(ok),'requested_controls',nAct,'sensitivity_rank',rankB,'mapping_file','results/ieee39_r2024b/interface_mapping.json');
writejson(fullfile(resDir,'mapping_status.json'),status);
close_system(probeModel,0);
assert(mapping.validated,'AEFC:MappingProbeFailed','Native mapping probe did not validate all requested actuator edges. Review interface_mapping.json.');
end

function selected=pickUnique(edges,n,kind)
selected=edges([]); seen={};
for i=1:numel(edges)
    if strcmp(kind,'observation'), key=sprintf('%s|%d',edges(i).src_block,edges(i).src_port);
    else, key=sprintf('%s|%d|%s|%d',edges(i).src_block,edges(i).src_port,edges(i).dst_block,edges(i).dst_port); end
    if any(strcmp(seen,key)), continue; end
    selected(end+1)=edges(i); %#ok<AGROW>
    seen{end+1}=key; %#ok<AGROW>
    if numel(selected)>=n, break; end
end
end

function p=translatePath(p,oldRoot,newRoot)
if startsWith(p,[oldRoot '/']), p=[newRoot p(numel(oldRoot)+1:end)]; elseif strcmp(p,oldRoot), p=newRoot; end
end

function makeEditable(block)
try, s=get_param(block,'LinkStatus'); if strcmp(s,'resolved'), set_param(block,'LinkStatus','inactive'); end, catch, end
end

function y=runAndRead(model,stopTime,names)
simIn=Simulink.SimulationInput(model);
simIn=simIn.setModelParameter('StopTime',num2str(stopTime,'%.17g'),'ReturnWorkspaceOutputs','on');
out=sim(simIn); y=zeros(numel(names),1);
for i=1:numel(names)
    try, v=out.get(names{i}); catch, v=[]; end
    if isempty(v), error('AEFC:WorkspaceOutputMissing','To Workspace output %s is missing from SimulationOutput.',names{i}); end
    data=extractData(v); data=double(data); data=squeeze(data);
    if ~isreal(data), data=abs(data); end
    data=data(:); data=data(isfinite(data));
    assert(~isempty(data),'AEFC:SignalEmpty','No finite samples for %s.',names{i});
    first=max(1,numel(data)-9); y(i)=mean(data(first:end));
end
end

function d=extractData(v)
if isa(v,'timeseries'), d=v.Data;
elseif isa(v,'Simulink.SimulationData.Dataset'), assert(v.numElements>0,'AEFC:DatasetEmpty','Workspace Dataset is empty.'); el=v.getElement(1); d=extractData(el.Values);
elseif isa(v,'Simulink.SimulationData.Signal'), d=extractData(v.Values);
elseif isnumeric(v) || islogical(v), d=v;
elseif isstruct(v)
    if isfield(v,'signals') && isfield(v.signals,'values'), d=v.signals.values;
    elseif isfield(v,'Data'), d=v.Data;
    else, error('AEFC:WorkspaceFormat','Unsupported struct workspace output.'); end
else
    try, d=v.Data; catch, error('AEFC:WorkspaceFormat','Unsupported workspace output class %s.',class(v)); end
end
end

function writejson(path,obj)
fid=fopen(path,'w'); assert(fid>0,'AEFC:IO','Cannot open %s',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(obj,'PrettyPrint',true),'char'); fwrite(fid,sprintf('\n'),'char');
end
