function aefc_ieee39_physical_event_interface_inventory_v3
% Full-model inventory of native load/fault/line/transformer blocks and
% actual Simscape physical port connections. Discovery only; no block is
% changed, and no safety or disturbance validity is inferred.
repo=pwd;out=fullfile(repo,'results','ieee39_stress_r1');
if ~exist(out,'dir'),mkdir(out);end
report=struct('status','NOT_STARTED','model','IEEE39BusSystem', ...
 'blocks_scanned',0,'fault_blocks',0,'actual_load_mask_blocks',0, ...
 'load_connection_labels',0,'transmission_line_blocks',0, ...
 'transformer_blocks',0,'unique_simscape_mask_types',{{}}, ...
 'fault_block',struct(),'candidate_blocks',struct([]), ...
 'fault_location_physically_resolved',false, ...
 'validated_exogenous_stressor_available',false, ...
 'full_network_safety_certified',false);
try
 [model,~]=aefc_ieee39_load_official;
 blocks=find_system(model,'FollowLinks','on','LookUnderMasks','all','Type','Block');
 report.blocks_scanned=numel(blocks);
 entries=struct('path',{},'name',{},'block_type',{},'mask_type',{}, ...
  'reference_block',{},'category',{},'mask_names',{},'mask_prompts',{}, ...
  'mask_values',{},'dialog_parameter_names',{},'dialog_parameter_values',{}, ...
  'physical_ports',{},'port_connectivity',{},'candidate_only',{});
 maskTypes={};
 for k=1:numel(blocks)
  p=blocks{k};nm=safeParam(p,'Name');bt=safeParam(p,'BlockType');
  mt=safeParam(p,'MaskType');rb=safeParam(p,'ReferenceBlock');
  if strcmp(bt,'SimscapeBlock') && ~isempty(mt),maskTypes{end+1}=mt;end %#ok<AGROW>
  low=lower([p ' ' nm ' ' bt ' ' mt ' ' rb]);
  cat='';
  if contains(low,'fault'),cat='fault';
  elseif strcmp(bt,'ConnectionLabel') && contains(low,'load'),cat='load_label';
  elseif contains(lower(mt),'load')||contains(lower(rb),'load'),cat='load_component';
  elseif contains(lower(mt),'transmission') && contains(lower(mt),'line'),cat='transmission_line';
  elseif contains(lower(mt),'transformer'),cat='transformer';
  end
  if isempty(cat),continue;end
  if strcmp(cat,'fault'),report.fault_blocks=report.fault_blocks+1;end
  if strcmp(cat,'load_label'),report.load_connection_labels=report.load_connection_labels+1;end
  if strcmp(cat,'load_component'),report.actual_load_mask_blocks=report.actual_load_mask_blocks+1;end
  if strcmp(cat,'transmission_line'),report.transmission_line_blocks=report.transmission_line_blocks+1;end
  if strcmp(cat,'transformer'),report.transformer_blocks=report.transformer_blocks+1;end
  mn=safeParam(p,'MaskNames');mp=safeParam(p,'MaskPrompts');mv=safeParam(p,'MaskValues');
  dpNames={};dpVals={};
  try
   dp=get_param(p,'DialogParameters');
   if isstruct(dp)
    dpNames=fieldnames(dp)';
    for z=1:numel(dpNames),dpVals{z}=safeParam(p,dpNames{z});end %#ok<AGROW>
   end
  catch
  end
  ph=struct('left',{{}},'right',{{}});
  try
   h=get_param(p,'PortHandles');
   if isfield(h,'LConn')
    for z=1:numel(h.LConn),ph.left{z}=portConnection(h.LConn(z));end %#ok<AGROW>
   end
   if isfield(h,'RConn')
    for z=1:numel(h.RConn),ph.right{z}=portConnection(h.RConn(z));end %#ok<AGROW>
   end
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
  e=struct('path',p,'name',nm,'block_type',bt,'mask_type',mt, ...
   'reference_block',rb,'category',cat,'mask_names',{toCell(mn)}, ...
   'mask_prompts',{toCell(mp)},'mask_values',{toCell(mv)}, ...
   'dialog_parameter_names',{dpNames},'dialog_parameter_values',{dpVals}, ...
   'physical_ports',ph,'port_connectivity',{pc},'candidate_only',true);
  entries(end+1)=e; %#ok<AGROW>
  if strcmp(cat,'fault'),report.fault_block=e;end
 end
 report.unique_simscape_mask_types=unique(maskTypes);
 report.candidate_blocks=entries;
 if report.fault_blocks==1
  report.status='NATIVE_FAULT_LOAD_LINE_TRANSFORMER_PARAMETERS_INVENTORIED';
 else
  report.status='NATIVE_FAULT_BLOCK_COUNT_UNEXPECTED';
 end
catch ME
 report.status='NATIVE_PHYSICAL_EVENT_INVENTORY_FAILED';
 report.error_id=ME.identifier;report.error_message=ME.message;report.error_stack=ME.stack;
end
fp=fullfile(out,'physical_event_interface_inventory_v3.json');
fid=fopen(fp,'w');assert(fid>0);
fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Native faults=%d loads=%d lines=%d transformers=%d.\\n', ...
 report.fault_blocks,report.actual_load_mask_blocks,report.transmission_line_blocks,report.transformer_blocks);
try,close_system('IEEE39BusSystem',0);catch,end
end
function c=portConnection(h)
c=struct('port_handle',double(h),'line_handle',-1,'source_block','','destination_block','', ...
 'source_port',[],'destination_port',[],'error','');
try
 line=get_param(h,'Line');c.line_handle=double(line);
 if isnumeric(line)&&isscalar(line)&&line>0
  sb=get_param(line,'SrcBlockHandle');db=get_param(line,'DstBlockHandle');
  if isnumeric(sb)&&isscalar(sb)&&sb>0,c.source_block=getfullname(sb);end
  if isnumeric(db)&&isscalar(db)&&db>0,c.destination_block=getfullname(db);end
  try,c.source_port=double(get_param(line,'SrcPortHandle'));catch,end
  try,c.destination_port=double(get_param(line,'DstPortHandle'));catch,end
 end
catch ME,c.error=[ME.identifier ': ' ME.message];end
end
function v=safeParam(p,n)
v='';try,v=toText(get_param(p,n));catch,end
end
function v=safeField(s,n)
v=[];try,if isfield(s,n),v=s.(n);end,catch,end
end
function s=blockName(h)
s='';try,if isnumeric(h)&&isscalar(h)&&h>0,s=getfullname(h);end,catch,end
end
function c=toCell(x)
if isempty(x),c={};elseif iscell(x),c=cellfun(@toText,x,'UniformOutput',false);else,c={toText(x)};end
end
function s=toText(x)
if ischar(x),s=x;elseif isstring(x),s=char(join(x(:),','));
elseif isnumeric(x)||islogical(x),s=mat2str(x);
elseif iscell(x),s=strjoin(cellfun(@toText,x,'UniformOutput',false),';');
else,try,s=char(string(x));catch,s=class(x);end,end
end
