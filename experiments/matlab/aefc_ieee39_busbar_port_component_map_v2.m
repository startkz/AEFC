function aefc_ieee39_busbar_port_component_map_v2
% Map every original IEEE39 busbar physical port to connected Simscape
% component ports using the parent/child physical connection-line handles.
% I# candidates follow the empirically validated interleaved port order:
% I_(2k-1)=LConn_k and I_(2k)=RConn_k. Signature audit is separate.
repo=pwd;res=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(res,'dir'),mkdir(res);end
q=struct('status','NOT_STARTED','model','IEEE39BusSystem', ...
 'busbar_blocks',0,'busbar_physical_ports',0,'busbar_ports_matched',0, ...
 'busbar_ports_unresolved',0,'unique_connected_line_blocks',0, ...
 'unique_connected_transformer_blocks',0,'bus16_1_rconn1_verified',false, ...
 'busbar_port_current_variable_mapping_validated',false, ...
 'current_variable_order_rule','I_(2k-1)=LConn_k; I_(2k)=RConn_k', ...
 'all_ports',struct([]),'busbar_port_mappings',struct([]), ...
 'full_network_safety_certified',false,'online_measurement_trusted',false);
try
 [model,~]=aefc_ieee39_load_official;
 blocks=find_system(model,'FollowLinks','on','LookUnderMasks','all','Type','Block');
 ports=struct('block',{},'block_name',{},'mask_type',{},'port_kind',{}, ...
  'port_index',{},'port_handle',{},'line_handle',{},'line_set',{},'is_busbar',{}, ...
  'current_variable_candidate',{});
 busNames={};
 for b=1:numel(blocks)
  p=blocks{b};if ~startsWith(p,[model '/Grid/']),continue;end
  nm=char(get_param(p,'Name'));mt=asText(safeParam(p,'MaskType'));
  tok=regexp(nm,'^Bus([0-9]+)(?:_([0-9]+))?$','tokens','once');
  isBus=~isempty(tok);
  if isBus,busNames{end+1}=nm;end %#ok<AGROW>
  ph=[];try,ph=get_param(p,'PortHandles');catch,continue;end
  for fld={'LConn','RConn'}
   fn=fld{1};if ~isfield(ph,fn),continue;end
   hh=ph.(fn);
   for k=1:numel(hh)
    h=hh(k);lh=-1;try,lh=double(get_param(h,'Line'));catch,end
    lineSet=[];
    if isfinite(lh)&&lh>0
     lineSet=lh;
     try,lineSet=[lineSet;double(get_param(lh,'LineParent'))];catch,end
     try,lc=get_param(lh,'LineChildren');lineSet=[lineSet;double(lc(:))];catch,end
     lineSet=unique(lineSet(isfinite(lineSet)&lineSet>0));
    end
    currentCandidate='';
    if isBus
     if strcmp(fn,'LConn'),ord=2*k-1;else,ord=2*k;end
     currentCandidate=sprintf('I%d',ord);
    end
    ports(end+1)=struct('block',p,'block_name',nm,'mask_type',mt, ...
      'port_kind',fn,'port_index',k,'port_handle',double(h), ...
      'line_handle',lh,'line_set',lineSet(:)', ...
      'is_busbar',isBus,'current_variable_candidate',currentCandidate); %#ok<AGROW>
   end
  end
 end
 busPorts=find([ports.is_busbar]);
 mappings=struct('bus_block',{},'logical_bus',{},'physical_section',{}, ...
  'bus_port_kind',{},'bus_port_index',{},'current_variable_candidate',{}, ...
  'bus_port_handle',{},'bus_line_set',{},'connected_ports',{},'connected_port_count',{}, ...
  'connected_blocks',{},'mapping_status',{},'current_variable_mapping_validated',{});
 lineBlocks={};tfBlocks={};matched=0;
 for ii=1:numel(busPorts)
  z=ports(busPorts(ii));tok=regexp(z.block_name,'^Bus([0-9]+)(?:_([0-9]+))?$','tokens','once');
  logicalBus=tok{1};section='';if numel(tok)>1,section=tok{2};end
  hits=struct('block',{},'block_name',{},'port_kind',{},'port_index',{}, ...
    'port_handle',{},'line_handle',{},'shared_line_handles',{});
  if ~isempty(z.line_set)
   for jj=1:numel(ports)
    y=ports(jj);if strcmp(y.block,z.block),continue;end
    shared=[];
    for a=1:numel(z.line_set)
     for c=1:numel(y.line_set)
      if abs(z.line_set(a)-y.line_set(c))<1e-6,shared(end+1)=z.line_set(a);end %#ok<AGROW>
     end
    end
    shared=unique(shared);
    if ~isempty(shared)
     hits(end+1)=struct('block',y.block,'block_name',y.block_name, ...
      'port_kind',y.port_kind,'port_index',y.port_index, ...
      'port_handle',y.port_handle,'line_handle',y.line_handle, ...
      'shared_line_handles',shared); %#ok<AGROW>
    end
   end
  end
  cb=unique({hits.block});
  if ~isempty(hits),matched=matched+1;end
  for c=1:numel(hits)
   nm=hits(c).block_name;
   if startsWith(nm,'TF ') || startsWith(nm,'TF_')
    tfBlocks{end+1}=nm; %#ok<AGROW>
   elseif contains(nm,' to ')
    lineBlocks{end+1}=nm; %#ok<AGROW>
   end
  end
  hitCells=cell(1,numel(hits));
  for hc=1:numel(hits),hitCells{hc}=hits(hc);end
  mappings(end+1)=struct('bus_block',z.block,'logical_bus',logicalBus, ...
   'physical_section',section,'bus_port_kind',z.port_kind, ...
   'bus_port_index',z.port_index,'current_variable_candidate',z.current_variable_candidate, ...
   'bus_port_handle',z.port_handle,'bus_line_set',z.line_set, ...
   'connected_ports',{hitCells},'connected_port_count',numel(hits), ...
   'connected_blocks',{cb}, ...
   'mapping_status',ternary(isempty(hits),'UNRESOLVED','MATCHED'), ...
   'current_variable_mapping_validated',false); %#ok<AGROW>
 end
 q.busbar_blocks=numel(unique(busNames));q.busbar_physical_ports=numel(busPorts);
 q.busbar_ports_matched=matched;q.busbar_ports_unresolved=numel(busPorts)-matched;
 q.unique_connected_line_blocks=numel(unique(lineBlocks));
 q.unique_connected_transformer_blocks=numel(unique(tfBlocks));
 q.all_ports=ports;q.busbar_port_mappings=mappings;
 idx=find(strcmp({mappings.bus_block},[model '/Grid/Bus16_1']) & ...
   strcmp({mappings.bus_port_kind},'RConn') & [mappings.bus_port_index]==1,1);
 if ~isempty(idx)
  h=mappings(idx).connected_ports;
  q.bus16_1_rconn1_verified=any(cellfun(@(y) ...
      strcmp(y.block,[model '/Grid/B16 to B17']) && ...
      strcmp(y.port_kind,'LConn') && y.port_index==1,h));
 end
 if q.bus16_1_rconn1_verified
  q.status='BUSBAR_PORT_COMPONENT_MAP_BUILT_BUS16_REFERENCE_VERIFIED';
 else
  q.status='BUSBAR_PORT_COMPONENT_MAP_BUILT_REFERENCE_NOT_RESOLVED';
 end
catch ME
 q.status='BUSBAR_PORT_COMPONENT_MAP_FAILED';q.error_id=ME.identifier;
 q.error_message=ME.message;q.error_stack=ME.stack;
end
fp=fullfile(res,'native_busbar_port_component_map_v2.json');
fid=fopen(fp,'w');assert(fid>0);fwrite(fid,jsonencode(q,'PrettyPrint',true),'char');
fwrite(fid,sprintf('\n'),'char');fclose(fid);
try,close_system('IEEE39BusSystem',0);catch,end
end
function v=safeParam(p,n),v='';try,v=get_param(p,n);catch,end,end
function s=asText(x)
if ischar(x),s=x;elseif isstring(x),s=char(x);elseif isnumeric(x)||islogical(x),s=mat2str(x);else,try,s=char(string(x));catch,s=class(x);end,end
end
function s=ternary(c,a,b),if c,s=a;else,s=b;end,end
