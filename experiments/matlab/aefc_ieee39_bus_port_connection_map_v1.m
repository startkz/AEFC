function aefc_ieee39_bus_port_connection_map_v1
% Extract the native IEEE39 bus-port/branch connection evidence.
% This is a topology and offline current-signature audit, not an online
% sensor certificate, DAE state decomposition, or safety proof.
repo=pwd;resDir=fullfile(repo,'results','ieee39_r2024b');
outDir=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(outDir,'dir'),mkdir(outDir);end
aefc_ieee39_build_stress;
model='IEEE39BusSystem_AEFCStress';
modelPath=fullfile(resDir,[model '.slx']);
assert(exist(modelPath,'file')==2,'AEFC:PortMapModel','Native IEEE39 model missing.');
load_system(modelPath);
try,set_param(model,'FastRestart','off');catch,end

% First collect actual Simulink/Simscape block-port connectivity metadata.
allBlocks=find_system(model,'LookUnderMasks','all','FollowLinks','on','Type','Block');
busBlocks={};lineBlocks={};transformerBlocks={};
for k=1:numel(allBlocks)
    b=allBlocks{k};[~,nm]=fileparts(b);
    if ~isempty(regexp(nm,'^Bus[0-9]+(_[0-9]+)?$','once')) && contains(b,[model '/Grid/'])
        busBlocks{end+1}=b; %#ok<AGROW>
    elseif ~isempty(regexp(nm,'^B[0-9]+_to_B[0-9]+$','once')) && contains(b,[model '/Grid/'])
        lineBlocks{end+1}=b; %#ok<AGROW>
    elseif ~isempty(regexp(nm,'^TF_B[0-9]+_to_B[0-9]+$','once')) && contains(b,[model '/Grid/'])
        transformerBlocks{end+1}=b; %#ok<AGROW>
    end
end
busBlocks=unique(busBlocks,'stable');lineBlocks=unique(lineBlocks,'stable');
transformerBlocks=unique(transformerBlocks,'stable');
busConnectivity=cell(size(busBlocks));
lineConnectivity=cell(size(lineBlocks));
transformerConnectivity=cell(size(transformerBlocks));
for k=1:numel(busBlocks),busConnectivity{k}=describeBlock(busBlocks{k});end
for k=1:numel(lineBlocks),lineConnectivity{k}=describeBlock(lineBlocks{k});end
for k=1:numel(transformerBlocks),transformerConnectivity{k}=describeBlock(transformerBlocks{k});end

% Run a short native plant interval and preserve signed three-phase current
% traces for every bus port and every line/transformer branch current.
set_param(model,'SimscapeLogType','all','SimscapeLogName','AEFC_PORT_MAP_SIMLOG');
try,set_param(model,'SimulationCommand','update');catch,end
in=Simulink.SimulationInput(model);
in=in.setModelParameter('StopTime','0.05','ReturnWorkspaceOutputs','on');
out=sim(in);
logNode=[];
try,logNode=out.get('AEFC_PORT_MAP_SIMLOG');catch,end
if ~isa(logNode,'simscape.logging.Node')
    try,logNode=simscape.logging.getSimulationLog(model);catch,end
end
assert(isa(logNode,'simscape.logging.Node'),'AEFC:PortMapLog','Missing native Simscape logging Node.');

busPort=struct('path',{},'bus_section',{},'logical_bus',{},'port_index',{}, ...
    'unit',{},'time_s',{},'values_real',{},'values_imag',{},'is_complex',{});
branch=struct('path',{},'component',{},'component_type',{},'endpoint_bus_a',{}, ...
    'endpoint_bus_b',{},'variable',{},'phase',{},'unit',{},'time_s',{}, ...
    'values_real',{},'values_imag',{},'is_complex',{});
stack={logNode};paths={model};head=1;visited=0;maxNodes=100000;maxDepth=28;
while head<=numel(stack) && visited<maxNodes
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
            try
                unit=char(child.unit);tt=double(time(child));vv=double(values(child));
            catch
                continue
            end
            if isempty(tt)||isempty(vv),continue;end
            tt=double(tt(:));vv=double(vv);
            if size(vv,1)~=numel(tt) && size(vv,2)==numel(tt),vv=vv.';end
            if size(vv,1)~=numel(tt) || any(~isfinite(tt)) || ...
                    any(~isfinite(real(vv(:)))) || any(~isfinite(imag(vv(:))))
                continue
            end
            [tt,ia]=unique(tt,'stable');vv=vv(ia,:);
            if numel(tt)<2,continue;end
            fullPath=[parent '/' key];isC=~isreal(vv);
            vr=real(vv);vi=imag(vv);
            tok=regexp(parent,'/Grid/Bus([^/]+)/I([0-9]+)$','tokens','once');
            if ~isempty(tok) && strcmp(unit,'A')
                parts=strsplit(tok{1},'_');logicalBus=parts{1};
                busPort(end+1)=struct('path',fullPath,'bus_section',tok{1}, ...
                    'logical_bus',logicalBus,'port_index',str2double(tok{2}), ...
                    'unit',unit,'time_s',tt(:)','values_real',vr, ...
                    'values_imag',vi,'is_complex',isC); %#ok<AGROW>
                continue
            end
            tok=regexp(parent,'/Grid/([^/]+)/transmission_line/(inductor_[abc])/i/amplitude$', ...
                'tokens','once');
            if ~isempty(tok) && strcmp(unit,'A')
                ep=regexp(tok{1},'^B([0-9]+)_to_B([0-9]+)$','tokens','once');
                assert(~isempty(ep),'AEFC:LineEndpointName','Unexpected line component name %s',tok{1});
                branch(end+1)=struct('path',fullPath,'component',tok{1}, ...
                    'component_type','transmission_line','endpoint_bus_a',ep{1}, ...
                    'endpoint_bus_b',ep{2},'variable',[tok{2} '/i/amplitude'], ...
                    'phase',tok{2}(end),'unit',unit,'time_s',tt(:)', ...
                    'values_real',vr,'values_imag',vi,'is_complex',isC); %#ok<AGROW>
                continue
            end
            tok=regexp(parent,'/Grid/(TF_B[0-9]+_to_B[0-9]+)/(i1|i2)$','tokens','once');
            if ~isempty(tok) && strcmp(unit,'A')
                ep=regexp(tok{1},'^TF_B([0-9]+)_to_B([0-9]+)$','tokens','once');
                assert(~isempty(ep),'AEFC:TransformerEndpointName','Unexpected transformer name %s',tok{1});
                branch(end+1)=struct('path',fullPath,'component',tok{1}, ...
                    'component_type','transformer','endpoint_bus_a',ep{1}, ...
                    'endpoint_bus_b',ep{2},'variable',tok{2}, ...
                    'phase','abc','unit',unit,'time_s',tt(:)', ...
                    'values_real',vr,'values_imag',vi,'is_complex',isC); %#ok<AGROW>
            end
        end
    end
end
lineNames=unique({branch(strcmp({branch.component_type},'transmission_line')).component});
transformerNames=unique({branch(strcmp({branch.component_type},'transformer')).component});
busSections=unique({busPort.bus_section});
logicalBuses=unique({busPort.logical_bus});
assert(numel(busPort)==123,'AEFC:BusPortCount','Expected 123 bus port current Series, found %d',numel(busPort));
assert(numel(lineNames)==34,'AEFC:LineCount','Expected 34 lines, found %d',numel(lineNames));
assert(numel(transformerNames)==12,'AEFC:TransformerCount','Expected 12 transformers, found %d',numel(transformerNames));
assert(numel(branch)==126,'AEFC:BranchCurrentCount','Expected 126 branch current Series, found %d',numel(branch));
assert(numel(busSections)==41 && numel(logicalBuses)==39, ...
    'AEFC:BusSectionCount','Expected 41 physical sections and 39 logical buses.');
info=struct();
info.model=model;info.backend='MATLAB R2024b native IEEE39BusSystem Simulink/Simscape';
info.capture_stop_time_s=0.05;info.simscape_nodes_visited=visited;
info.bus_port_current_count=numel(busPort);info.bus_port_current_series=busPort;
info.physical_bus_sections=numel(busSections);info.physical_bus_section_names={busSections};
info.logical_bus_count=numel(logicalBuses);info.logical_bus_ids={logicalBuses};
info.line_component_count=numel(lineNames);info.line_component_names={lineNames};
info.transformer_component_count=numel(transformerNames);info.transformer_component_names={transformerNames};
info.branch_current_series_count=numel(branch);info.branch_current_series=branch;
info.simulink_bus_block_count=numel(busBlocks);info.simulink_line_block_count=numel(lineBlocks);
info.simulink_transformer_block_count=numel(transformerBlocks);
info.bus_block_connectivity=busConnectivity;
info.line_block_connectivity=lineConnectivity;
info.transformer_block_connectivity=transformerConnectivity;
info.full_network_safety_certified=false;
info.online_sensor_integrity_verified=false;
info.branch_thermal_limits_validated=false;
info.interpretation=['This artifact preserves 123 bus-port current traces, 102 line-phase current traces, ' ...
    '24 transformer-winding current traces, and Simulink port-connectivity metadata. ' ...
    'A port-to-component mapping is accepted only after endpoint/topology and signed-current ' ...
    'consistency are jointly checked. This is offline topology evidence, not online sensing or a safety certificate.'];
fp=fullfile(outDir,'native_ieee39_bus_port_connection_map_v1.json');
fid=fopen(fp,'w');assert(fid>0,'AEFC:PortMapIO','Cannot write connection map');
fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('IEEE39 bus-port connection evidence: %d bus ports, %d lines, %d transformers, %d branch current series.\n', ...
    numel(busPort),numel(lineNames),numel(transformerNames),numel(branch));
try,set_param(model,'FastRestart','off');catch,end
try,close_system(model,0);catch,end
end

function out=describeBlock(block)
out=struct('path',block,'name',get_param(block,'Name'),'block_type',safeParam(block,'BlockType'), ...
    'mask_type',safeParam(block,'MaskType'),'reference_block',safeParam(block,'ReferenceBlock'), ...
    'port_connectivity',struct([]),'port_handles',struct([]),'connectivity_error','');
try
    pc=get_param(block,'PortConnectivity');
    records=struct('index',{},'type',{},'position',{},'src_blocks',{}, ...
        'src_ports',{},'dst_blocks',{},'dst_ports',{});
    for i=1:numel(pc)
        records(end+1)=struct('index',i,'type',safeText(pc(i).Type), ...
            'position',safeNumeric(pc(i).Position), ...
            'src_blocks',{blockNames(pc(i).SrcBlock)}, ...
            'src_ports',safeNumeric(pc(i).SrcPort), ...
            'dst_blocks',{blockNames(pc(i).DstBlock)}, ...
            'dst_ports',safeNumeric(pc(i).DstPort)); %#ok<AGROW>
    end
    out.port_connectivity=records;
catch ME
    out.connectivity_error=ME.message;
end
try
    ph=get_param(block,'PortHandles');fields=fieldnames(ph);
    records=struct('field',{},'port_number',{},'port_type',{}, ...
        'line_type',{},'line_src_blocks',{},'line_dst_blocks',{});
    for i=1:numel(fields)
        hs=ph.(fields{i});
        for j=1:numel(hs)
            h=hs(j);ln=-1;lt='';
            try,ln=get_param(h,'Line');catch,end
            if isnumeric(ln) && isscalar(ln) && ln>0
                try,lt=safeText(get_param(ln,'LineType'));catch,end
                try,src=blockNames(get_param(ln,'SrcBlockHandle'));catch,src={};end
                try,dst=blockNames(get_param(ln,'DstBlockHandle'));catch,dst={};end
            else
                src={};dst={};
            end
            records(end+1)=struct('field',fields{i}, ...
                'port_number',safeParam(h,'PortNumber'), ...
                'port_type',safeParam(h,'PortType'),'line_type',lt, ...
                'line_src_blocks',{src},'line_dst_blocks',{dst}); %#ok<AGROW>
        end
    end
    out.port_handles=records;
catch ME
    out.connectivity_error=[out.connectivity_error ' | ' ME.message];
end
end

function x=safeParam(h,n)
try,x=safeText(get_param(h,n));catch,x='';end
end
function x=safeText(v)
if ischar(v),x=v;elseif isstring(v),x=char(v);elseif isnumeric(v),x=mat2str(v);else,try,x=char(v);catch,x='';end,end
end
function x=safeNumeric(v)
if isnumeric(v),x=double(v);else,x=[];end
end
function names=blockNames(handles)
names={};if isempty(handles),return;end
if iscell(handles),handles=[handles{:}];end
if ischar(handles)||isstring(handles),names=cellstr(handles);return;end
handles=double(handles(:)');
for h=handles
    if ~isfinite(h)||h<=0,continue;end
    try,names{end+1}=getfullname(h);catch %#ok<AGROW>
        try,names{end+1}=get_param(h,'Name');catch,end %#ok<AGROW>
    end
end
end
