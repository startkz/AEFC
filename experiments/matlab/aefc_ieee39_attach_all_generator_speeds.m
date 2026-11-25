function nSensors = aefc_ieee39_attach_all_generator_speeds(model)
% Instrument all TEN existing physical rotor-speed outputs in the OFFICIAL
% IEEE39 native model. Signals are legitimate generator-local measurements,
% not hidden Simulink xout/oracle states. Their integrity still needs a
% separate physical trust proof; they do not cover network algebraic states.
%
% Adds top-level To Workspace: AEFC_NATIVE_GEN_ALL_10 (10-vector).
assert(bdIsLoaded(model),'AEFC:AllGenModel','Model must be loaded before sensor attachment');
blocks=find_system(model,'LookUnderMasks','all','FollowLinks','on','Type','Block');
src=cell(10,1);keys=cell(10,1);
for i=1:10
    key=sprintf('Gen%d@Bus',i);
    candidates={};
    for j=1:numel(blocks)
        p=blocks{j};
        if ~contains(p,['/Generators/' key]) || ~contains(p,'Governor'),continue;end
        name='';
        try,name=char(get_param(p,'Name'));catch,end
        if strcmp(name,'w')
            candidates{end+1}=p;
        end
    end
    assert(~isempty(candidates),'AEFC:AllGenMissing', ...
        'No physical generator speed signal found for %s',key);
    % Prefer exactly matching the deployed four generator /Governor/w path.
    score=zeros(numel(candidates),1);
    for j=1:numel(candidates)
        score(j)=double(endsWith(candidates{j},'/w'))*100 ...
                  +double(contains(candidates{j},'Prime Mover'))*10 ...
                  -double(contains(candidates{j},'Reference'))*100;
    end
    [~,best]=max(score);
    src{i}=candidates{best};
    tk=regexp(src{i},'Generators/(Gen[0-9]+@Bus[0-9]+)/','tokens','once');
    assert(~isempty(tk),'AEFC:GenKey','Cannot recover exact Gen/Bus key');
    keys{i}=tk{1};
end
assert(numel(unique(keys))==10,'AEFC:AllGenDuplicate','Rotor-speed sensor mapping must cover 10 distinct machines');
mux=[model '/AEFC_GENALL_MUX'];
add_block('simulink/Signal Routing/Mux',mux,'Inputs','10', ...
    'Position',[730 70 736 380]);
mph=get_param(mux,'PortHandles');
for i=1:10
    p=src{i};parent=get_param(p,'Parent');
    makeEditable(parent);
    ph=get_param(p,'PortHandles');
    assert(~isempty(ph.Outport),'AEFC:AllGenPort','No speed source Outport');
    tag=sprintf('AEFC_GENALL_TAG_%02d',i);
    goto=[parent sprintf('/AEFC_GENALL_GOTO_%02d',i)];
    add_block('simulink/Signal Routing/Goto',goto,'GotoTag',tag, ...
        'TagVisibility','global','Position',[50 400+25*i 145 420+25*i]);
    gph=get_param(goto,'PortHandles');
    add_line(parent,ph.Outport(1),gph.Inport(1),'autorouting','on');
    from=[model sprintf('/AEFC_GENALL_FROM_%02d',i)];
    add_block('simulink/Signal Routing/From',from,'GotoTag',tag, ...
        'Position',[640 80+27*i 715 100+27*i]);
    fph=get_param(from,'PortHandles');
    add_line(model,fph.Outport(1),mph.Inport(i),'autorouting','on');
end
sink=[model '/AEFC_NATIVE_GEN_ALL_10_TOWS'];
add_block('simulink/Sinks/To Workspace',sink, ...
    'VariableName','AEFC_NATIVE_GEN_ALL_10','SaveFormat','Timeseries',...
    'Position',[770 425 920 455]);
sph=get_param(sink,'PortHandles');
add_line(model,mph.Outport(1),sph.Inport(1),'autorouting','on');
nSensors=10;
end
function makeEditable(block)
try
    st=get_param(block,'LinkStatus');
    if strcmp(st,'resolved'),set_param(block,'LinkStatus','inactive');end
catch
end
end
