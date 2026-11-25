function aefc_ieee39_fault_connection_map_v4
% Resolve the native three-phase fault's Simscape physical port to a bus or
% connection label by matching its physical connection line handle against
% all physical ports in the original Grid subsystem.
repo=pwd;res=fullfile(repo,'results','ieee39_stress_r1');if ~exist(res,'dir'),mkdir(res);end
q=struct('status','NOT_STARTED','fault_block','IEEE39BusSystem/Grid/Fault (Three-Phase)', ...
 'fault_port_line_handle',-1,'matching_physical_ports',struct([]), ...
 'line_object_parameters',struct(),'fault_location_resolved',false, ...
 'online_measurement_trusted',false,'full_network_safety_certified',false);
try
 [model,~]=aefc_ieee39_load_official;fault=[model '/Grid/Fault (Three-Phase)'];
 ph=get_param(fault,'PortHandles');assert(isfield(ph,'LConn')&&numel(ph.LConn)==1);
 line=get_param(ph.LConn(1),'Line');q.fault_port_line_handle=double(line);
 params={};vals={};
 try
  op=get_param(line,'ObjectParameters');params=fieldnames(op)';
  for k=1:numel(params)
   try,vals{k}=asText(get_param(line,params{k}));catch,vals{k}='';end %#ok<AGROW>
  end
 catch
 end
 q.line_object_parameters=struct('names',{params},'values',{vals});
 blocks=find_system(model,'FollowLinks','on','LookUnderMasks','all','Type','Block');
 hits=struct('block',{},'name',{},'mask_type',{},'port_kind',{}, ...
  'port_index',{},'port_handle',{},'line_handle',{},'position',{});
 for b=1:numel(blocks)
  p=blocks{b};if ~startsWith(p,[model '/Grid/']),continue;end
  h=[];
  try,h=get_param(p,'PortHandles');catch,continue;end
  for fld={'LConn','RConn'}
   fn=fld{1};if ~isfield(h,fn),continue;end
   for k=1:numel(h.(fn))
    lh=-1;try,lh=get_param(h.(fn)(k),'Line');catch,end
    if isequal(double(lh),double(line))
     pos=[];try,pos=get_param(h.(fn)(k),'Position');catch,end
     hits(end+1)=struct('block',p,'name',asText(get_param(p,'Name')), ...
       'mask_type',asText(safeParam(p,'MaskType')),'port_kind',fn, ...
       'port_index',k,'port_handle',double(h.(fn)(k)), ...
       'line_handle',double(lh),'position',pos); %#ok<AGROW>
    end
   end
  end
 end
 q.matching_physical_ports=hits;
 q.fault_location_resolved=numel(hits)>=2;
 if q.fault_location_resolved,q.status='FAULT_PHYSICAL_LINE_HANDLE_MATCHED';else,q.status='FAULT_PHYSICAL_LINE_HANDLE_NOT_RESOLVED';end
catch ME
 q.status='FAULT_CONNECTION_MAP_FAILED';q.error_id=ME.identifier;q.error_message=ME.message;q.error_stack=ME.stack;
end
fp=fullfile(res,'fault_connection_map_v4.json');fid=fopen(fp,'w');assert(fid>0);
fwrite(fid,jsonencode(q,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
try,close_system('IEEE39BusSystem',0);catch,end
end
function v=safeParam(p,n),v='';try,v=get_param(p,n);catch,end,end
function s=asText(x)
if ischar(x),s=x;elseif isstring(x),s=char(x);elseif isnumeric(x)||islogical(x),s=mat2str(x);else,try,s=char(string(x));catch,s=class(x);end,end
end
