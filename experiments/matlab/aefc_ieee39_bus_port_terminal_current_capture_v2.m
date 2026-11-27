function aefc_ieee39_bus_port_terminal_current_capture_v2
% Capture bus-port currents and actual three-phase terminal-current vectors.
% The earlier inductor_a/b/c internal-current selection is not assumed to
% represent line terminal phases. This run records phase_splitter1/2 currents.
repo=pwd;resDir=fullfile(repo,'results','ieee39_r2024b');
outDir=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(outDir,'dir'),mkdir(outDir);end
aefc_ieee39_build_stress;
model='IEEE39BusSystem_AEFCStress';
modelPath=fullfile(resDir,[model '.slx']);
assert(exist(modelPath,'file')==2,'AEFC:TerminalCaptureModel','Native IEEE39 model missing.');
load_system(modelPath);
try,set_param(model,'FastRestart','off');catch,end
set_param(model,'SimscapeLogType','all','SimscapeLogName','AEFC_TERMINAL_CURRENT_SIMLOG');
in=Simulink.SimulationInput(model);
in=in.setModelParameter('StopTime','0.05','ReturnWorkspaceOutputs','on');
out=sim(in);
logNode=[];
try,logNode=out.get('AEFC_TERMINAL_CURRENT_SIMLOG');catch,end
if ~isa(logNode,'simscape.logging.Node')
    try,logNode=simscape.logging.getSimulationLog(model);catch,end
end
assert(isa(logNode,'simscape.logging.Node'),'AEFC:TerminalCaptureLog','Missing native Simscape logging Node.');

busPort=struct('path',{},'bus_section',{},'logical_bus',{},'port_index',{}, ...
    'unit',{},'time_s',{},'values_real',{},'values_imag',{},'is_complex',{});
lineTerminal=struct('path',{},'component',{},'terminal',{},'unit',{}, ...
    'time_s',{},'values_real',{},'values_imag',{},'is_complex',{});
transformerWinding=struct('path',{},'component',{},'winding',{},'unit',{}, ...
    'time_s',{},'values_real',{},'values_imag',{},'is_complex',{});
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
            fullPath=[parent '/' key];isC=~isreal(vv);
            vr=real(vv);vi=imag(vv);
            tok=regexp(parent,'/Grid/Bus([^/]+)/I([0-9]+)$','tokens','once');
            if ~isempty(tok)&&strcmp(unit,'A')
                parts=strsplit(tok{1},'_');logicalBus=parts{1};
                busPort(end+1)=struct('path',fullPath,'bus_section',tok{1}, ...
                    'logical_bus',logicalBus,'port_index',str2double(tok{2}), ...
                    'unit',unit,'time_s',tt(:)','values_real',vr, ...
                    'values_imag',vi,'is_complex',isC); %#ok<AGROW>
                continue
            end
            tok=regexp(parent,'/Grid/([^/]+)/phase_splitter([12])/I/instantaneous$', ...
                'tokens','once');
            if ~isempty(tok)&&strcmp(unit,'A')
                lineTerminal(end+1)=struct('path',fullPath,'component',tok{1}, ...
                    'terminal',str2double(tok{2}),'unit',unit,'time_s',tt(:)', ...
                    'values_real',vr,'values_imag',vi,'is_complex',isC); %#ok<AGROW>
                continue
            end
            tok=regexp(parent,'/Grid/(TF_B[0-9]+_to_B[0-9]+)/(i1|i2)$','tokens','once');
            if ~isempty(tok)&&strcmp(unit,'A')
                transformerWinding(end+1)=struct('path',fullPath,'component',tok{1}, ...
                    'winding',tok{2},'unit',unit,'time_s',tt(:)', ...
                    'values_real',vr,'values_imag',vi,'is_complex',isC); %#ok<AGROW>
            end
        end
    end
end
lineComponents=unique({lineTerminal.component});
transformerComponents=unique({transformerWinding.component});
busSections=unique({busPort.bus_section});
logicalBuses=unique({busPort.logical_bus});
assert(numel(busPort)==123,'AEFC:BusPortCount','Expected 123 bus-port currents, found %d',numel(busPort));
assert(numel(lineTerminal)==68,'AEFC:LineTerminalCount','Expected 68 line terminal vectors, found %d',numel(lineTerminal));
assert(numel(lineComponents)==34,'AEFC:LineComponentCount','Expected 34 line components, found %d',numel(lineComponents));
assert(numel(transformerWinding)==24,'AEFC:TransformerWindingCount','Expected 24 transformer winding vectors, found %d',numel(transformerWinding));
assert(numel(transformerComponents)==12,'AEFC:TransformerComponentCount','Expected 12 transformers, found %d',numel(transformerComponents));
assert(numel(busSections)==41&&numel(logicalBuses)==39,'AEFC:BusSectionCount','Expected 41 sections and 39 logical buses.');
info=struct();
info.model=model;info.release='MATLAB R2024b';info.capture_stop_time_s=0.05;
info.simscape_nodes_visited=visited;
info.bus_port_current_count=numel(busPort);info.bus_port_current_series=busPort;
info.line_terminal_current_count=numel(lineTerminal);info.line_terminal_current_series=lineTerminal;
info.line_component_count=numel(lineComponents);info.line_component_names={lineComponents};
info.transformer_winding_current_count=numel(transformerWinding);info.transformer_winding_current_series=transformerWinding;
info.transformer_component_count=numel(transformerComponents);info.transformer_component_names={transformerComponents};
info.physical_bus_sections=numel(busSections);info.logical_bus_count=numel(logicalBuses);
info.full_network_safety_certified=false;info.online_sensor_integrity_verified=false;
info.interpretation=['This capture records native Bus/I# currents, both three-phase line terminal current vectors ' ...
    '(phase_splitter1/2), and transformer winding currents. It is for offline port-index matching only; ' ...
    'it does not certify sensor integrity, branch thermal ratings, DAE observability, or network safety.'];
fp=fullfile(outDir,'native_ieee39_bus_port_terminal_current_capture_v2.json');
fid=fopen(fp,'w');assert(fid>0);fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Terminal current capture: %d bus-port series, %d line terminal vectors, %d transformer winding vectors.\n', ...
    numel(busPort),numel(lineTerminal),numel(transformerWinding));
try,set_param(model,'FastRestart','off');catch,end
try,close_system(model,0);catch,end
end
