function aefc_ieee39_mapping_probe
% Validate native IEEE39 observation/actuation candidates by instrumenting a
% disposable model copy, logging real signals, and applying small additive
% perturbations on candidate control edges.  Only causally responsive edges
% are emitted as validated mapping evidence.
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

original='IEEE39BusSystem';
try
    load_system(original);
catch
    openExample('simscapeelectrical/IEEE39BusSystemExample');
    load_system(original);
end
probeModel='IEEE39BusSystem_AEFCProbe';
probePath=fullfile(resDir,[probeModel '.slx']);
if bdIsLoaded(probeModel), close_system(probeModel,0); end
if exist(probePath,'file'), delete(probePath); end
save_system(original,probePath);
close_system(original,0);
load_system(probePath);
set_param(probeModel,'SignalLogging','on');
try, set_param(probeModel,'SignalLoggingName','logsout'); catch, end

obsNames=cell(nObs,1);
for i=1:nObs
    src=translatePath(obs(i).src_block,original,probeModel);
    ph=get_param(src,'PortHandles');
    assert(numel(ph.Outport)>=obs(i).src_port,'AEFC:ObservationPort','Missing observation port on %s',src);
    lh=get_param(ph.Outport(obs(i).src_port),'Line');
    assert(lh~=-1,'AEFC:ObservationLine','Observation edge has no line: %s',src);
    obsNames{i}=sprintf('AEFC_OBS_%02d',i);
    try, set_param(lh,'Name',obsNames{i}); catch, end
    try, set_param(lh,'DataLogging','on'); catch, end
    try, set_param(lh,'DataLoggingNameMode','Custom'); catch, end
    try, set_param(lh,'DataLoggingName',obsNames{i}); catch, end
end

injBlocks=cell(nAct,1);
for j=1:nAct
    src=translatePath(ctrl(j).src_block,original,probeModel);
    dst=translatePath(ctrl(j).dst_block,original,probeModel);
    parent=get_param(src,'Parent');
    assert(strcmp(parent,get_param(dst,'Parent')),'AEFC:CrossHierarchy','Control edge crosses hierarchy: %s -> %s',src,dst);
    srcPH=get_param(src,'PortHandles'); dstPH=get_param(dst,'PortHandles');
    sp=srcPH.Outport(ctrl(j).src_port); dp=dstPH.Inport(ctrl(j).dst_port);
    pos=get_param(dst,'Position');
    x=max(10,pos(1)-150); y=pos(2)+25*(j-1);
    sumPath=[parent sprintf('/AEFC_PROBE_SUM_%02d',j)];
    cPath=[parent sprintf('/AEFC_PROBE_INJ_%02d',j)];
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
save_system(probeModel,probePath);

probeStop=0.30; epsilon=1e-3;
for j=1:nAct, set_param(injBlocks{j},'Value','0'); end
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

mapping=struct;
mapping.model='IEEE39BusSystem';
mapping.release=version('-release');
mapping.mapping_type='native_r2024b_causal_probe';
mapping.observation_edges=obs;
mapping.control_edges=ctrl;
mapping.observation_signal_names=obsNames;
mapping.baseline_observation=y0(:)';
mapping.probe_epsilon=epsilon;
mapping.sensitivity_matrix=B;
mapping.control_valid=ok;
mapping.control_errors=err;
mapping.validated=all(ok) && rank(B)>=min(2,min(size(B)));
mapping.validation_rule='Each selected actuator must cause a finite nontrivial response in logged native IEEE39 signals; sensitivity matrix rank must be at least two.';
mapping.probe_model_file=strrep(probePath,[repo filesep],'');
writejson(fullfile(resDir,'interface_mapping.json'),mapping);

status=struct('validated',mapping.validated,'valid_controls',sum(ok),'requested_controls',nAct, ...
              'sensitivity_rank',rank(B),'mapping_file','results/ieee39_r2024b/interface_mapping.json');
writejson(fullfile(resDir,'mapping_status.json'),status);
close_system(probeModel,0);
assert(mapping.validated,'AEFC:MappingProbeFailed','Native mapping probe did not validate all requested actuator edges. Review interface_mapping.json.');
end

function selected=pickUnique(edges,n,kind)
selected=edges([]); seen={};
for i=1:numel(edges)
    if strcmp(kind,'observation')
        key=sprintf('%s|%d',edges(i).src_block,edges(i).src_port);
    else
        key=sprintf('%s|%d|%s|%d',edges(i).src_block,edges(i).src_port,edges(i).dst_block,edges(i).dst_port);
    end
    if any(strcmp(seen,key)), continue; end
    selected(end+1)=edges(i); %#ok<AGROW>
    seen{end+1}=key; %#ok<AGROW>
    if numel(selected)>=n, break; end
end
end

function p=translatePath(p,oldRoot,newRoot)
if startsWith(p,[oldRoot '/'])
    p=[newRoot p(numel(oldRoot)+1:end)];
elseif strcmp(p,oldRoot)
    p=newRoot;
end
end

function y=runAndRead(model,stopTime,names)
simIn=Simulink.SimulationInput(model);
simIn=simIn.setModelParameter('StopTime',num2str(stopTime,'%.17g'));
out=sim(simIn);
try
    logs=out.logsout;
catch
    error('AEFC:LogsoutMissing','Signal logging did not produce logsout.');
end
y=zeros(numel(names),1);
for i=1:numel(names)
    el=logs.get(names{i});
    if isempty(el), error('AEFC:SignalMissing','Missing logged signal %s',names{i}); end
    data=double(el.Values.Data);
    data=data(:);
    assert(~isempty(data),'AEFC:SignalEmpty','Empty logged signal %s',names{i});
    tail=data(max(1,end-min(9,numel(data)-1)):end);
    y(i)=mean(tail,'omitnan');
end
end

function writejson(path,obj)
fid=fopen(path,'w'); assert(fid>0,'AEFC:IO','Cannot open %s',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(obj,'PrettyPrint',true),'char'); fwrite(fid,sprintf('\n'),'char');
end
