function aefc_ieee39_physical_event_interface_inventory_v2
% Query real original IEEE39 Simulink/Simscape block masks, dialog parameters
% and wiring for candidate fault/load/line disturbances. This is discovery,
% not permission to rewire or claim the stressor has been validated.
repo=pwd;res=fullfile(repo,'results','ieee39_stress_r1');
if ~exist(res,'dir'),mkdir(res);end
report=struct('status','NOT_STARTED','model','IEEE39BusSystem', ...
 'blocks_scanned',0,'fault_blocks',0,'load_named_blocks',0, ...
 'load_mask_blocks',0,'line_blocks',0,'transformer_blocks',0, ...
 'actual_exogenous_fault_source_validated',false, ...
 'fault_insertion_and_clearance_verified',false, ...
 'full_network_safety_certified',false, ...
 'entries',struct([]),'unique_grid_simscape_mask_types',{{}});
try
 [model,~]=aefc_ieee39_load_official;
 blocks=find_system(model,'FollowLinks','on','LookUnderMasks','all','Type','Block');
 report.blocks_scanned=numel(blocks);
 entries=struct('path',{},'name',{},'block_type',{},'mask_type',{}, ...
  'reference_block',{},'link_status',{},'category',{}, ...
  'mask_names',{},'mask_prompts',{},'mask_values',{}, ...
  'dialog_parameter_names',{},'dialog_parameter_values',{}, ...
  'inport_count',{},'outport_count',{},'physical_left_count',{}, ...
  'physical_right_count',{},'port_connectivity',{}, ...
  'candidate_only',{});
 maskTypes={};
 for k=1:numel(blocks)
  p=blocks{k};if ~startsWith(p,[model '/Grid/']),continue;end
  name=safeParam(p,'Name');bt=safeParam(p,'BlockType');
  mt=safeParam(p,'MaskType');rb=safeParam(p,'ReferenceBlock');
  ls=safeParam(p,'LinkStatus');
  if ~isempty(mt) && strcmp(bt,'SimscapeBlock'),maskTypes{end+1}=mt;end %#ok<AGROW>
  low=lower([p ' ' name ' ' bt ' ' mt ' ' rb]);
  cat='';
  if contains(low,'fault'),cat='fault_candidate';
  elseif contains(low,'load'),cat='load_candidate';
  elseif ~isempty(regexp(p,'/TF_B\d+_to_B\d+','once')),cat='transformer';
  elseif ~isempty(regexp(p,'/B\d+_to_B\d+','once')),cat='line';
  elseif strcmp(bt,'SimscapeBlock') && ~isempty(mt),cat='other_simscape_mask';
  end
  if isempty(cat),continue;end
  if strcmp(cat,'fault_candidate'),report.fault_blocks=report.fault_blocks+1;end
  if strcmp(cat,'load_candidate')
    report.load_named_blocks=report.load_named_blocks+1;
    if contains(lower(mt),'load')||contains(lower(rb),'load')
      report.load_mask_blocks=report.load_mask_blocks+1;
    end
  end
  if strcmp(cat,'line'),report.line_blocks=report.line_blocks+1;end
  if strcmp(cat,'transformer'),report.transformer_blocks=report.transformer_blocks+1;end
  mn=safeParam(p,'MaskNames');mp=safeParam(p,'MaskPrompts');mv=safeParam(p,'MaskValues');
  dpNames={};dpVals={};
  try
    dp=get_param(p,'DialogParameters');
    if isstruct(dp)
      dpNames=fieldnames(dp)';
      for z=1:numel(dpNames)
        dpVals{z}=safeParam(p,dpNames{z}); %#ok<AGROW>
      end
    end
  catch
  end
  ph=struct('inport',0,'outport',0,'left',0,'right',0);
  try,h=get_param(p,'PortHandles');ph.inport=numel(h.Inport);ph.outport=numel(h.Outport);
   if isfield(h,'LConn'),ph.left=numel(h.LConn);end
   if isfield(h,'RConn'),ph.right=numel(h.RConn);end
  catch
  end
  pc={};
  try
    q=get_param(p,'PortConnectivity');
    for z=1:numel(q)
      pc{z}=struct('type',safeField(q(z),'Type'), ...
       'src_block',blockName(safeField(q(z),'SrcBlock')), ...
       'src_port',safeField(q(z),'SrcPort'), ...
       'dst_block',blockName(safeField(q(z),'DstBlock')), ...
       'dst_port',safeField(q(z),'DstPort')); %#ok<AGROW>
    end
  catch
  end
  entries(end+1)=struct('path',p,'name',name,'block_type',bt, ...
   'mask_type',mt,'reference_block',rb,'link_status',ls, ...
   'category',cat,'mask_names',{toCell(mn)}, ...
   'mask_prompts',{toCell(mp)},'mask_values',{toCell(mv)}, ...
   'dialog_parameter_names',{dpNames},'dialog_parameter_values',{dpVals}, ...
   'inport_count',ph.inport,'outport_count',ph.outport, ...
   'physical_left_count',ph.left,'physical_right_count',ph.right, ...
   'port_connectivity',{pc},'candidate_only',true); %#ok<AGROW>
 end
 report.entries=entries;
 report.unique_grid_simscape_mask_types=unique(maskTypes);
 report.status='ORIGINAL_NATIVE_FAULT_LOAD_BRANCH_PARAMETER_WIRING_INVENTORIED';
catch ME
 report.status='ORIGINAL_NATIVE_EVENT_INTERFACE_INVENTORY_FAILED';
 report.error_id=ME.identifier;report.error_message=ME.message;
end
fp=fullfile(res,'physical_event_interface_inventory_v2.json');
fid=fopen(fp,'w');assert(fid>0);
fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Fault candidates=%d; load candidates=%d; line=%d; transformer=%d.\\n', ...
 report.fault_blocks,report.load_named_blocks,report.line_blocks,report.transformer_blocks);
try,close_system('IEEE39BusSystem',0);catch,end
end
function v=safeParam(p,n)
v='';
try,x=get_param(p,n);v=toText(x);catch,end
end
function v=safeField(s,n)
v=[];
try,if isfield(s,n),v=s.(n);end,catch,end
end
function s=blockName(h)
s='';
try,if isnumeric(h)&&isscalar(h)&&h>0,s=getfullname(h);end,catch,end
end
function c=toCell(x)
if isempty(x),c={};elseif iscell(x),c=cellfun(@toText,x,'UniformOutput',false);
else,c={toText(x)};end
end
function s=toText(x)
if ischar(x),s=x;
elseif isstring(x),s=char(join(x(:),','));
elseif isnumeric(x)||islogical(x),s=mat2str(x);
elseif iscell(x),s=strjoin(cellfun(@toText,x,'UniformOutput',false),';');
else
 try,s=char(string(x));catch,s=class(x);end
end
end
