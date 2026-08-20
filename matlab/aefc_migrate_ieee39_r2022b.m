function report = aefc_migrate_ieee39_r2022b(archivePath, outDir)
%AEFC_MIGRATE_IEEE39_R2022B Migrate the public EPFL IEEE-39 model to a
% GitHub-hosted MATLAB R2022b offline-simulation target.
%
% This migration is intentionally conservative. It preserves the physical
% Specialized Power Systems network and only neutralizes blocks that are
% identifiable as ARTEMiS/RT-LAB/OPAL-RT runtime-interface blocks. Every
% change is recorded. A migrated model is considered usable only if
% update-diagram succeeds and a short non-real-time simulation completes.

arguments
    archivePath (1,:) char
    outDir (1,:) char
end

if ~isfile(archivePath)
    error('AEFC:MissingArchive','Archive not found: %s', archivePath);
end

if exist(outDir,'dir')
    rmdir(outDir,'s');
end
mkdir(outDir);
sourceDir = fullfile(outDir,'source');
migratedDir = fullfile(outDir,'migrated');
reportDir = fullfile(outDir,'report');
mkdir(sourceDir); mkdir(migratedDir); mkdir(reportDir);
unzip(archivePath, sourceDir);
addpath(genpath(sourceDir));

report = struct();
report.matlabVersion = version;
report.release = version('-release');
report.archive = archivePath;
report.outDir = outDir;
report.startedUtc = char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX'));
report.products = ver;
report.models = struct('source',{},'name',{},'blockCount',{},'loadOk',{}, ...
    'compileBeforeOk',{},'compileBeforeError',{},'candidateScore',{}, ...
    'migrated',{},'replacements',{},'compileAfterOk',{}, ...
    'compileAfterError',{},'smokeOk',{},'smokeError',{}, ...
    'stopTime',{},'simWallSeconds',{});
report.initScripts = find_files(sourceDir,'.m');
report.cFiles = find_files(sourceDir,'.c');
report.modelFiles = [find_files(sourceDir,'.mdl'), find_files(sourceDir,'.slx')];
report.modelFiles = unique(report.modelFiles,'stable');

if isempty(report.modelFiles)
    write_report(report,reportDir);
    error('AEFC:NoModel','No .mdl or .slx model found after extraction.');
end

selectedInit = select_init_scripts(report.initScripts);
report.selectedInitScripts = selectedInit;
report.initScriptErrors = {};
for k=1:numel(selectedInit)
    try
        run(selectedInit{k});
    catch ME
        report.initScriptErrors{end+1,1} = selectedInit{k}; %#ok<AGROW>
        report.initScriptErrors{end,2} = ME.message;
    end
end

for i=1:numel(report.modelFiles)
    src = report.modelFiles{i};
    [~,name,~] = fileparts(src);
    rec = empty_model_record(src,name);
    try
        load_system(src);
        rec.loadOk = true;
        blocks = find_system(name,'LookUnderMasks','all','FollowLinks','on','Type','Block');
        rec.blockCount = numel(blocks);
        rec.candidateScore = score_main_model(name, blocks);
        write_block_inventory(name, blocks, fullfile(reportDir, sprintf('%02d_%s_blocks.tsv',i,safe_name(name))));
        try
            set_param(name,'SimulationCommand','update');
            rec.compileBeforeOk = true;
        catch MEc
            rec.compileBeforeError = flatten_error(MEc);
        end
        close_system(name,0);
    catch MEl
        rec.loadOk = false;
        rec.compileBeforeError = flatten_error(MEl);
        try, close_system(name,0); catch, end
    end
    report.models(end+1) = rec; %#ok<AGROW>
end

scores = zeros(1,numel(report.models));
for i=1:numel(report.models)
    scores(i) = report.models(i).candidateScore + 1e-4*report.models(i).blockCount;
end
[~,ord] = sort(scores,'descend');
report.ranking = ord;
report.mainCandidateIndex = ord(1);
report.mainCandidateSource = report.models(ord(1)).source;

for oi=1:numel(ord)
    i = ord(oi);
    if ~report.models(i).loadOk, continue; end
    src = report.models(i).source;
    [~,name,~] = fileparts(src);
    outFile = fullfile(migratedDir,[safe_name(name) '_R2022b.slx']);
    replacements = struct('path',{},'reason',{},'inports',{},'outports',{},'strategy',{});
    try
        load_system(src);
        save_system(name,outFile);
        close_system(name,0);
        [~,newName,~] = fileparts(outFile);
        load_system(outFile);

        [replacements, migrationWarnings] = neutralize_runtime_blocks(newName);
        report.models(i).migrationWarnings = migrationWarnings;
        configure_offline_solver(newName);
        save_system(newName,outFile);
        report.models(i).migrated = outFile;
        report.models(i).replacements = replacements;

        try
            set_param(newName,'SimulationCommand','update');
            report.models(i).compileAfterOk = true;
        catch MEc
            report.models(i).compileAfterError = flatten_error(MEc);
        end

        if report.models(i).compileAfterOk
            try
                stopTime = choose_smoke_stop_time(newName);
                t = tic;
                simOut = sim(newName,'StopTime',num2str(stopTime,17), ...
                    'ReturnWorkspaceOutputs','on'); %#ok<NASGU>
                report.models(i).simWallSeconds = toc(t);
                report.models(i).stopTime = stopTime;
                report.models(i).smokeOk = true;
            catch MEs
                report.models(i).smokeError = flatten_error(MEs);
            end
        end
        close_system(newName,0);
    catch MEm
        report.models(i).compileAfterError = flatten_error(MEm);
        try, close_system(name,0); catch, end
        try
            [~,newName,~] = fileparts(outFile);
            close_system(newName,0);
        catch
        end
    end
end

report.finishedUtc = char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX'));
report.successfulModelIndices = find([report.models.smokeOk]);
report.realPhysicalSmokePassed = ~isempty(report.successfulModelIndices);
if report.realPhysicalSmokePassed
    best = [];
    for k=1:numel(ord)
        if report.models(ord(k)).smokeOk
            best = ord(k); break;
        end
    end
    report.selectedModelIndex = best;
    report.selectedMigratedModel = report.models(best).migrated;
else
    report.selectedModelIndex = [];
    report.selectedMigratedModel = '';
end

write_report(report,reportDir);
if ~report.realPhysicalSmokePassed
    error('AEFC:R2022bMigrationSmokeFailed', ...
        ['No migrated IEEE39 candidate completed both update-diagram and a short ' ...
         'physical simulation. Inspect build/ieee39_r2022b/report for exact block/library errors.']);
end
end

function rec = empty_model_record(src,name)
rec = struct('source',src,'name',name,'blockCount',0,'loadOk',false, ...
    'compileBeforeOk',false,'compileBeforeError','','candidateScore',0, ...
    'migrated','','replacements',struct('path',{},'reason',{},'inports',{},'outports',{},'strategy',{}), ...
    'compileAfterOk',false,'compileAfterError','','smokeOk',false,'smokeError','', ...
    'stopTime',NaN,'simWallSeconds',NaN);
end

function out = find_files(rootDir, ext)
d = dir(fullfile(rootDir,'**',['*' ext]));
out = cell(1,numel(d));
for i=1:numel(d), out{i}=fullfile(d(i).folder,d(i).name); end
end

function selected = select_init_scripts(files)
selected = {};
for i=1:numel(files)
    [~,n,~]=fileparts(files{i});
    s=lower(n);
    if contains(s,'init') || contains(s,'param') || contains(s,'data') || contains(s,'load')
        selected{end+1}=files{i}; %#ok<AGROW>
    end
end
end

function score = score_main_model(modelName, blocks)
score = 0;
s = lower(modelName);
if contains(s,'39'), score=score+15; end
if contains(s,'ieee'), score=score+10; end
if contains(s,'network') || contains(s,'grid') || contains(s,'system'), score=score+5; end
for j=1:numel(blocks)
    b=blocks{j};
    bt=safe_get(b,'BlockType'); mt=safe_get(b,'MaskType'); rb=safe_get(b,'ReferenceBlock');
    t=lower([b ' ' bt ' ' mt ' ' rb]);
    if contains(t,'synchronous machine'), score=score+2; end
    if contains(t,'generator'), score=score+0.5; end
    if contains(t,'powergui'), score=score+8; end
    if contains(t,'transmission line'), score=score+0.25; end
    if contains(t,'three-phase'), score=score+0.1; end
end
end

function write_block_inventory(model, blocks, file)
fid=fopen(file,'w');
cleanup=onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid,'path\tblock_type\tmask_type\treference_block\tlink_status\truntime_class\n');
for j=1:numel(blocks)
    b=blocks{j};
    fprintf(fid,'%s\t%s\t%s\t%s\t%s\t%s\n',esc(b),esc(safe_get(b,'BlockType')), ...
        esc(safe_get(b,'MaskType')),esc(safe_get(b,'ReferenceBlock')), ...
        esc(safe_get(b,'LinkStatus')),esc(runtime_class(b)));
end
end

function [repl,warnings] = neutralize_runtime_blocks(model)
blocks=find_system(model,'LookUnderMasks','all','FollowLinks','on','Type','Block');
[~,idx]=sort(cellfun(@(x) numel(strfind(x,'/')),blocks),'descend');
blocks=blocks(idx);
repl=struct('path',{},'reason',{},'inports',{},'outports',{},'strategy',{});
warnings={};
for j=1:numel(blocks)
    b=blocks{j};
    if ~ishandle_block(b), continue; end
    cls=runtime_class(b);
    if isempty(cls), continue; end
    if is_physical_power_block(b), continue; end
    try
        ph=get_param(b,'PortHandles');
        nin=numel(ph.Inport); nout=numel(ph.Outport);
        old=b; strategy=replace_block_with_adapter(b,nin,nout);
        r=struct('path',old,'reason',cls,'inports',nin,'outports',nout,'strategy',strategy);
        repl(end+1)=r; %#ok<AGROW>
    catch ME
        warnings{end+1,1}=b; %#ok<AGROW>
        warnings{end,2}=flatten_error(ME);
    end
end
end

function tf = is_physical_power_block(b)
rb=lower(safe_get(b,'ReferenceBlock')); mt=lower(safe_get(b,'MaskType'));
keep={'synchronous','machine','transmission','transformer','three-phase','load', ...
      'breaker','voltage measurement','current measurement','powergui','source'};
tf=false;
for i=1:numel(keep)
    if contains(rb,keep{i}) || contains(mt,keep{i}), tf=true; return; end
end
end

function cls = runtime_class(b)
t=lower([b ' ' safe_get(b,'MaskType') ' ' safe_get(b,'ReferenceBlock') ' ' safe_get(b,'BlockType')]);
cls='';
patterns = { ...
    'artemis','ARTEMIS runtime/solver'; ...
    'rt-lab','RT-LAB runtime'; ...
    'rtlab','RT-LAB runtime'; ...
    'opal-rt','OPAL-RT runtime'; ...
    'opcomm','OPAL-RT communication'; ...
    'opwrite','OPAL-RT logging'; ...
    'opmonitor','OPAL-RT monitor'; ...
    'optrigger','OPAL-RT trigger'; ...
    'oprecorder','OPAL-RT recorder'; ...
    'opwait','OPAL-RT synchronization'; ...
    'opfrom','OPAL-RT communication'; ...
    'opgoto','OPAL-RT communication'};
for i=1:size(patterns,1)
    if contains(t,patterns{i,1}), cls=patterns{i,2}; return; end
end
end

function strategy = replace_block_with_adapter(block,nin,nout)
parent=get_param(block,'Parent');
name=get_param(block,'Name');
pos=get_param(block,'Position');
ph=get_param(block,'PortHandles');
inSrc=cell(1,nin); outDst=cell(1,nout);
for i=1:nin
    inSrc{i}=[]; ln=get_param(ph.Inport(i),'Line');
    if ln~=-1, inSrc{i}=get_param(ln,'SrcPortHandle'); end
end
for i=1:nout
    outDst{i}=[]; ln=get_param(ph.Outport(i),'Line');
    if ln~=-1, outDst{i}=get_param(ln,'DstPortHandle'); end
end
for i=1:nin
    ln=get_param(ph.Inport(i),'Line'); if ln~=-1, try delete_line(ln); catch, end; end
end
for i=1:nout
    ln=get_param(ph.Outport(i),'Line'); if ln~=-1, try delete_line(ln); catch, end; end
end
delete_block(block);
newPath=[parent '/' name];
add_block('simulink/Ports & Subsystems/Subsystem',newPath,'Position',pos);
try delete_line(newPath,'In1/1','Out1/1'); catch, end
try delete_block([newPath '/In1']); catch, end
try delete_block([newPath '/Out1']); catch, end
for i=1:nin
    add_block('simulink/Ports & Subsystems/In1',[newPath sprintf('/In%d',i)],'Port',num2str(i));
end
for i=1:nout
    add_block('simulink/Ports & Subsystems/Out1',[newPath sprintf('/Out%d',i)],'Port',num2str(i));
    if i<=nin
        add_line(newPath,sprintf('In%d/1',i),sprintf('Out%d/1',i),'autorouting','on');
    else
        c=[newPath sprintf('/Zero%d',i)];
        add_block('simulink/Sources/Constant',c,'Value','0');
        add_line(newPath,sprintf('Zero%d/1',i),sprintf('Out%d/1',i),'autorouting','on');
    end
end
for i=nout+1:nin
    tr=[newPath sprintf('/Term%d',i)];
    add_block('simulink/Sinks/Terminator',tr);
    add_line(newPath,sprintf('In%d/1',i),sprintf('Term%d/1',i),'autorouting','on');
end
newPh=get_param(newPath,'PortHandles');
for i=1:min(nin,numel(newPh.Inport))
    if ~isempty(inSrc{i}) && ishandle(inSrc{i})
        try add_line(parent,inSrc{i},newPh.Inport(i),'autorouting','on'); catch, end
    end
end
for i=1:min(nout,numel(newPh.Outport))
    dst=outDst{i};
    if isempty(dst), continue; end
    if ~iscell(dst), dst=num2cell(dst); end
    for k=1:numel(dst)
        if ~isempty(dst{k}) && ishandle(dst{k})
            try add_line(parent,newPh.Outport(i),dst{k},'autorouting','on'); catch, end
        end
    end
end
if nin==nout && nin>0, strategy='portwise_passthrough';
elseif nout==0, strategy='sink_terminate';
elseif nin==0, strategy='zero_source';
else, strategy='passthrough_plus_zero_or_terminate'; end
end

function configure_offline_solver(model)
try set_param(model,'SimulationMode','normal'); catch, end
try set_param(model,'RapidAcceleratorUpToDateCheck','off'); catch, end
solver=lower(safe_get(model,'Solver'));
if contains(solver,'rtwin') || contains(solver,'rsim') || contains(solver,'rti') || contains(solver,'opal')
    try set_param(model,'SolverType','Fixed-step','Solver','FixedStepDiscrete'); catch, end
end
pg=find_system(model,'LookUnderMasks','all','FollowLinks','on','Regexp','on','Name','(?i)^powergui$');
for i=1:numel(pg)
    try_set(pg{i},'SimulationMode','Discrete');
    try_set(pg{i},'SampleTime','5e-5');
end
end

function stopTime=choose_smoke_stop_time(model)
stopTime=0.05;
try
    st=str2double(get_param(model,'StopTime'));
    if isfinite(st) && st>0, stopTime=min(st,0.05); end
catch
end
if stopTime<=0, stopTime=0.01; end
end

function try_set(block,param,value)
try
    op=get_param(block,'ObjectParameters');
    if isfield(op,param), set_param(block,param,value); end
catch
end
end

function tf=ishandle_block(path)
try, get_param(path,'Handle'); tf=true; catch, tf=false; end
end

function v=safe_get(obj,param)
try
    v=get_param(obj,param);
    if isnumeric(v), v=num2str(v); end
catch
    v='';
end
end

function s=safe_name(s)
s=regexprep(s,'[^A-Za-z0-9_\-]','_');
end

function s=esc(s)
if isnumeric(s), s=num2str(s); end
s=strrep(char(s),sprintf('\t'),' ');
s=strrep(s,sprintf('\n'),' ');
s=strrep(s,sprintf('\r'),' ');
end

function s=flatten_error(ME)
s=ME.message;
try
    for k=1:numel(ME.stack)
        s=sprintf('%s | %s:%d',s,ME.stack(k).name,ME.stack(k).line); %#ok<AGROW>
    end
catch
end
s=esc(s);
end

function write_report(report,reportDir)
save(fullfile(reportDir,'migration_report.mat'),'report');
fid=fopen(fullfile(reportDir,'migration_report.json'),'w');
fwrite(fid,jsonencode(report,'PrettyPrint',true),'char'); fclose(fid);
fid=fopen(fullfile(reportDir,'model_summary.tsv'),'w');
fprintf(fid,'index\tname\tblocks\tload_ok\tcompile_before\tscore\tmigrated\treplacements\tcompile_after\tsmoke_ok\tcompile_error\tsmoke_error\n');
for i=1:numel(report.models)
    r=report.models(i);
    fprintf(fid,'%d\t%s\t%d\t%d\t%d\t%.6f\t%s\t%d\t%d\t%d\t%s\t%s\n', ...
        i,esc(r.name),r.blockCount,r.loadOk,r.compileBeforeOk,r.candidateScore, ...
        esc(r.migrated),numel(r.replacements),r.compileAfterOk,r.smokeOk, ...
        esc(r.compileAfterError),esc(r.smokeError));
end
fclose(fid);
end
