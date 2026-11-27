function aefc_ieee39_online_measurement_port_audit_v1
% Inspect the native IEEE39-derived Simulink/Simscape model for existing
% signal-level measurement ports that could be routed to an independent
% online safety monitor. Simscape logging paths alone are NOT online ports.
repo=pwd;resDir=fullfile(repo,'results','ieee39_r2024b');
outDir=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(outDir,'dir'),mkdir(outDir);end
aefc_ieee39_build_stress;
model='IEEE39BusSystem_AEFCStress';
modelPath=fullfile(resDir,[model '.slx']);
assert(exist(modelPath,'file')==2,'AEFC:SensorPortModel','Native IEEE39 model missing.');
load_system(modelPath);
blocks=find_system(model,'LookUnderMasks','all','FollowLinks','on','Type','Block');

busBlocks={};lineBlocks={};transformerBlocks={};
for k=1:numel(blocks)
    b=blocks{k};
    if ~startsWith(b,[model '/Grid/']),continue;end
    [~,nm]=fileparts(b);
    if ~isempty(regexp(nm,'^Bus[0-9]+(_[0-9]+)?$','once'))
        busBlocks{end+1}=b; %#ok<AGROW>
    elseif ~isempty(regexp(nm,'^B[0-9]+ to B[0-9]+$','once'))
        lineBlocks{end+1}=b; %#ok<AGROW>
    elseif ~isempty(regexp(nm,'^TF[ _]B[0-9]+[ _]to[ _]B[0-9]+$','once'))
        transformerBlocks{end+1}=b; %#ok<AGROW>
    end
end
busBlocks=unique(busBlocks,'stable');lineBlocks=unique(lineBlocks,'stable');
transformerBlocks=unique(transformerBlocks,'stable');

busDetails=cell(size(busBlocks));lineDetails=cell(size(lineBlocks));
transformerDetails=cell(size(transformerBlocks));
for k=1:numel(busBlocks),busDetails{k}=describeComponent(busBlocks{k});end
for k=1:numel(lineBlocks),lineDetails{k}=describeComponent(lineBlocks{k});end
for k=1:numel(transformerBlocks),transformerDetails{k}=describeComponent(transformerBlocks{k});end

% Find existing measurement/conversion blocks anywhere in the native model.
candidateBlocks=struct('path',{},'name',{},'block_type',{},'mask_type',{},'reference_block',{},'port_handles',{});
candidateCount=0;
for k=1:numel(blocks)
    b=blocks{k}; nm=lower(char(get_param(b,'Name')));
    bt=lower(safeText(safeParam(b,'BlockType')));
    mt=lower(safeText(safeParam(b,'MaskType')));
    rb=lower(safeText(safeParam(b,'ReferenceBlock')));
    q=[nm ' ' bt ' ' mt ' ' rb];
    if contains(q,'sensor') || contains(q,'measurement') || ...
       contains(q,'ps-simulink') || contains(q,'simulink-ps') || ...
       contains(q,'voltage measurement') || contains(q,'current measurement')
        candidateCount=candidateCount+1;
        candidateBlocks(candidateCount)=struct('path',b, ...
            'name',char(get_param(b,'Name')),'block_type',safeText(safeParam(b,'BlockType')), ...
            'mask_type',safeText(safeParam(b,'MaskType')), ...
            'reference_block',safeText(safeParam(b,'ReferenceBlock')), ...
            'port_handles',{describePorts(b)}); %#ok<AGROW>
    end
end

ctrlPath=[model '/AEFC_NATIVE_CONTROLLER'];
obsMuxPath=[model '/AEFC_OBS_MUX'];
harnessPath=[model '/AEFC_NATIVE_ATTACK_SOURCE'];
controller=describeComponent(ctrlPath);
obsMux=describeComponent(obsMuxPath);
attackHarness=describeComponent(harnessPath);

% Explicitly list current signal routes and the sensor taps used by the
% existing controller. This is a wiring audit, not an integrity proof.
obsFrom=cell(4,1);
for k=1:4
    p=[model sprintf('/AEFC_OBS_FROM_%02d',k)];
    if any(strcmp(blocks,p)),obsFrom{k}=describeComponent(p);else,obsFrom{k}=struct('path',p,'missing',true);end
end

info=struct();
info.model=model;info.backend='MATLAB R2024b native Simulink/Simscape';
info.native_busbar_blocks=numel(busBlocks);
info.native_line_blocks=numel(lineBlocks);
info.native_transformer_blocks=numel(transformerBlocks);
info.busbar_blocks=busDetails;
info.line_blocks=lineDetails;
info.transformer_blocks=transformerDetails;
info.measurement_or_converter_candidate_block_count=candidateCount;
info.measurement_or_converter_candidate_blocks=candidateBlocks;
info.controller=controller;
info.observation_mux=obsMux;
info.observation_from_blocks=obsFrom;
info.attack_harness=attackHarness;
info.current_online_controller_physical_inputs=4;
info.current_online_controller_packet_inputs=1;
info.current_online_controller_total_top_level_inputs=2;
info.bus_voltage_simscape_log_is_online_signal=false;
info.line_terminal_current_simscape_log_is_online_signal=false;
info.transformer_winding_current_simscape_log_is_online_signal=false;
info.trusted_online_sensor_integrity_verified=false;
info.sensor_error_bounds_verified=false;
info.full_network_safety_certified=false;
info.interpretation=['This audit inventories existing block-level signal ports and measurement/converter blocks. ' ...
    'A Simscape logging Series path is not itself a routable controller input. The four existing controller ' ...
    'physical inputs remain the four generator rotor-speed channels. No online sensor integrity or error bound ' ...
    'is inferred from block existence or offline simulator logs.'];

fp=fullfile(outDir,'native_ieee39_online_measurement_port_audit_v1.json');
fid=fopen(fp,'w');assert(fid>0,'AEFC:SensorPortIO','Cannot write sensor-port audit');
fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Measurement-port audit: %d buses, %d lines, %d transformers, %d candidate sensor/converter blocks.\n', ...
    numel(busBlocks),numel(lineBlocks),numel(transformerBlocks),candidateCount);
try,close_system(model,0);catch,end
end

function d=describeComponent(block)
d=struct('path',block,'name',char(get_param(block,'Name')), ...
    'block_type',safeText(safeParam(block,'BlockType')), ...
    'mask_type',safeText(safeParam(block,'MaskType')), ...
    'reference_block',safeText(safeParam(block,'ReferenceBlock')), ...
    'port_handles',{describePorts(block)},'port_connectivity',struct([]), ...
    'descendant_block_count',0,'descendant_blocks',{{}},'error','');
try
    pc=get_param(block,'PortConnectivity');
    rec=struct('index',{},'type',{},'src_blocks',{},'src_ports',{},'dst_blocks',{},'dst_ports',{});
    for i=1:numel(pc)
        rec(end+1)=struct('index',i,'type',safeText(pc(i).Type), ...
            'src_blocks',{blockNames(pc(i).SrcBlock)}, ...
            'src_ports',safeNumeric(pc(i).SrcPort), ...
            'dst_blocks',{blockNames(pc(i).DstBlock)}, ...
            'dst_ports',safeNumeric(pc(i).DstPort)); %#ok<AGROW>
    end
    d.port_connectivity=rec;
catch ME
    d.error=ME.message;
end
try
    kids=find_system(block,'LookUnderMasks','all','FollowLinks','on','Type','Block');
    kids=kids(~strcmp(kids,block));
    d.descendant_block_count=numel(kids);
    names=cell(size(kids));
    for i=1:numel(kids)
        names{i}=struct('path',kids{i},'name',char(get_param(kids{i},'Name')), ...
            'block_type',safeText(safeParam(kids{i},'BlockType')), ...
            'mask_type',safeText(safeParam(kids{i},'MaskType')), ...
            'reference_block',safeText(safeParam(kids{i},'ReferenceBlock')));
    end
    d.descendant_blocks=names;
catch ME
    d.error=[d.error ' | ' ME.message];
end
end

function out=describePorts(block)
out=struct('field',{},'port_number',{},'port_type',{},'line_type',{}, ...
    'line_src_blocks',{},'line_dst_blocks',{});
try
    ph=get_param(block,'PortHandles');fields=fieldnames(ph);
    for i=1:numel(fields)
        hs=ph.(fields{i});
        for j=1:numel(hs)
            h=hs(j);ln=-1;lt='';src={};dst={};
            try,ln=get_param(h,'Line');catch,end
            if isnumeric(ln)&&isscalar(ln)&&ln>0
                try,lt=safeText(get_param(ln,'LineType'));catch,end
                try,src=blockNames(get_param(ln,'SrcBlockHandle'));catch,end
                try,dst=blockNames(get_param(ln,'DstBlockHandle'));catch,end
            end
            out(end+1)=struct('field',fields{i}, ...
                'port_number',safeParam(h,'PortNumber'), ...
                'port_type',safeText(safeParam(h,'PortType')), ...
                'line_type',lt,'line_src_blocks',{src},'line_dst_blocks',{dst}); %#ok<AGROW>
        end
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
