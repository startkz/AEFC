function aefc_ieee39_dynamic_probe
% Phase-A dynamic instrumentation qualification on the official MathWorks
% IEEE39BusSystem model. This is NOT an AEFC-FRL learner comparison.
assert(~verLessThan('matlab','24.2'),'AEFC:ReleaseTooOld','MATLAB R2024b or later is required.');

repo=pwd;
resDir=fullfile(repo,'results','ieee39_r2024b');
outDir=fullfile(resDir,'dynamic_probe');
if ~exist(outDir,'dir'), mkdir(outDir); end

[model,~]=aefc_ieee39_load_official;
blocks=find_system(model,'LookUnderMasks','all','FollowLinks','on','Type','Block');

% Inventory the actual dynamic model interfaces before any controller or
% protection modification. The inventory is deliberately descriptive:
% candidates are not treated as validated actuators or executed relays.
records=repmat(emptyRecord(),0,1);
speedBlocks=repmat(struct('path','','generator_key','','generator_index',0, ...
    'workspace_name','','sink_path',''),0,1);
for i=1:numel(blocks)
    b=blocks{i};
    name=safeget(b,'Name');
    mask=safeget(b,'MaskType');
    ref=safeget(b,'ReferenceBlock');
    typ=safeget(b,'BlockType');
    parent=safeget(b,'Parent');
    low=lower([b ' ' name ' ' mask ' ' ref]);
    isGen=contains(b,[model '/Generators/Gen']);
    isLoad=contains(b,[model '/Loads']);
    isGrid=contains(b,[model '/Grid']);
    interesting=isGen && hasAny(low,{'pref','governor','prime mover','governor and', ...
        'speed','rotor','pm','pmech','mechanical','valve','gate','servo','turbine','w'}) ...
        || (isLoad && hasAny(low,{'breaker','switch','load','fault','relay','trip'})) ...
        || (isGrid && hasAny(low,{'breaker','switch','fault','relay','trip'})) ...
        || hasAny(low,{'three-phase fault','breaker','underfrequency','relay'});
    if interesting
        r=emptyRecord();
        r.path=b; r.name=name; r.block_type=typ; r.mask_type=mask;
        r.reference_block=ref; r.parent=parent;
        try
            ph=get_param(b,'PortHandles');
            r.n_inports=numel(ph.Inport); r.n_outports=numel(ph.Outport);
        catch
        end
        try
            mn=get_param(b,'MaskNames'); mv=get_param(b,'MaskValues');
            if ischar(mn), mn={mn}; end
            if ischar(mv), mv={mv}; end
            r.mask_parameters=struct;
            for q=1:min(numel(mn),numel(mv))
                key=matlab.lang.makeValidName(mn{q});
                r.mask_parameters.(key)=mv{q};
            end
        catch
        end
        r.output_connections=outputConnections(b);
        records(end+1,1)=r; %#ok<AGROW>
    end

    % The native model exposes generator rotor speed as a per-unit signal
    % named w inside each generator's governor. Keep one signal per machine.
    if isGen && contains(lower(b),'/governor/') && strcmpi(strtrim(name),'w')
        g=generatorKey(b);
        if ~isempty(g) && ~any(strcmp({speedBlocks.generator_key},g))
            tok=regexp(g,'Gen(\d+)@Bus(\d+)','tokens','once');
            if ~isempty(tok)
                gi=str2double(tok{1});
                s=struct('path',b,'generator_key',g,'generator_index',gi, ...
                    'workspace_name',sprintf('AEFC_DYN_W_GEN%02d',gi), ...
                    'sink_path','');
                speedBlocks(end+1,1)=s; %#ok<AGROW>
            end
        end
    end
end

assert(numel(speedBlocks)==10,'AEFC:DynamicSpeedCount', ...
    'Expected one governor rotor-speed signal for each of 10 generators; discovered %d.',numel(speedBlocks));
[~,ord]=sort([speedBlocks.generator_index]);
speedBlocks=speedBlocks(ord);

% Branch all ten real rotor-speed signals to explicit SimulationOutput traces.
for i=1:numel(speedBlocks)
    src=speedBlocks(i).path;
    parent=get_param(src,'Parent');
    makeEditable(parent);
    ph=get_param(src,'PortHandles');
    assert(~isempty(ph.Outport),'AEFC:DynamicSpeedPort','No output port at %s.',src);
    sink=[parent sprintf('/AEFC_DYN_SPEED_TOWS_GEN%02d',speedBlocks(i).generator_index)];
    if getSimulinkBlockHandle(sink)>0, delete_block(sink); end
    add_block('simulink/Sinks/To Workspace',sink, ...
        'VariableName',speedBlocks(i).workspace_name, ...
        'SaveFormat','Timeseries','Position',sinkPosition(get_param(src,'Position')));
    sph=get_param(sink,'PortHandles');
    add_line(parent,ph.Outport(1),sph.Inport,'autorouting','on');
    speedBlocks(i).sink_path=sink;
end

set_param(model,'ReturnWorkspaceOutputs','on');
set_param(model,'SignalLogging','off');
stopTime=20.0;
simIn=Simulink.SimulationInput(model);
simIn=simIn.setModelParameter('StopTime',num2str(stopTime,'%.17g'), ...
    'ReturnWorkspaceOutputs','on','SignalLogging','off');
simOut=sim(simIn);

series=cell(10,1);
timeRef=[];
freq=cell(10,1);
for i=1:10
    v=simOut.get(speedBlocks(i).workspace_name);
    assert(~isempty(v),'AEFC:DynamicTraceMissing','Missing %s.',speedBlocks(i).workspace_name);
    [tt,ww]=extractSeries(v);
    tt=double(tt(:)); ww=double(squeeze(ww)); ww=ww(:);
    assert(numel(tt)==numel(ww) && numel(tt)>10,'AEFC:DynamicTraceShape','Bad trace shape for %s.',speedBlocks(i).generator_key);
    assert(all(isfinite(tt)) && all(isfinite(ww)),'AEFC:DynamicTraceFinite','Non-finite trace for %s.',speedBlocks(i).generator_key);
    if isempty(timeRef), timeRef=tt; else
        assert(numel(tt)==numel(timeRef) && max(abs(tt-timeRef))<1e-8, ...
            'AEFC:DynamicTimeAlignment','Generator speed traces are not time aligned.');
    end
    series{i}=ww;
    freq{i}=60.0*ww; % w is p.u.; nominal system frequency is 60 Hz.
end

F=cell2mat(cellfun(@(x)x(:),freq,'UniformOutput',false)');
W=cell2mat(cellfun(@(x)x(:),series,'UniformOutput',false)');
t=timeRef;
dF=F-60.0;
rocof=zeros(size(F));
dt=median(diff(t));
win=max(3,round(0.10/max(dt,eps)));
for j=1:10
    raw=gradient(F(:,j),t);
    rocof(:,j)=movmean(raw,win,'Endpoints','shrink');
end

faultOn=5.0; faultClear=5.1;
post=find(t>=faultOn);
assert(~isempty(post),'AEFC:FaultWindowMissing','Simulation did not reach documented fault onset.');
[fMin,idxMinLocal]=min(F(post,:),[],1);
tPost=t(post);
tNadir=zeros(1,10);
for j=1:10, tNadir(j)=tPost(idxMinLocal(j)); end
maxAbsRoCoF=max(abs(rocof(post,:)),[],1);
maxAbsDf=max(abs(dF(post,:)),[],1);
baseIdx=find(t>=max(0,faultOn-1.0) & t<faultOn);
fBase=mean(F(baseIdx,:),1);
settleTime=nan(1,10);
for j=1:10
    for k=find(t>=faultClear)'
        last=min(numel(t),k+max(1,round(1.0/max(dt,eps)))-1);
        if last-k+1>=max(1,round(1.0/max(dt,eps))) && ...
                all(abs(F(k:last,j)-fBase(j))<=0.1)
            settleTime(j)=t(k)-faultClear;
            break;
        end
    end
end

% COI frequency is intentionally not synthesized from an arithmetic mean.
% Actual H_i and machine MVA ratings must be extracted from the synchronous
% machine parameter blocks before this quantity is reported.
writeFrequencyCsv(fullfile(outDir,'frequency_per_generator.csv'),t,F,dF,rocof);
summary=struct;
summary.study='official_mathworks_ieee39_dynamic_instrumentation_probe';
summary.status='phase_A_instrumentation_only_not_AEFC_FRL_evidence';
summary.model='IEEE39BusSystem';
summary.matlab_release=version('-release');
summary.backend='MathWorks Simscape Electrical native dynamic model';
summary.stop_time_s=stopTime;
summary.documented_fault=struct('location','Bus-16','type','three-phase-to-ground', ...
    'start_time_s',faultOn,'clear_time_s',faultClear,'source','MathWorks IEEE 39-Bus System example');
summary.generator_count=10;
summary.frequency_definition='f_i(t)=60*w_i(t), where w_i is the measured per-unit governor rotor-speed signal';
summary.rocof_estimator='gradient(f_i,t), followed by a 0.10-s moving mean';
summary.coi_frequency_available=false;
summary.coi_frequency_reason='Inertia H_i and machine MVA bases have not yet been extracted from the native synchronous-machine blocks.';
summary.generator_metrics=repmat(struct('generator_key','','f_nadir_hz',0, ...
    't_nadir_s',0,'max_abs_delta_f_hz',0,'max_abs_rocof_hz_s',0, ...
    'settling_time_after_fault_clear_s',NaN,'baseline_frequency_hz',0),10,1);
for j=1:10
    summary.generator_metrics(j).generator_key=speedBlocks(j).generator_key;
    summary.generator_metrics(j).f_nadir_hz=fMin(j);
    summary.generator_metrics(j).t_nadir_s=tNadir(j);
    summary.generator_metrics(j).max_abs_delta_f_hz=maxAbsDf(j);
    summary.generator_metrics(j).max_abs_rocof_hz_s=maxAbsRoCoF(j);
    summary.generator_metrics(j).settling_time_after_fault_clear_s=settleTime(j);
    summary.generator_metrics(j).baseline_frequency_hz=fBase(j);
end

summary.discovery=struct;
summary.discovery.rotor_speed_signals=speedBlocks;
summary.discovery.relevant_block_count=numel(records);
summary.discovery.actuator_candidates=filterRecords(records,{'pref','pmech','mechanical','valve','gate','servo','turbine'});
summary.discovery.protection_candidates=filterRecords(records,{'breaker','switch','fault','relay','trip'});
summary.discovery.load_candidates=filterRecords(records,{'/loads/'});
summary.parameter_candidates=machineParameterCandidates(blocks,model);
writejson(fullfile(outDir,'dynamic_probe_summary.json'),summary);
writejson(fullfile(outDir,'dynamic_block_inventory.json'),struct('model',model, ...
    'release',version('-release'),'blocks',records,'machine_parameter_candidates',summary.parameter_candidates));

fig=figure('Visible','off','Color','w','Position',[100 100 1200 760]);
subplot(2,1,1); hold on;
for j=1:10, plot(t,F(:,j),'LineWidth',0.9); end
xline(faultOn,'--k','Fault on'); xline(faultClear,':k','Fault clear');
ylabel('Generator rotor frequency (Hz)'); xlabel('Time (s)');
title('Native IEEE39 dynamic response to the documented Bus-16 fault');
grid on; legend({speedBlocks.generator_key},'Location','eastoutside','FontSize',7);
subplot(2,1,2); hold on;
for j=1:10, plot(t,rocof(:,j),'LineWidth',0.8); end
xline(faultOn,'--k'); xline(faultClear,':k');
ylabel('RoCoF (Hz/s)'); xlabel('Time (s)'); grid on;
exportgraphics(fig,fullfile(outDir,'Fig_Dynamic_Frequency_RoCoF.png'),'Resolution',300);
close(fig);

manifest=struct('source_commit',getenv('GITHUB_SHA'),'matlab_release',version('-release'), ...
    'model','IEEE39BusSystem','stop_time_s',stopTime, ...
    'frequency_csv_sha256',sha256File(fullfile(outDir,'frequency_per_generator.csv')), ...
    'summary_sha256',sha256File(fullfile(outDir,'dynamic_probe_summary.json')));
writejson(fullfile(outDir,'manifest.json'),manifest);
close_system(model,0);
end

function r=emptyRecord()
r=struct('path','','name','','block_type','','mask_type','','reference_block','', ...
    'parent','','n_inports',0,'n_outports',0,'mask_parameters',struct, ...
    'output_connections',{{}});
end

function y=filterRecords(records,terms)
y=records([]);
for i=1:numel(records)
    txt=lower([records(i).path ' ' records(i).name ' ' records(i).block_type ' ' records(i).mask_type ' ' records(i).reference_block]);
    if hasAny(txt,terms), y(end+1)=records(i); end %#ok<AGROW>
end
end

function p=machineParameterCandidates(blocks,model)
p=repmat(struct('path','','name','','mask_type','','mask_parameters',struct),0,1);
for i=1:numel(blocks)
    b=blocks{i};
    if ~contains(b,[model '/Generators/Gen']), continue; end
    txt=lower([b ' ' safeget(b,'Name') ' ' safeget(b,'MaskType') ' ' safeget(b,'ReferenceBlock')]);
    if ~hasAny(txt,{'synchronous machine','machine','inertia','rotor'})
        continue;
    end
    r=struct('path',b,'name',safeget(b,'Name'),'mask_type',safeget(b,'MaskType'),'mask_parameters',struct);
    try
        mn=get_param(b,'MaskNames'); mv=get_param(b,'MaskValues');
        if ischar(mn), mn={mn}; end
        if ischar(mv), mv={mv}; end
        for q=1:min(numel(mn),numel(mv))
            key=matlab.lang.makeValidName(mn{q});
            r.mask_parameters.(key)=mv{q};
        end
    catch
    end
    p(end+1,1)=r; %#ok<AGROW>
end
end

function c=outputConnections(block)
c={};
try
    ph=get_param(block,'PortHandles');
    for k=1:numel(ph.Outport)
        lh=get_param(ph.Outport(k),'Line');
        if isempty(lh) || all(lh==-1), continue; end
        dst=get_param(lh,'DstBlockHandle');
        for j=1:numel(dst)
            if dst(j)<=0, continue; end
            c{end+1}=getfullname(dst(j)); %#ok<AGROW>
        end
    end
catch
end
end

function g=generatorKey(path)
tok=regexp(path,'Generators/(Gen\d+@Bus\d+)','tokens','once');
if isempty(tok), g=''; else, g=tok{1}; end
end

function tf=hasAny(txt,terms)
tf=false;
for k=1:numel(terms)
    if contains(txt,lower(terms{k})), tf=true; return; end
end
end

function pos=sinkPosition(srcPos)
x=srcPos(3)+70; y=srcPos(2)+30;
pos=[x y x+125 y+28];
end

function makeEditable(block)
try
    if strcmp(get_param(block,'LinkStatus'),'resolved'), set_param(block,'LinkStatus','inactive'); end
catch
end
end

function v=safeget(block,param)
try
    v=get_param(block,param);
    if isstring(v), v=char(v); end
catch
    v='';
end
end

function [t,d]=extractSeries(v)
if isa(v,'timeseries')
    t=v.Time; d=v.Data;
elseif isa(v,'Simulink.SimulationData.Signal')
    [t,d]=extractSeries(v.Values);
elseif isa(v,'Simulink.SimulationData.Dataset')
    assert(v.numElements>0,'AEFC:DatasetEmpty','Empty Dataset output.');
    [t,d]=extractSeries(v.getElement(1).Values);
else
    try, t=v.Time; d=v.Data;
    catch, error('AEFC:DynamicOutputFormat','Unsupported output %s.',class(v)); end
end
end

function writeFrequencyCsv(path,t,F,dF,R)
fid=fopen(path,'w'); assert(fid>0,'AEFC:IO','Cannot write %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fprintf(fid,'time_s');
for j=1:size(F,2), fprintf(fid,',f_gen%02d_hz,df_gen%02d_hz,rocof_gen%02d_hz_s',j,j,j); end
fprintf(fid,'\n');
for i=1:numel(t)
    fprintf(fid,'%.10g',t(i));
    for j=1:size(F,2), fprintf(fid,',%.10g,%.10g,%.10g',F(i,j),dF(i,j),R(i,j)); end
    fprintf(fid,'\n');
end
end

function writejson(path,obj)
fid=fopen(path,'w'); assert(fid>0,'AEFC:IO','Cannot write %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(obj,'PrettyPrint',true),'char'); fwrite(fid,sprintf('\n'),'char');
end

function h=sha256File(path)
fid=fopen(path,'r'); assert(fid>0,'AEFC:IO','Cannot hash %s.',path);
c=onCleanup(@()fclose(fid)); %#ok<NASGU>
b=fread(fid,inf,'*uint8');
md=java.security.MessageDigest.getInstance('SHA-256'); md.update(b);
d=typecast(md.digest(),'uint8'); h=lower(reshape(dec2hex(d,2).',1,[]));
end
