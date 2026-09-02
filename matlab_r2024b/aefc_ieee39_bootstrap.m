function aefc_ieee39_bootstrap
% Bootstrap the native MathWorks IEEE39BusSystem on a headless CI runner.
% GitHub-hosted MATLAB supports running the installed product, but openExample
% is unavailable in this configuration. Therefore this bootstrap resolves the
% installed .slx directly and never substitutes a third-party IEEE39 model.

assert(~verLessThan('matlab','24.2'), ...
    'AEFC:ReleaseTooOld', 'R2024b or later is required for IEEE39BusSystem.');

repo = pwd;
outDir = fullfile(repo,'Figures','IEEE39-R2024b');
resDir = fullfile(repo,'results','ieee39_r2024b');
if ~exist(outDir,'dir'), mkdir(outDir); end
if ~exist(resDir,'dir'), mkdir(resDir); end

modelName = 'IEEE39BusSystem';
resolvedModel = '';
resolutionMethod = '';

% 1) Already on path.
hit = which([modelName '.slx']);
if ~isempty(hit)
    resolvedModel = hit;
    resolutionMethod = 'which';
end

% 2) Shell-side asset inventory produced by the workflow.
assetFile = fullfile(resDir,'install_asset_search.txt');
if isempty(resolvedModel) && exist(assetFile,'file')==2
    lines = splitlines(string(fileread(assetFile)));
    for i=1:numel(lines)
        p = strtrim(lines(i));
        if strlength(p)==0, continue; end
        [~,n,e] = fileparts(char(p));
        if strcmpi(n,modelName) && strcmpi(e,'.slx') && exist(char(p),'file')==2
            resolvedModel = char(p);
            resolutionMethod = 'workflow-file-search';
            break;
        end
    end
end

% 3) Direct recursive search under matlabroot. This is slower but makes the
% bootstrap robust to product-layout changes between runner images.
if isempty(resolvedModel)
    matches = dir(fullfile(matlabroot,'**',[modelName '.slx']));
    if ~isempty(matches)
        resolvedModel = fullfile(matches(1).folder,matches(1).name);
        resolutionMethod = 'matlabroot-recursive-search';
    end
end

resolution = struct;
resolution.model = modelName;
resolution.matlab_release = version('-release');
resolution.matlabroot = matlabroot;
resolution.resolved_model = resolvedModel;
resolution.resolution_method = resolutionMethod;
resolution.openExample_used = false;
writejson(fullfile(resDir,'model_resolution.json'),resolution);

assert(~isempty(resolvedModel),'AEFC:ModelNotFound', ...
    ['IEEE39BusSystem.slx was not found in the installed R2024b product tree. ' ...
     'Inspect results/ieee39_r2024b/install_asset_search.txt and model_resolution.json.']);

load_system(resolvedModel);
assert(bdIsLoaded(modelName),'AEFC:ModelNotLoaded','IEEE39BusSystem is not loaded.');

try, set_param(modelName,'SignalLogging','on'); catch, end
try, set_param(modelName,'SaveOutput','on'); catch, end
try, set_param(modelName,'SaveTime','on'); catch, end

copyPath = fullfile(outDir,'IEEE39BusSystem_AEFC.slx');
save_system(modelName, copyPath);

blocks = find_system(modelName,'LookUnderMasks','all','FollowLinks','on','Type','Block');
records = repmat(struct('path','','name','','block_type','','mask_type','','reference_block',''),numel(blocks),1);
for i = 1:numel(blocks)
    b = blocks{i};
    records(i).path = b;
    records(i).name = get_param(b,'Name');
    records(i).block_type = safeget(b,'BlockType');
    records(i).mask_type = safeget(b,'MaskType');
    records(i).reference_block = safeget(b,'ReferenceBlock');
end

patterns = {'Generators','Measurements','AVR','Exciter','Governor','PSS','Speed','Rotor','Voltage','Vref','Pref','Load','Fault','Bus'};
interesting = false(numel(records),1);
for i = 1:numel(records)
    txt = lower([records(i).path ' ' records(i).name ' ' records(i).mask_type ' ' records(i).reference_block]);
    for j = 1:numel(patterns)
        if contains(txt,lower(patterns{j}))
            interesting(i) = true;
            break;
        end
    end
end

inv = struct;
inv.evidence_source = 'real_mathworks_ieee39_simscape';
inv.migration_target = 'R2024b';
inv.matlab_release = version('-release');
inv.matlab_version = version;
inv.model = modelName;
inv.resolved_model = resolvedModel;
inv.resolution_method = resolutionMethod;
inv.saved_model = strrep(copyPath,[repo filesep],'');
inv.legacy_archive = 'Figures/IEEE-39-bus-power.zip';
inv.legacy_git_blob_sha = '41db586d592851c4a81205a4cc5c7c770b7a0c48';
inv.total_blocks = numel(blocks);
inv.interesting_blocks = records(interesting);
writejson(fullfile(resDir,'bootstrap_inventory.json'),inv);

smoke = struct;
smoke.evidence_source = inv.evidence_source;
smoke.matlab_release = inv.matlab_release;
smoke.model = modelName;
smoke.stop_time_s = 0.20;
smoke.success = false;
smoke.error_identifier = '';
smoke.error_message = '';
smoke.output_fields = {};
smoke.final_time = NaN;

try
    simIn = Simulink.SimulationInput(modelName);
    simIn = simIn.setModelParameter('StopTime',num2str(smoke.stop_time_s));
    out = sim(simIn);
    smoke.output_fields = fieldnames(out);
    try
        t = out.tout;
        if ~isempty(t), smoke.final_time = t(end); end
    catch
    end
    smoke.success = true;
catch ME
    smoke.error_identifier = ME.identifier;
    smoke.error_message = ME.message;
    writejson(fullfile(resDir,'smoke_summary.json'),smoke);
    rethrow(ME);
end

writejson(fullfile(resDir,'smoke_summary.json'),smoke);
save_system(modelName, copyPath);
close_system(modelName,0);
end

function v = safeget(block,param)
try
    v = get_param(block,param);
    if isstring(v), v = char(v); end
catch
    v = '';
end
end

function writejson(path,obj)
fid = fopen(path,'w');
assert(fid>0,'AEFC:IO','Cannot open %s for writing.',path);
c = onCleanup(@() fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(obj,'PrettyPrint',true),'char');
fwrite(fid,sprintf('\n'),'char');
end
