function aefc_ieee39_build_native_model
% Build an editable native IEEE39 copy whose real logged observations feed
% AEFCNativeController. The shield output and post-shield attack leave the
% controller on separate ports and are added to the validated control edge
% in that order: original reference + shield correction + post-shield attack.
repo=pwd; resDir=fullfile(repo,'results','ieee39_r2024b');
mapPath=fullfile(resDir,'interface_mapping.json');
assert(exist(mapPath,'file')==2,'AEFC:MappingMissing','Validated mapping file is missing.');
m=jsondecode(fileread(mapPath));
assert(m.validated,'AEFC:MappingInvalid','interface_mapping.json is not validated.');
assert(numel(m.observation_edges)==4 && numel(m.control_edges)==4,'AEFC:MappingDimension','Expected 4 observation and 4 control edges.');

[original,~]=aefc_ieee39_load_official;
nativeModel='IEEE39BusSystem_AEFCNative';
nativePath=fullfile(resDir,[nativeModel '.slx']);
if bdIsLoaded(nativeModel), close_system(nativeModel,0); end
if exist(nativePath,'file'), delete(nativePath); end
save_system(original,nativePath);
if bdIsLoaded(original), close_system(original,0); end
if ~bdIsLoaded(nativeModel), load_system(nativePath); end
assert(bdIsLoaded(nativeModel),'AEFC:NativeModelLoad','Native AEFC model was not loaded after Save As.');
set_param(nativeModel,'SignalLogging','on');
try, set_param(nativeModel,'SignalLoggingName','logsout'); catch, end

% Top-level observation fan-in.
mux=[nativeModel '/AEFC_OBS_MUX'];
add_block('simulink/Signal Routing/Mux',mux,'Inputs','4','Position',[120 80 125 210]);
muxPH=get_param(mux,'PortHandles');
for i=1:4
    e=m.observation_edges(i);
    src=translatePath(e.src_block,original,nativeModel); parent=get_param(src,'Parent'); makeEditable(parent);
    srcPH=get_param(src,'PortHandles'); sp=srcPH.Outport(e.src_port);
    lh=get_param(sp,'Line');
    sig=sprintf('AEFC_NATIVE_OBS_%02d',i);
    if lh~=-1
        try, set_param(lh,'Name',sig); catch, end
        try, set_param(lh,'DataLogging','on'); catch, end
        try, set_param(lh,'DataLoggingNameMode','Custom'); catch, end
        try, set_param(lh,'DataLoggingName',sig); catch, end
    end
    tag=sprintf('AEFC_OBS_TAG_%02d',i);
    g=[parent sprintf('/AEFC_OBS_GOTO_%02d',i)];
    add_block('simulink/Signal Routing/Goto',g,'GotoTag',tag,'TagVisibility','global','Position',[40 40+35*i 115 60+35*i]);
    gPH=get_param(g,'PortHandles'); add_line(parent,sp,gPH.Inport,'autorouting','on');
    f=[nativeModel sprintf('/AEFC_OBS_FROM_%02d',i)];
    add_block('simulink/Signal Routing/From',f,'GotoTag',tag,'Position',[20 80+30*i 90 100+30*i]);
    fPH=get_param(f,'PortHandles'); add_line(nativeModel,fPH.Outport,muxPH.Inport(i),'autorouting','on');
end

ctrl=[nativeModel '/AEFC_NATIVE_CONTROLLER'];
add_block('simulink/User-Defined Functions/MATLAB System',ctrl, ...
    'System','AEFCNativeController','SimulateUsing','Interpreted execution', ...
    'Position',[210 105 390 195]);
try, set_param(nativeModel,'SimulationCommand','update'); catch, end
ctrlPH=get_param(ctrl,'PortHandles');
assert(numel(ctrlPH.Inport)>=1 && numel(ctrlPH.Outport)>=3,'AEFC:SystemPorts','AEFCNativeController did not expose 1 input and 3 outputs.');
add_line(nativeModel,muxPH.Outport,ctrlPH.Inport(1),'autorouting','on');

shieldDemux=[nativeModel '/AEFC_SHIELD_DEMUX']; attackDemux=[nativeModel '/AEFC_ATTACK_DEMUX'];
add_block('simulink/Signal Routing/Demux',shieldDemux,'Outputs','4','Position',[455 70 460 155]);
add_block('simulink/Signal Routing/Demux',attackDemux,'Outputs','4','Position',[455 175 460 260]);
sdPH=get_param(shieldDemux,'PortHandles'); adPH=get_param(attackDemux,'PortHandles');
lineShield=add_line(nativeModel,ctrlPH.Outport(1),sdPH.Inport,'autorouting','on');
lineAttack=add_line(nativeModel,ctrlPH.Outport(2),adPH.Inport,'autorouting','on');
try, set_param(lineShield,'Name','AEFC_SHIELD_VECTOR','DataLogging','on'); catch, end
try, set_param(lineAttack,'Name','AEFC_POST_ATTACK_VECTOR','DataLogging','on'); catch, end

diagLine=add_line(nativeModel,ctrlPH.Outport(3),addDiagSink(nativeModel),'autorouting','on');
try, set_param(diagLine,'Name','AEFC_DIAG','DataLogging','on','DataLoggingNameMode','Custom','DataLoggingName','AEFC_DIAG'); catch, end

% Distribute shield and post-shield signals to the validated actuator edges.
for i=1:4
    stag=sprintf('AEFC_USHIELD_TAG_%02d',i); atag=sprintf('AEFC_UATTACK_TAG_%02d',i);
    sg=[nativeModel sprintf('/AEFC_USHIELD_GOTO_%02d',i)]; ag=[nativeModel sprintf('/AEFC_UATTACK_GOTO_%02d',i)];
    add_block('simulink/Signal Routing/Goto',sg,'GotoTag',stag,'TagVisibility','global','Position',[520 55+30*i 600 75+30*i]);
    add_block('simulink/Signal Routing/Goto',ag,'GotoTag',atag,'TagVisibility','global','Position',[520 175+30*i 600 195+30*i]);
    sgPH=get_param(sg,'PortHandles'); agPH=get_param(ag,'PortHandles');
    add_line(nativeModel,sdPH.Outport(i),sgPH.Inport,'autorouting','on');
    add_line(nativeModel,adPH.Outport(i),agPH.Inport,'autorouting','on');

    e=m.control_edges(i);
    src=translatePath(e.src_block,original,nativeModel); dst=translatePath(e.dst_block,original,nativeModel);
    parent=get_param(src,'Parent'); assert(strcmp(parent,get_param(dst,'Parent')),'AEFC:CrossHierarchy','Control edge crosses hierarchy.'); makeEditable(parent);
    srcPH=get_param(src,'PortHandles'); dstPH=get_param(dst,'PortHandles'); sp=srcPH.Outport(e.src_port); dp=dstPH.Inport(e.dst_port);
    sumPath=[parent sprintf('/AEFC_NATIVE_SUM_%02d',i)];
    fs=[parent sprintf('/AEFC_USHIELD_FROM_%02d',i)]; fa=[parent sprintf('/AEFC_UATTACK_FROM_%02d',i)];
    pos=get_param(dst,'Position'); x=max(10,pos(1)-170); y=pos(2)+20*(i-1);
    add_block('simulink/Math Operations/Sum',sumPath,'Inputs','+++','Position',[x y x+35 y+40]);
    add_block('simulink/Signal Routing/From',fs,'GotoTag',stag,'Position',[x-115 y+45 x-45 y+65]);
    add_block('simulink/Signal Routing/From',fa,'GotoTag',atag,'Position',[x-115 y+75 x-45 y+95]);
    sumPH=get_param(sumPath,'PortHandles'); fsPH=get_param(fs,'PortHandles'); faPH=get_param(fa,'PortHandles');
    delete_line(parent,sp,dp);
    add_line(parent,sp,sumPH.Inport(1),'autorouting','on');
    add_line(parent,fsPH.Outport,sumPH.Inport(2),'autorouting','on');
    add_line(parent,faPH.Outport,sumPH.Inport(3),'autorouting','on');
    add_line(parent,sumPH.Outport,dp,'autorouting','on');
end

save_system(nativeModel,nativePath);
build=struct('model',nativeModel,'model_file',strrep(nativePath,[repo filesep],''), ...
    'mapping_file','results/ieee39_r2024b/interface_mapping.json', ...
    'controller','AEFCNativeController','observation_channels',4,'actuation_channels',4, ...
    'authority_order','native observation -> PATBU -> risk gate -> trust-gated adaptation -> robust shield -> post-shield attack -> validated native control edge');
writejson(fullfile(resDir,'native_model_build.json'),build);
close_system(nativeModel,0);
end

function sinkPH=addDiagSink(model)
p=[model '/AEFC_DIAG_TERMINATOR'];
add_block('simulink/Sinks/Terminator',p,'Position',[455 285 475 305]);
ph=get_param(p,'PortHandles'); sinkPH=ph.Inport;
end

function makeEditable(block)
try
    s=get_param(block,'LinkStatus');
    if strcmp(s,'resolved'), set_param(block,'LinkStatus','inactive'); end
catch
end
end

function p=translatePath(p,oldRoot,newRoot)
if startsWith(p,[oldRoot '/']), p=[newRoot p(numel(oldRoot)+1:end)]; elseif strcmp(p,oldRoot), p=newRoot; end
end

function writejson(path,obj)
fid=fopen(path,'w'); assert(fid>0,'AEFC:IO','Cannot open %s',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(obj,'PrettyPrint',true),'char'); fwrite(fid,sprintf('\n'),'char');
end
