function aefc_ieee39_fault_connection_map_v6
% Resolve the original native three-phase fault via PortConnectivity's
% physical destination port handles, then map those handles to block paths.
repo=pwd;res=fullfile(repo,'results','ieee39_stress_r1');if ~exist(res,'dir'),mkdir(res);end
q=struct('status','NOT_STARTED','fault_block','IEEE39BusSystem/Grid/Fault (Three-Phase)', ...
 'port_connectivity',struct([]),'connected_physical_ports',struct([]), ...
 'line_handle',-1,'line_parent_handle',-1,'line_child_handles',[], ...
 'line_segments',struct([]),'resolved_bus_blocks',{{}}, ...
 'fault_location_resolved',false,'online_measurement_trusted',false, ...
 'full_network_safety_certified',false);
try
 [model,~]=aefc_ieee39_load_official;fault=[model '/Grid/Fault (Three-Phase)'];
 pc=get_param(fault,'PortConnectivity');
 pcOut=struct('type',{},'src_block_handle',{},'src_block',{},'src_port_handles',{}, ...
   'dst_block_handle',{},'dst_block',{},'dst_port_handles',{});
 ports=[];
 for k=1:numel(pc)
  sb=safeNum(pc(k),'SrcBlock');db=safeNum(pc(k),'DstBlock');
  sp=safeVector(pc(k),'SrcPort');dp=safeVector(pc(k),'DstPort');
  pcOut(end+1)=struct('type',safeText(pc(k),'Type'), ...
   'src_block_handle',sb,'src_block',blockName(sb), ...
   'src_port_handles',sp,'dst_block_handle',db,'dst_block',blockName(db), ...
   'dst_port_handles',dp); %#ok<AGROW>
  ports=[ports sp(:)' dp(:)']; %#ok<AGROW>
 end
 q.port_connectivity=pcOut;
 ph=get_param(fault,'PortHandles');
 if isfield(ph,'LConn')&&~isempty(ph.LConn)
  line=get_param(ph.LConn(1),'Line');q.line_handle=double(line);
  try,q.line_parent_handle=double(get_param(line,'LineParent'));catch,end
  try,q.line_child_handles=double(get_param(line,'LineChildren'));catch,end
 end
 portRecords=struct('handle',{},'parent',{},'name',{},'block_type',{}, ...
   'mask_type',{},'port_number',{},'port_type',{},'line_handle',{},'position',{},'error',{});
 for k=1:numel(ports)
  h=ports(k);if isempty(h)||~isfinite(h)||h<=0,continue;end
  parent='';name='';bt='';mt='';pn='';pt='';lh=-1;pos=[];err='';
  try,parent=char(get_param(h,'Parent'));catch ME,err=[ME.identifier ': ' ME.message];end
  if ~isempty(parent)
   try,name=char(get_param(parent,'Name'));catch,end
   try,bt=char(get_param(parent,'BlockType'));catch,end
   try,mt=char(get_param(parent,'MaskType'));catch,end
  end
  try,pn=asText(get_param(h,'PortNumber'));catch,end
  try,pt=asText(get_param(h,'PortType'));catch,end
  try,lh=double(get_param(h,'Line'));catch,end
  try,pos=get_param(h,'Position');catch,end
  portRecords(end+1)=struct('handle',double(h),'parent',parent,'name',name, ...
   'block_type',bt,'mask_type',mt,'port_number',pn,'port_type',pt, ...
   'line_handle',lh,'position',pos,'error',err); %#ok<AGROW>
 end
 q.connected_physical_ports=portRecords;
 bus={};
 for k=1:numel(portRecords)
  tok=regexp(portRecords(k).parent,'/Grid/Bus([^/]+)$','tokens','once');
  if ~isempty(tok),bus{end+1}=tok{1};end %#ok<AGROW>
 end
 q.resolved_bus_blocks=unique(bus);
 q.fault_location_resolved=~isempty(q.resolved_bus_blocks);
 if q.fault_location_resolved
  q.status='FAULT_CONNECTED_BUS_PORTS_RESOLVED';
 else
  q.status='PORTCONNECTIVITY_ENDPOINTS_CAPTURED_BUS_NOT_DIRECTLY_RESOLVED';
 end
catch ME
 q.status='FAULT_CONNECTION_MAP_FAILED';q.error_id=ME.identifier;q.error_message=ME.message;q.error_stack=ME.stack;
end
fp=fullfile(res,'fault_connection_map_v6.json');fid=fopen(fp,'w');assert(fid>0);
fwrite(fid,jsonencode(q,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
try,close_system('IEEE39BusSystem',0);catch,end
end
function v=safeNum(s,n),v=-1;try,v=double(s.(n));catch,end,end
function v=safeVector(s,n),v=[];try,v=double(s.(n));catch,end,end
function s=safeText(x,n),s='';try,s=asText(x.(n));catch,end,end
function s=blockName(h)
s='';try,if isnumeric(h)&&isscalar(h)&&h>0,s=getfullname(h);end,catch,end
end
function s=asText(x)
if ischar(x),s=x;elseif isstring(x),s=char(x);elseif isnumeric(x)||islogical(x),s=mat2str(x);else,try,s=char(string(x));catch,s=class(x);end,end
end
