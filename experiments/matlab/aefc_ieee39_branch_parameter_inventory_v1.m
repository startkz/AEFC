function aefc_ieee39_branch_parameter_inventory_v1
% Extract native line/transformer block parameters for comparison with
% MATPOWER case39 reference R/X, tap, baseMVA and RATE_A data.
repo=pwd;resDir=fullfile(repo,'results','ieee39_r2024b');
outDir=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(outDir,'dir'),mkdir(outDir);end
aefc_ieee39_build_stress;
model='IEEE39BusSystem_AEFCStress';
load_system(fullfile(resDir,[model '.slx']));
blocks=find_system(model,'LookUnderMasks','all','FollowLinks','on','Type','Block');
lineBlocks={};transformerBlocks={};
for k=1:numel(blocks)
 b=blocks{k};if ~startsWith(b,[model '/Grid/']),continue;end
 [~,nm]=fileparts(b);
 if ~isempty(regexp(nm,'^B[0-9]+ to B[0-9]+$','once'))
  lineBlocks{end+1}=b; %#ok<AGROW>
 elseif ~isempty(regexp(nm,'^TF[ _]B[0-9]+[ _]to[ _]B[0-9]+$','once'))
  transformerBlocks{end+1}=b; %#ok<AGROW>
 end
end
lineBlocks=unique(lineBlocks,'stable');transformerBlocks=unique(transformerBlocks,'stable');
lineDetails=cell(size(lineBlocks));tfDetails=cell(size(transformerBlocks));
for k=1:numel(lineBlocks),lineDetails{k}=extractParams(lineBlocks{k});end
for k=1:numel(transformerBlocks),tfDetails{k}=extractParams(transformerBlocks{k});end
info=struct();
info.model=model;info.backend='MATLAB R2024b native Simulink/Simscape';
info.line_component_count=numel(lineBlocks);info.transformer_component_count=numel(transformerBlocks);
info.line_components=lineDetails;info.transformer_components=tfDetails;
info.model_nominal_frequency_hz=NaN;
info.model_base_mva=NaN;
info.model_base_voltage_kv=NaN;
info.parameter_equivalence_verified=false;
info.thermal_limit_verified=false;
info.interpretation=['Raw native block parameters are exported without assuming that the MathWorks model ' ...
 'uses MATPOWER parameter conventions. Per-unit conversion requires verified system baseMVA, bus voltage ' ...
 'bases, frequency, line length and transformer winding voltage bases. RATE_A is not promoted to a thermal ' ...
 'limit until those quantities are reconciled.'];
fp=fullfile(outDir,'native_ieee39_branch_parameter_inventory_v1.json');
fid=fopen(fp,'w');assert(fid>0,'AEFC:BranchParamIO','Cannot write parameter inventory');
fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Native branch parameter inventory: %d lines, %d transformers.\n',numel(lineBlocks),numel(transformerBlocks));
try,close_system(model,0);catch,end
end

function d=extractParams(block)
d=struct('path',block,'name',char(get_param(block,'Name')), ...
 'block_type',safeText(safeParam(block,'BlockType')), ...
 'mask_type',safeText(safeParam(block,'MaskType')), ...
 'reference_block',safeText(safeParam(block,'ReferenceBlock')), ...
 'link_status',safeText(safeParam(block,'LinkStatus')), ...
 'mask_names',{{}},'mask_prompts',{{}},'mask_values',{{}}, ...
 'dialog_parameters',struct([]),'error','');
try
 d.mask_names=get_param(block,'MaskNames');
 d.mask_prompts=get_param(block,'MaskPrompts');
 d.mask_values=get_param(block,'MaskValues');
catch ME,d.error=[d.error ' Mask: ' ME.message];end
try
 p=get_param(block,'DialogParameters');names=fieldnames(p);
 rows=struct('name',{},'prompt',{},'type',{},'value',{},'enum',{});
 for i=1:numel(names)
  nm=names{i};q=p.(nm);val='';
  try,val=safeText(get_param(block,nm));catch
   try,val=safeText(q.Value);catch,end
  end
  prompt='';ptype='';enums={};
  try,prompt=safeText(q.Prompt);catch,end
  try,ptype=safeText(q.Type);catch,end
  try,enums=q.Enum;catch,end
  rows(end+1)=struct('name',nm,'prompt',prompt,'type',ptype,'value',val,'enum',{enums}); %#ok<AGROW>
 end
 d.dialog_parameters=rows;
catch ME,d.error=[d.error ' DialogParameters: ' ME.message];end
try
 d.port_handles=portSummary(block);
catch
 d.port_handles=struct([]);
end
end
function out=portSummary(block)
out=struct('field',{},'port_number',{},'port_type',{});
ph=get_param(block,'PortHandles');fields=fieldnames(ph);
for i=1:numel(fields)
 hs=ph.(fields{i});
 for j=1:numel(hs)
  out(end+1)=struct('field',fields{i},'port_number',safeText(safeParam(hs(j),'PortNumber')), ...
   'port_type',safeText(safeParam(hs(j),'PortType'))); %#ok<AGROW>
 end
end
end
function x=safeParam(h,n)
try,x=get_param(h,n);catch,x='';end
end
function x=safeText(v)
if ischar(v),x=v;elseif isstring(v),x=char(v);elseif isnumeric(v),x=mat2str(v);elseif iscell(v),try,x=strjoin(cellfun(@safeText,v,'UniformOutput',false),';');catch,x='';end;else,try,x=char(v);catch,x='';end,end
end
