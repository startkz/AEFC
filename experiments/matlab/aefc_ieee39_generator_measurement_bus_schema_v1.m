function aefc_ieee39_generator_measurement_bus_schema_v1
% Export the bus-element selections and Bus Creator signal names for the
% existing 10-generator measurement bus.
repo=pwd;resDir=fullfile(repo,'results','ieee39_r2024b');
outDir=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(outDir,'dir'),mkdir(outDir);end
aefc_ieee39_build_stress;
model='IEEE39BusSystem_AEFCStress';load_system(fullfile(resDir,[model '.slx']));
paths={ [model '/Generators/Bus' newline 'Creator1'], ...
        [model '/Measurements'] };
for g=1:10
  genPath=generatorPath(model,g);
  paths{end+1}=[genPath '/Bus' newline 'Creator']; %#ok<AGROW>
  paths{end+1}=[genPath sprintf('/mGen%d',g)]; %#ok<AGROW>
end
measBlocks=find_system([model '/Measurements'],'LookUnderMasks','all','FollowLinks','on','Type','Block');
for k=1:numel(measBlocks)
 b=measBlocks{k};
 if contains(get_param(b,'BlockType'),'Inport') || ...
    contains(get_param(b,'BlockType'),'Mux') || ...
    contains(get_param(b,'BlockType'),'Scope')
    paths{end+1}=b; %#ok<AGROW>
 end
end
paths=unique(paths,'stable');
records=cell(size(paths));
for k=1:numel(paths)
 if getSimulinkBlockHandle(paths{k})>0
  records{k}=describeBlock(paths{k});
 else
  records{k}=struct('path',paths{k},'missing',true);
 end
end
info=struct();info.model=model;info.generator_count=10;
info.generator_measurement_bus_source=[model '/Generators'];
info.generator_measurement_bus_destination=[model '/Measurements'];
info.blocks=records;
info.interpretation=['This exports existing Bus Creator and In Bus Element parameter values. ' ...
 'Bus fields are model-generated signals, not independent physical sensor attestations.'];
fp=fullfile(outDir,'native_ieee39_generator_measurement_bus_schema_v1.json');
fid=fopen(fp,'w');assert(fid>0,'AEFC:GenBusSchemaIO','Cannot write generator bus schema');
fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Generator measurement bus schema exported for %d blocks.\n',numel(paths));
try,close_system(model,0);catch,end
end

function p=generatorPath(model,g)
names={'Gen1@Bus39','Gen2@Bus31','Gen3@Bus32','Gen4@Bus33','Gen5@Bus34', ...
       'Gen6@Bus35','Gen7@Bus36','Gen8@Bus37','Gen9@Bus38','Gen10@Bus30'};
p=[model '/Generators/' names{g}];
end
function d=describeBlock(block)
d=struct('path',block,'name',char(get_param(block,'Name')), ...
 'block_type',safeText(safeParam(block,'BlockType')),'mask_type',safeText(safeParam(block,'MaskType')), ...
 'reference_block',safeText(safeParam(block,'ReferenceBlock')),'dialog_parameters',struct([]), ...
 'mask_names',{{}},'mask_values',{{}},'error','');
try,d.mask_names=get_param(block,'MaskNames');d.mask_values=get_param(block,'MaskValues');catch,end
try
 p=get_param(block,'DialogParameters');names=fieldnames(p);
 rows=struct('name',{},'prompt',{},'type',{},'value',{});
 for i=1:numel(names)
  nm=names{i};v='';pr='';ty='';
  try,v=safeText(get_param(block,nm));catch,try,v=safeText(p.(nm).Value);catch,end,end
  try,pr=safeText(p.(nm).Prompt);catch,end
  try,ty=safeText(p.(nm).Type);catch,end
  rows(end+1)=struct('name',nm,'prompt',pr,'type',ty,'value',v); %#ok<AGROW>
 end
 d.dialog_parameters=rows;
catch ME,d.error=ME.message;end
end
function x=safeParam(h,n)
try,x=get_param(h,n);catch,x='';end
end
function x=safeText(v)
if ischar(v),x=v;elseif isstring(v),x=char(v);elseif isnumeric(v),x=mat2str(v);elseif iscell(v),try,x=strjoin(cellfun(@safeText,v,'UniformOutput',false),';');catch,x='';end;else,try,x=char(v);catch,x='';end,end
end
