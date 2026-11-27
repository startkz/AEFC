function aefc_ieee39_physical_disturbance_inventory
% Real ORIGINAL R2024b IEEE39 model: enumerate available external load,
% network switching, line, transformer, inertia and Pref disturbance ports.
% Finding a block doesn't authorize rewiring it or claim actuator safety.
repo=pwd;res=fullfile(repo,'results','ieee39_stress_r1');
if ~exist(res,'dir'),mkdir(res);end
result=struct('status','NOT_STARTED','model','IEEE39BusSystem', ...
    'candidate_count',0,'grid_load_candidates',0, ...
    'grid_line_switch_candidates',0,'generator_injection_candidates',0, ...
    'validated_exogenous_stressor_available',false, ...
    'native_physical_disturbance_preserves_safety_contract',false, ...
    'full_network_safety_certified',false);
try
    [model,~]=aefc_ieee39_load_official;
    blocks=find_system(model,'FollowLinks','on','LookUnderMasks','all','Type','Block');
    entries=struct('path',{},'name',{},'type',{}, ...
      'category',{},'inports',{},'outports',{}, ...
      'source_block_links',{},'candidate_only',{});
    for k=1:numel(blocks)
        path=blocks{k};
        nm='';typ='';
        try,nm=char(get_param(path,'Name'));catch,end
        try,typ=char(get_param(path,'BlockType'));catch,end
        str=lower([path ' ' nm ' ' typ]);
        cat='';
        if contains(str,'/grid/') && ...
            (contains(str,'load') || contains(str,'demand'))
            cat='grid_load';
        elseif contains(str,'/grid/') && ...
            (contains(str,'breaker') || contains(str,'fault') || ...
             contains(str,'switch') || contains(str,'line'))
            cat='grid_branch_switch_or_line';
        elseif contains(str,'/generators/') && ...
            (contains(str,'pref') || contains(str,'mechanical power') || ...
             contains(str,'governor'))
            cat='generator_pref_or_governor';
        elseif contains(str,'step') || contains(str,'pulse') || ...
              contains(str,'ramp')
            cat='time_varying_source';
        end
        if isempty(cat),continue;end
        inports=0;outports=0;src={};
        try
            p=get_param(path,'PortHandles');
            inports=numel(p.Inport);outports=numel(p.Outport);
            for ii=1:inports
                h=get_param(p.Inport(ii),'Line');
                if h~=-1
                    ph=get_param(h,'SrcBlockHandle');
                    if ph>0,src{end+1}=getfullname(ph);end %#ok<AGROW>
                end
            end
        catch
        end
        entries(end+1)=struct('path',path,'name',nm,'type',typ, ...
            'category',cat,'inports',inports,'outports',outports, ...
            'source_block_links',{src},'candidate_only',true); %#ok<AGROW>
        result.candidate_count=result.candidate_count+1;
        if strcmp(cat,'grid_load'),result.grid_load_candidates=result.grid_load_candidates+1;end
        if strcmp(cat,'grid_branch_switch_or_line')
            result.grid_line_switch_candidates=result.grid_line_switch_candidates+1;
        end
        if strcmp(cat,'generator_pref_or_governor')
            result.generator_injection_candidates=result.generator_injection_candidates+1;
        end
    end
    result.source_blocks_scanned=numel(blocks);
    result.entries=entries;
    result.status='OFFICIAL_NATIVE_PHYSICAL_STRESS_CANDIDATES_INVENTORIED';
catch ME
    result.status='OFFICIAL_NATIVE_PHYSICAL_STRESS_DISCOVERY_FAILED';
    result.error_message=ME.message;result.error_id=ME.identifier;
end
fp=fullfile(res,'physical_disturbance_source_inventory.json');
fid=fopen(fp,'w');assert(fid>0);
fwrite(fid,jsonencode(result,'PrettyPrint',true),'char');
fwrite(fid,sprintf('\n'),'char');fclose(fid);
try,close_system('IEEE39BusSystem',0);catch,end
fprintf('Native IEEE39 physical disturbance candidates: %d; no independent safety certification.\\n',result.candidate_count);
end
