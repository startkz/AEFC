function aefc_ieee39_generator_measurement_bus_audit_v1
% Read-only inventory of the native generator measurement bus and sink.
repo=pwd;resDir=fullfile(repo,'results','ieee39_r2024b');
outDir=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(outDir,'dir'),mkdir(outDir);end
aefc_ieee39_build_stress;
model='IEEE39BusSystem_AEFCStress';
load_system(fullfile(resDir,[model '.slx']));
genPath=[model '/Generators'];measPath=[model '/Measurements'];
assert(getSimulinkBlockHandle(genPath)>0,'AEFC:GenBusMissing','Generators subsystem missing');
assert(getSimulinkBlockHandle(measPath)>0,'AEFC:MeasBusMissing','Measurements subsystem missing');
gen=describeBlock(genPath);meas=describeBlock(measPath);
allMeas=find_system(measPath,'LookUnderMasks','all','FollowLinks','on','Type','Block');
allGen=find_system(genPath,'LookUnderMasks','all','FollowLinks','on','Type','Block');
measDetails=cell(size(allMeas));
for k=1:numel(allMeas),measDetails{k}=describeBlock(allMeas{k});end
genSummary=struct([]);
keep={};
for k=1:numel(allGen)
    b=allGen{k};
    nm=char(get_param(b,'Name'));
    bt=lower(safeText(safeParam(b,'BlockType')));
    mt=safeText(safeParam(b,'MaskType'));
    parts=strsplit(b,'/');
    leaf=parts{end};
    parent='';
    if numel(parts)>=2,parent=parts{end-1};end
    isMachineMeasurement=contains(mt,'Synchronous Machine')&&contains(mt,'Measurement');
    isBusCreator=contains(lower(nm),'bus')&&contains(lower(nm),'creator');
    isGeneratorBusOutport=strcmp(bt,'outport')&&~isempty(regexp(nm,'^mGen[0-9]+$','once'));
    converterNames={['PS-Simulink' char(10) 'Converter1'], ...
                    ['PS-Simulink' char(10) 'Converter11'], ...
                    ['PS-Simulink' char(10) 'Converter12']};
    isRootMeasurementConverter=~isempty(regexp(parent,'^Gen[0-9]+@Bus[0-9]+$','once')) ...
        && any(strcmp(leaf,converterNames));
    if isMachineMeasurement||isBusCreator||isGeneratorBusOutport||isRootMeasurementConverter
        keep{end+1}=b; %#ok<AGROW>
    end
end
for k=1:numel(keep)
    genSummary(k)=describeBlock(keep{k}); %#ok<AGROW>
end
info=struct();
info.model=model;
info.generator_subsystem=gen;
info.measurements_subsystem=meas;
info.generator_descendant_block_count=numel(allGen);
info.measurements_descendant_block_count=numel(allMeas);
info.generator_measurement_related_blocks=genSummary;
info.measurements_subsystem_blocks=measDetails;
info.measurements_subsystem_is_sink_only=isempty(meas.port_handles(strcmp({meas.port_handles.field},'Outport')));
info.existing_generator_measurement_bus_available=true;
info.generator_measurement_bus_routed_to_aefc_controller=false;
info.interpretation=['This audit records the existing Generators-to-Measurements bus, its selected elements, ' ...
    'the generator measurement blocks, Bus Creators and root-level PS-Simulink converters. The bus is routed ' ...
    'to a Measurements sink and is not automatically connected to AEFCNativeController. These are model ' ...
    'measurement signals, not independently authenticated field sensors.'];
fp=fullfile(outDir,'native_ieee39_generator_measurement_bus_audit_v1.json');
fid=fopen(fp,'w');assert(fid>0,'AEFC:GenBusIO','Cannot write generator bus audit');
fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Generator measurement inventory: %d generator blocks, %d measurement sink blocks, %d selected blocks.\n', ...
    numel(allGen),numel(allMeas),numel(genSummary));
try,close_system(model,0);catch,end
end

function d=describeBlock(block)
d=struct('path',block,'name',char(get_param(block,'Name')), ...
    'block_type',safeText(safeParam(block,'BlockType')),'mask_type',safeText(safeParam(block,'MaskType')), ...
    'reference_block',safeText(safeParam(block,'ReferenceBlock')),'port_handles',{describePorts(block)}, ...
    'port_connectivity',struct([]),'descendant_block_count',0,'dialog_parameters',struct([]),'error','');
try
    pc=get_param(block,'PortConnectivity');
    rec=struct('index',{},'type',{},'src_blocks',{},'src_ports',{},'dst_blocks',{},'dst_ports',{});
    for i=1:numel(pc)
        rec(end+1)=struct('index',i,'type',safeText(pc(i).Type), ...
            'src_blocks',{blockNames(pc(i).SrcBlock)},'src_ports',safeNumeric(pc(i).SrcPort), ...
            'dst_blocks',{blockNames(pc(i).DstBlock)},'dst_ports',safeNumeric(pc(i).DstPort)); %#ok<AGROW>
    end
    d.port_connectivity=rec;
catch ME
    d.error=ME.message;
end
try
    q=get_param(block,'DialogParameters');fn=fieldnames(q);
    rows=struct('name',{},'prompt',{},'type',{},'value',{});
    for i=1:numel(fn)
        nm=fn{i};z=q.(nm);v='';pr='';ty='';
        try,v=safeText(get_param(block,nm));catch,try,v=safeText(z.Value);catch,end,end
        try,pr=safeText(z.Prompt);catch,end
        try,ty=safeText(z.Type);catch,end
        rows(end+1)=struct('name',nm,'prompt',pr,'type',ty,'value',v); %#ok<AGROW>
    end
    d.dialog_parameters=rows;
catch ME
    d.error=[d.error ' | DialogParameters: ' ME.message];
end
try
    kids=find_system(block,'LookUnderMasks','all','FollowLinks','on','Type','Block');
    d.descendant_block_count=max(0,numel(kids)-1);
catch
end
end

function out=describePorts(block)
out=struct('field',{},'port_number',{},'port_type',{},'line_type',{},'line_src_blocks',{},'line_dst_blocks',{});
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
            out(end+1)=struct('field',fields{i},'port_number',safeParam(h,'PortNumber'), ...
                'port_type',safeText(safeParam(h,'PortType')),'line_type',lt, ...
                'line_src_blocks',{src},'line_dst_blocks',{dst}); %#ok<AGROW>
        end
    end
catch
end
end

function x=safeParam(h,n)
try,x=get_param(h,n);catch,x='';end
end
function x=safeText(v)
if ischar(v),x=v;elseif isstring(v),x=char(v);elseif isnumeric(v),x=mat2str(v);elseif iscell(v)
    try,x=strjoin(cellfun(@safeText,v,'UniformOutput',false),';');catch,x='';end
else
    try,x=char(v);catch,x='';end
end
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
