function aefc_ieee39_sensor_library_inventory_v1
% Inventory candidate Simscape Electrical sensor blocks suitable for
% three-phase bus-voltage and branch-current measurement insertion.
outDir=fullfile(pwd,'results','ieee39_safety_mapping');
if ~exist(outDir,'dir'),mkdir(outDir);end
libs={'ee_lib','fl_lib','simscape'};
allCandidates=struct('library',{},'path',{},'name',{},'block_type',{}, ...
 'mask_type',{},'reference_block',{},'port_handles',{},'dialog_parameters',{},'error',{});
for q=1:numel(libs)
 lib=libs{q};
 try,load_system(lib);catch,continue;end
 try,blocks=find_system(lib,'LookUnderMasks','all','FollowLinks','on','Type','Block');catch,continue;end
 for k=1:numel(blocks)
  b=blocks{k};nm=lower(char(get_param(b,'Name')));
  mt=lower(safeText(safeParam(b,'MaskType')));
  rb=lower(safeText(safeParam(b,'ReferenceBlock')));
  bt=lower(safeText(safeParam(b,'BlockType')));
  qtext=[nm ' ' mt ' ' rb ' ' bt];
  if ~(contains(qtext,'sensor')||contains(qtext,'measurement')|| ...
       contains(qtext,'three-phase v-i')||contains(qtext,'three phase v-i')|| ...
       contains(qtext,'voltage measurement')||contains(qtext,'current measurement'))
   continue
  end
  rec=struct('library',lib,'path',b,'name',char(get_param(b,'Name')), ...
   'block_type',safeText(safeParam(b,'BlockType')), ...
   'mask_type',safeText(safeParam(b,'MaskType')), ...
   'reference_block',safeText(safeParam(b,'ReferenceBlock')), ...
   'port_handles',portSummary(b),'dialog_parameters',struct([]),'error','');
  try
   p=get_param(b,'DialogParameters');names=fieldnames(p);
   rows=struct('name',{},'prompt',{},'type',{},'value',{});
   for j=1:numel(names)
    nm2=names{j};v='';pr='';ty='';
    try,v=safeText(get_param(b,nm2));catch,try,v=safeText(p.(nm2).Value);catch,end,end
    try,pr=safeText(p.(nm2).Prompt);catch,end
    try,ty=safeText(p.(nm2).Type);catch,end
    rows(end+1)=struct('name',nm2,'prompt',pr,'type',ty,'value',v); %#ok<AGROW>
   end
   rec.dialog_parameters=rows;
  catch ME,rec.error=ME.message;end
  allCandidates(end+1)=rec; %#ok<AGROW>
 end
end
info=struct();info.libraries_scanned=libs;info.candidate_block_count=numel(allCandidates);
info.candidate_blocks=allCandidates;
info.interpretation=['Candidate blocks are inventoried for library selection only. A block is considered usable ' ...
 'for native Simscape instrumentation only after its conserving-port type, physical-signal output, phase count, ' ...
 'unit, and compatibility with the native Busbar/line/transformer ports are checked.'];
fp=fullfile(outDir,'native_ieee39_sensor_library_inventory_v1.json');
fid=fopen(fp,'w');assert(fid>0,'AEFC:SensorLibraryIO','Cannot write sensor library inventory');
fwrite(fid,jsonencode(info,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Sensor library candidates: %d across %d libraries.\n',numel(allCandidates),numel(libs));
end

function out=portSummary(block)
out=struct('field',{},'port_number',{},'port_type',{});
try
 ph=get_param(block,'PortHandles');fields=fieldnames(ph);
 for i=1:numel(fields)
  hs=ph.(fields{i});
  for j=1:numel(hs)
   out(end+1)=struct('field',fields{i},'port_number',safeText(safeParam(hs(j),'PortNumber')), ...
    'port_type',safeText(safeParam(hs(j),'PortType'))); %#ok<AGROW>
  end
 end
catch
end
end
function x=safeParam(h,n)
try,x=get_param(h,n);catch,x='';end
end
function x=safeText(v)
if ischar(v),x=v;elseif isstring(v),x=char(v);elseif isnumeric(v),x=mat2str(v);else,try,x=char(v);catch,x='';end,end
end
