function aefc_ieee39_fault_connection_map_v5
% Resolve the original native three-phase fault physical connection.
% Simulink physical connection lines may be branched; inspect parent and all
% LineChildren handles rather than matching only the parent line handle.
repo=pwd;res=fullfile(repo,'results','ieee39_stress_r1');if ~exist(res,'dir'),mkdir(res);end
q=struct('status','NOT_STARTED','fault_block','IEEE39BusSystem/Grid/Fault (Three-Phase)', ...
 'fault_port_line_handle',-1,'line_parent_handle',-1,'line_child_handles',[], ...
 'line_segments',struct([]),'matching_physical_ports',struct([]), ...
 'fault_location_resolved',false,'online_measurement_trusted',false, ...
 'full_network_safety_certified',false);
try
 [model,~]=aefc_ieee39_load_official;fault=[model '/Grid/Fault (Three-Phase)'];
 ph=get_param(fault,'PortHandles');assert(isfield(ph,'LConn')&&numel(ph.LConn)==1);
 faultPort=ph.LConn(1);line=get_param(faultPort,'Line');q.fault_port_line_handle=double(line);
 parent=-1;children=[];
 try,parent=get_param(line,'LineParent');catch,end
 try,children=get_param(line,'LineChildren');catch,end
 q.line_parent_handle=double(parent);q.line_child_handles=double(children(:))';
 lineHandles=unique([double(line);double(parent);double(children(:))]);
 lineHandles=lineHandles(isfinite(lineHandles)&lineHandles>0);
 segs=struct('handle',{},'parent',{},'src_block_handle',{},'src_block',{}, ...
  'src_port_handle',{},'dst_block_handle',{},'dst_block',{},'dst_port_handle',{}, ...
  'connected',{},'points',{});
 for k=1:numel(lineHandles)
  h=lineHandles(k);sb=-1;db=-1;sp=-1;dp=-1;conn='';pts=[];
  try,sb=double(get_param(h,'SrcBlockHandle'));catch,end
  try,db=double(get_param(h,'DstBlockHandle'));catch,end
  try,sp=double(get_param(h,'SrcPortHandle'));catch,end
  try,dp=double(get_param(h,'DstPortHandle'));catch,end
  try,conn=char(get_param(h,'Connected'));catch,end
  try,pts=get_param(h,'Points');catch,end
  segs(end+1)=struct('handle',h,'parent',double(safeParam(h,'LineParent')), ...
    'src_block_handle',sb,'src_block',blockName(sb),'src_port_handle',sp, ...
    'dst_block_handle',db,'dst_block',blockName(db),'dst_port_handle',dp, ...
    'connected',conn,'points',pts); %#ok<AGROW>
 end
 q.line_segments=segs;
 blocks=find_system(model,'FollowLinks','on','LookUnderMasks','all','Type','Block');
 hits=struct('block',{},'mask_type',{},'port_kind',{},'port_index',{}, ...
  'port_handle',{},'line_handle',{},'is_fault_block',{},'position',{});
 for b=1:numel(blocks)
  p=blocks{b};if ~startsWith(p,[model '/Grid/']),continue;end
  h=[];try,h=get_param(p,'PortHandles');catch,continue;end
  for fld={'LConn','RConn'}
   fn=fld{1};if ~isfield(h,fn),continue;end
   ports=h.(fn);
   for k=1:numel(ports)
    portHandle=ports(k);lh=-1;try,lh=double(get_param(portHandle,'Line'));catch,end
    if any(abs(lineHandles-lh)<1e-6)
     pos=[];try,pos=get_param(portHandle,'Position');catch,end
     hits(end+1)=struct('block',p,'mask_type',asText(safeParam(p,'MaskType')), ...
      'port_kind',fn,'port_index',k,'port_handle',double(portHandle), ...
      'line_handle',lh,'is_fault_block',strcmp(p,fault),'position',pos); %#ok<AGROW>
    end
   end
  end
 end
 q.matching_physical_ports=hits;
 nonFault=hits(~[hits.is_fault_block]);
 q.fault_location_resolved=~isempty(nonFault);
 if q.fault_location_resolved
  q.status='FAULT_CONNECTED_PHYSICAL_PORTS_RESOLVED';
 else
  q.status='FAULT_CONNECTION_BRANCH_HANDLES_CAPTURED_BUT_ENDPOINT_UNRESOLVED';
 end
catch ME
 q.status='FAULT_CONNECTION_MAP_FAILED';q.error_id=ME.identifier;q.error_message=ME.message;q.error_stack=ME.stack;
end
fp=fullfile(res,'fault_connection_map_v5.json');fid=fopen(fp,'w');assert(fid>0);
fwrite(fid,jsonencode(q,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
try,close_system('IEEE39BusSystem',0);catch,end
end
function v=safeParam(h,n),v=-1;try,v=get_param(h,n);catch,end,end
function s=blockName(h)
s='';try,if isnumeric(h)&&isscalar(h)&&h>0,s=getfullname(h);end,catch,end
end
function s=asText(x)
if ischar(x),s=x;elseif isstring(x),s=char(x);elseif isnumeric(x)||islogical(x),s=mat2str(x);else,try,s=char(string(x));catch,s=class(x);end,end
end
