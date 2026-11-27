function aefc_ieee39_grid_physical_leaf_census_v5
% Corrected offline physical-leaf census of the ORIGINAL MathWorks R2024b
% IEEE39 Simscape log. The leaf variable is the PARENT node immediately
% before '/series' (the previous v1 incorrectly classified key='series').
% Values are an offline plant oracle, NOT authenticated online sensors.
repo=pwd;res=fullfile(repo,'results','ieee39_safety_mapping');
if ~exist(res,'dir'),mkdir(res);end
report=struct('status','NOT_STARTED','official_original_model','IEEE39BusSystem', ...
 'sampling_window_seconds',0.05,'visited_nodes',0,'logged_leaf_paths',0, ...
 'logical_bus_ids_with_Vt',0,'physical_bus_voltage_sections',0, ...
 'bus_voltage_leaf_rows',0,'bus_phase_leaf_rows',0,'bus_current_leaf_rows',0, ...
 'line_components_with_current',0,'line_current_leaf_rows',0, ...
 'transformer_components_with_current',0,'transformer_current_leaf_rows',0, ...
 'branch_current_leaf_rows',0,'branch_loss_leaf_rows',0, ...
 'full_network_online_observer_verified',false, ...
 'full_network_DAE_state_estimation_certified',false, ...
 'rigorous_nonlinear_reachability_certified',false, ...
 'all_entries_offline_simscape_oracle_only',true, ...
 'trusted_online_safety_sensors',false);
try
 [model,~]=aefc_ieee39_load_official;
 in=Simulink.SimulationInput(model);
 in=in.setModelParameter('StopTime','0.05','ReturnWorkspaceOutputs','on', ...
   'SimscapeLogType','all','SimscapeLogName','AEFC_LEAF_SIMLOG');
 out=sim(in);node=[];
 try,node=out.get('AEFC_LEAF_SIMLOG');catch,end
 if isempty(node),try,node=simscape.logging.getSimulationLog(model);catch,end,end
 assert(isa(node,'simscape.logging.Node'),'AEFC:NoSimscapeLog','No native Simscape logging tree');
 stack={node};paths={model};head=1;maxNodes=60000;maxEntries=40000;
 entries=struct('path',{},'category',{},'logical_bus',{},'bus_section',{}, ...
   'component',{},'variable',{},'unit',{},'points',{},'dimension',{}, ...
   'time_start',{},'time_end',{},'min_real',{},'max_real',{}, ...
   'max_abs',{},'finite',{},'error',{});
 busIds={};busSections={};lineIds={};tfIds={};
 while head<=numel(stack) && report.visited_nodes<maxNodes
   nd=stack{head};parent=paths{head};head=head+1;
   report.visited_nodes=report.visited_nodes+1;
   props=properties(nd);
   for j=1:numel(props)
     key=props{j};child=[];
     try,child=nd.(key);catch,end
     if isa(child,'simscape.logging.Node')
       stack{end+1}=child;paths{end+1}=[parent '/' key]; %#ok<AGROW>
     elseif isa(child,'simscape.logging.Series')
       report.logged_leaf_paths=report.logged_leaf_paths+1;
       fullPath=[parent '/' key];
       if ~contains(fullPath,[model '/Grid/']),continue;end
       variable=regexp(parent,'/([^/]+)$','tokens','once');
       if isempty(variable),continue;end
       variable=variable{1};category='other';logicalBus='';section='';
       component='';
        tok=regexp(parent,'/Grid/Bus([^/]+)/(Vt|ph|I\\d+)$','tokens','once');
        if ~isempty(tok)
          busParts=strsplit(tok{1},'_');logicalBus=busParts{1};section='';
          if numel(busParts)>1,section=busParts{2};end
          variable=tok{2};
          if strcmp(variable,'Vt')
            category='bus_voltage';busIds{end+1}=logicalBus; %#ok<AGROW>
            busSections{end+1}=[logicalBus '_' section]; %#ok<AGROW>
            report.bus_voltage_leaf_rows=report.bus_voltage_leaf_rows+1;
          elseif strcmp(variable,'ph')
            category='bus_phase';report.bus_phase_leaf_rows=report.bus_phase_leaf_rows+1;
          else
            category='bus_current';report.bus_current_leaf_rows=report.bus_current_leaf_rows+1;
          end
        else
          % Native line current is logged below transmission_line/inductor_{a,b,c}/i/amplitude.
          tok=regexp(parent,'/Grid/([^/]+)/transmission_line/(inductor_[abc])/i/amplitude$','tokens','once');
          if ~isempty(tok)
            component=tok{1};variable=[tok{2} '/i/amplitude'];
            category='line_current';lineIds{end+1}=component; %#ok<AGROW>
          else
            % Native transformer winding currents are logged as i1 and i2.
            tok=regexp(parent,'/Grid/(TF_[^/]+)/(i1|i2)$','tokens','once');
            if ~isempty(tok)
              component=tok{1};variable=tok{2};
              category='transformer_current';tfIds{end+1}=component; %#ok<AGROW>
            end
          end
        end
       if ~any(strcmp(category,{'bus_voltage','bus_phase','bus_current', ...
             'line_current','line_loss','transformer_current','transformer_loss'}))
         continue
       end
       unit='';err='';v=[];t=[];dim=[];
       try
         unit=char(child.unit);dim=double(child.dimension);
         v=double(values(child));t=double(time(child));
       catch ME
         err=[ME.identifier ': ' ME.message];
       end
       if any(strcmp(category,{'line_current','transformer_current'})) && ~strcmp(unit,'A')
         continue
       end
       finite=~isempty(v)&&all(isfinite(real(v(:))))&&all(isfinite(imag(v(:))));
       mn=NaN;mx=NaN;ma=NaN;ts=NaN;te=NaN;
       if finite
         mn=min(real(v(:)));mx=max(real(v(:)));ma=max(abs(v(:)));
       end
       if ~isempty(t),ts=min(t(:));te=max(t(:));end
       if numel(entries)<maxEntries
         entries(end+1)=struct('path',fullPath,'category',category, ...
          'logical_bus',logicalBus,'bus_section',section,'component',component, ...
          'variable',variable,'unit',unit,'points',double(child.points), ...
          'dimension',dim,'time_start',ts,'time_end',te, ...
          'min_real',mn,'max_real',mx,'max_abs',ma, ...
          'finite',finite,'error',err); %#ok<AGROW>
       end
     end
   end
 end
 report.truncated=report.visited_nodes>=maxNodes || head<=numel(stack) || numel(entries)>=maxEntries;
 report.logical_bus_ids_with_Vt=numel(unique(busIds));
 report.physical_bus_voltage_sections=numel(unique(busSections));
 report.line_components_with_current=numel(unique(lineIds));
 report.transformer_components_with_current=numel(unique(tfIds));
 report.line_current_leaf_rows=sum(strcmp({entries.category},'line_current'));
 report.transformer_current_leaf_rows=sum(strcmp({entries.category},'transformer_current'));
 report.branch_current_leaf_rows=report.line_current_leaf_rows+report.transformer_current_leaf_rows;
 report.branch_loss_leaf_rows=sum(ismember({entries.category},{'line_loss','transformer_loss'}));
 report.entries=entries;
 report.status='OFFLINE_PHYSICAL_GRID_LEAF_VALUES_EXTRACTED';
catch ME
 report.status='OFFLINE_PHYSICAL_GRID_LEAF_EXTRACTION_FAILED';
 report.error_id=ME.identifier;report.error_message=ME.message;report.error_stack=ME.stack;
 report.error_stack=ME.stack;
end
fp=fullfile(res,'native_grid_physical_leaf_census_v5.json');
fid=fopen(fp,'w');assert(fid>0);
fwrite(fid,jsonencode(report,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');fclose(fid);
fprintf('Grid physical leaves: buses=%d sections=%d lines=%d transformers=%d; offline only.\\n', ...
 report.logical_bus_ids_with_Vt,report.physical_bus_voltage_sections, ...
 report.line_components_with_current,report.transformer_components_with_current);
try,close_system('IEEE39BusSystem',0);catch,end
end
