function aefc_ieee39_native_fault_recovery_strict_pilot_v1
% Run the ORIGINAL MathWorks IEEE39 Bus16_1 fault with STRICT fail-closed
% execution. Without a reviewed full-state certificate, all added Pref
% corrections must be rejected and the original generator governor paths
% must remain unchanged. Offline Simscape logs are evaluation-only; this is
% not a full-state safety certificate or a certified emergency-viability proof.
repo=pwd;protocolPath=fullfile(repo,'configs','ieee39_native_fault_recovery_protocol_r1.json');
p=jsondecode(fileread(protocolPath));
mapping=jsondecode(fileread(fullfile(repo,'results','ieee39_r2024b','interface_mapping.json')));
obsKeys=mapping.observation_generator_keys;
loc=jsondecode(fileread(fullfile(repo,'configs','ieee39_native_fault_recovery_protocol_r1_location_addendum.json')));
faultBus=loc.fault.physical_bus_section;faultLine=loc.fault.connected_transmission_line;
rp=p.preregistered_recovery_predicate;
busTol=double(rp.bus_voltage_relative_deviation_from_prefault_baseline_max);
speedBound=double(rp.generator_speed_max_abs_normalized_deviation);
holdSamples=double(rp.hold_samples);
cfg=jsondecode(fileread(fullfile(repo,'configs','ieee39_unpriv_r1.json')));
model=char(p.model);modelPath=fullfile(repo,'results','ieee39_r2024b',[model '.slx']);
if exist(modelPath,'file')~=2,aefc_ieee39_build_stress;end
load_system(modelPath);
ctrl=[model '/AEFC_NATIVE_CONTROLLER'];harness=[model '/AEFC_NATIVE_ATTACK_SOURCE'];
fault=[model '/Grid/Fault (Three-Phase)'];
assert(getSimParam(fault,'enable_temporal_fault')=='1','AEFC:FaultDisabled','Temporal fault must remain enabled');
faultStart=str2double(getSimParam(fault,'fault_start_time'));
faultDuration=str2double(getSimParam(fault,'fault_duration'));
faultType=str2double(getSimParam(fault,'fault_type_option'));
Rpn=str2double(getSimParam(fault,'R_pn_fault'));
Rng=str2double(getSimParam(fault,'R_ng_fault'));
assert(abs(faultStart-p.fault_parameters_frozen.fault_start_time_s)<1e-9);
assert(abs(faultDuration-p.fault_parameters_frozen.fault_duration_s)<1e-9);
assert(faultType==p.fault_parameters_frozen.fault_type_option);
assert(abs(Rpn-p.fault_parameters_frozen.R_pn_fault_ohm)<1e-12);
assert(abs(Rng-p.fault_parameters_frozen.R_ng_fault_ohm)<1e-12);
assert(strcmpi(char(get_param(fault,'MaskType')),'Fault (Three-Phase)'));
dt=double(p.sample_time_s);stop=double(p.stop_time_s);tq=(0:dt:stop)';
pre=(tq>=p.prefault_baseline_window_s(1) & tq<=p.prefault_baseline_window_s(2));
faultMask=(tq>=p.fault_window_s(1)-1e-10 & tq<=p.fault_window_s(2)+1e-10);
postStart=double(p.post_fault_recovery_start_s);
assert(sum(pre)>=10 && sum(faultMask)>=3);
outRoot=fullfile(repo,'results','ieee39_fault_recovery_r1','strict_pilot_v1');
if exist(outRoot,'dir')==7 && ~isempty(dir(fullfile(outRoot,'**','*.jsonl')))
 error('AEFC:Overwrite','Refuse to overwrite prior native fault trajectories');
end
if ~exist(outRoot,'dir'),mkdir(outRoot);end
methods=p.methods;codes=p.method_codes;seedList=double(p.pilot_seeds(:));
assert(numel(methods)==2 && numel(codes)==2 && numel(seedList)==2, ...
 'AEFC:PilotShape','Expected two methods and two scalar pilot seeds.');
assert(all(isfinite(seedList)) && numel(unique(seedList))==numel(seedList), ...
 'AEFC:PilotSeeds','Pilot seeds must be finite and unique.');
assert(any(strcmp(methods,'AEFC-Full')) && any(strcmp(methods,'Supervisor-only')), ...
 'AEFC:PilotMethods','Both preregistered comparison methods are required.');
rows=struct([]);n=0;
set_param(ctrl,'MethodCode','7','ExploratoryMode','false');
set_param(harness,'ScenarioCode','1','Seed','0','AttackScale','1','StressAmplitude','0');
% Simscape logging configuration is frozen before Fast Restart. The log
% name cannot be changed through SimulationInput once Fast Restart is active.
set_param(model,'SimscapeLogType','all','SimscapeLogName','AEFC_FAULT_SIMLOG');
try,set_param(model,'SimulationCommand','update');catch,end
try,set_param(model,'FastRestart','on');catch ME,rethrow(ME);end
for mi=1:numel(methods)
 method=methods{mi};mc=codes(mi);
 runDir=fullfile(outRoot,method);if ~exist(runDir,'dir'),mkdir(runDir);end
 for seedIndex=1:numel(seedList)
  seed=seedList(seedIndex);
  assert(isscalar(seed) && isfinite(seed),'AEFC:PilotSeed','Each run must use one scalar seed.');
  in=Simulink.SimulationInput(model);
  in=in.setBlockParameter(ctrl,'MethodCode',num2str(mc));
  in=in.setBlockParameter(ctrl,'ExploratoryMode','0');
  in=in.setBlockParameter(harness,'ScenarioCode','1');
  in=in.setBlockParameter(harness,'Seed',num2str(seed));
  in=in.setBlockParameter(harness,'AttackScale','1');
  in=in.setBlockParameter(harness,'StressAmplitude','0');
  in=in.setModelParameter('StopTime',num2str(stop,'%.17g'));
  in=in.setModelParameter('ReturnWorkspaceOutputs','on');
  out=sim(in);
  % Actual online four-speed input, ten independent physical speed outputs.
  obs=zeros(numel(tq),4);
  for q=1:4,obs(:,q)=sampleOutput(out,sprintf('AEFC_NATIVE_OBS_%02d',q),tq,1);end
  diagv=sampleOutput(out,'AEFC_DIAG',tq,16);
  ushield=sampleOutput(out,'AEFC_SHIELD_VECTOR',tq,4);
  upost=sampleOutput(out,'AEFC_POST_ATTACK_VECTOR',tq,4);
  assert(max(abs(upost),[],'all')<1e-12,'AEFC:FaultPilotUnexpectedPrefAttack', ...
      'The fault-only experiment must not inject a synthetic Pref attack.');
  basePref=zeros(numel(tq),4);delPref=zeros(numel(tq),4);
  for q=1:4
   basePref(:,q)=sampleOutput(out,sprintf('AEFC_NATIVE_PREF_BASE_%02d',q),tq,1);
   delPref(:,q)=sampleOutput(out,sprintf('AEFC_NATIVE_PREF_DELIVERED_%02d',q),tq,1);
  end
  prefResidual=delPref-basePref-ushield-upost;
  assert(max(abs(prefResidual),[],'all')<1e-6,'AEFC:FaultPrefInterposition','Native Pref identity failed');
  maxAddedPrefCorrection=max(abs(delPref-basePref),[],'all');
  assert(maxAddedPrefCorrection<1e-12,'AEFC:StrictFailClosed', ...
      'Strict mode must reject every added Pref correction when the native full-state certificate is absent.');
  gen=sampleOutput(out,'AEFC_NATIVE_GEN_ALL_10',tq,10);
  genBase=mean(gen(pre,:),1);
  genNormSigned=(gen-genBase)/double(rp.generator_speed_normalization_divisor_pu);
  genNormAbs=abs(genNormSigned);
  speedNorm=max(genNormAbs,[],2);
  % Native Simscape logging is an offline plant oracle, never an online
  % sensor supplied to the controller.
  logNode=[];
  try,logNode=out.get('AEFC_FAULT_SIMLOG');catch,end
  if ~isa(logNode,'simscape.logging.Node')
   logNode=[];try,logNode=simscape.logging.getSimulationLog(model);catch,end
  end
  assert(isa(logNode,'simscape.logging.Node'),'AEFC:FaultSimscapeLog','Missing original plant Simscape log');
  [busRows,branchRows,faultRows]=extractPhysicalLeaves(logNode,model);
  busIds=unique({busRows.logical_bus});
  sections=numel(busRows);
  assert(numel(busIds)==39,'AEFC:FaultBusCoverage','Expected 39 logical bus Vt channels; found %d',numel(busIds));
  assert(sections>=39,'AEFC:FaultBusSections','Expected at least 39 physical bus sections');
  busMap=struct('path',{},'logical_bus',{},'section',{},'unit',{});
  for bm=1:sections
   busMap(bm)=struct('path',busRows(bm).path,'logical_bus',busRows(bm).logical_bus, ...
       'section',busRows(bm).section,'unit',busRows(bm).unit); %#ok<AGROW>
  end
  busV=zeros(numel(tq),sections);busBase=zeros(1,sections);
  for q=1:sections
   [tt,vv]=normalizeLeaf(busRows(q).time,busRows(q).values);
   busV(:,q)=interp1(tt,vv,tq,'linear','extrap');
   busBase(q)=mean(busV(pre,q));
  end
  relBus=abs(busV-busBase)./max(abs(busBase),1e-6);
  busDev=max(relBus,[],2);
  bus16Idx=find(strcmp({busRows.logical_bus},'16'));
  assert(~isempty(bus16Idx),'AEFC:Bus16Missing','No physical voltage section for logical Bus16.');
  faultBusTokens=regexp(faultBus,'/Bus([0-9]+)_([0-9]+)$','tokens','once');
  assert(~isempty(faultBusTokens) && strcmp(faultBusTokens{1},'16'), ...
      'AEFC:Bus16FaultLocation','Frozen fault location is not a split Bus16 section.');
  faultedBus16Idx=find(strcmp({busRows.logical_bus},faultBusTokens{1}) & ...
      strcmp({busRows.section},faultBusTokens{2}));
  assert(numel(faultedBus16Idx)==1,'AEFC:Bus16FaultSection','Expected exactly one Bus16_1 voltage section.');
  bus16Rel=relBus(:,bus16Idx);
  bus16Dev=max(bus16Rel,[],2);
  faultedBus16Rel=relBus(:,faultedBus16Idx);
  busVoltageExposed=any(any(relBus(faultMask,:)>busTol+1e-9));
  generatorSpeedExposed=any(any(genNormAbs(faultMask,:)>speedBound+1e-9));
  bus16Exposed=any(any(bus16Rel(faultMask,:)>busTol+1e-9));
  faultedBus16Exposed=any(faultedBus16Rel(faultMask)>busTol+1e-9);
  exposed=busVoltageExposed || generatorSpeedExposed;
  recovered=false;recIdx=NaN;
  postCandidates=find(tq>=postStart-1e-10);
  for q=1:numel(postCandidates)
   i=postCandidates(q);j=i+holdSamples-1;
   if j<=numel(tq) && all(busDev(i:j)<=busTol+1e-9) && ...
        all(speedNorm(i:j)<=speedBound+1e-9)
      recovered=true;recIdx=i;break;
   end
  end
  if exposed && recovered,recTime=tq(recIdx)-postStart;else,recTime=NaN;end
  assert(~isempty(branchRows),'AEFC:BranchCurrentMissing', ...
      'No native line/transformer current series were extracted from the Simscape log.');
  faultLineParts=regexp(char(faultLine),'/([^/]+)$','tokens','once');
  assert(~isempty(faultLineParts),'AEFC:FaultLinePath','Configured adjacent-line path has no terminal component name.');
  faultLineComponent=faultLineParts{1};
  faultLineMatchKey=lower(regexprep(faultLineComponent,'[^A-Za-z0-9]',''));
  branchComponentKeys=cellfun(@(x) lower(regexprep(char(x),'[^A-Za-z0-9]','')), ...
      {branchRows.component},'UniformOutput',false);
  adjacentIdx=find(strcmp(branchComponentKeys,faultLineMatchKey));
  availableLineComponents=unique({branchRows.component});
  assert(numel(adjacentIdx)==3,'AEFC:Bus16AdjacentLineCurrent', ...
      ['Expected three native phase-current series for configured line "%s" ' ...
       '(normalized key "%s"); found %d. Available components: %s'], ...
      faultLineComponent,faultLineMatchKey,numel(adjacentIdx),strjoin(availableLineComponents,', '));
  adjacentPhaseLabels={branchRows(adjacentIdx).variable};
  expectedPhaseLabels={'inductor_a/i/amplitude','inductor_b/i/amplitude','inductor_c/i/amplitude'};
  assert(numel(unique(adjacentPhaseLabels))==3 && all(ismember(expectedPhaseLabels,adjacentPhaseLabels)), ...
      'AEFC:Bus16AdjacentLinePhases', ...
      'Adjacent-line current channels must contain exactly the native a/b/c inductor amplitude series.');
  assert(all(strcmp({branchRows(adjacentIdx).unit},'A')),'AEFC:Bus16AdjacentLineUnits', ...
      'Adjacent-line current channels must retain their native ampere units.');
  adjacentCurrent=zeros(numel(tq),numel(adjacentIdx));
  branchSummary=struct('path',{},'component',{},'variable',{},'unit',{}, ...
       'max_current_all',{},'max_current_fault',{},'max_current_prefault',{},'max_current_postfault',{});
  for q=1:numel(branchRows)
   [tt,vv]=normalizeLeaf(branchRows(q).time,branchRows(q).values);
   vq=interp1(tt,vv,tq,'linear','extrap');
   adjacentPosition=find(adjacentIdx==q,1);
   if ~isempty(adjacentPosition),adjacentCurrent(:,adjacentPosition)=vq;end
   branchSummary(q)=struct('path',branchRows(q).path,'component',branchRows(q).component, ...
       'variable',branchRows(q).variable,'unit',branchRows(q).unit, ...
       'max_current_all',max(abs(vq)), ...
       'max_current_fault',max(abs(vq(faultMask))), ...
       'max_current_prefault',max(abs(vq(pre))), ...
       'max_current_postfault',max(abs(vq(tq>=postStart))));
  end
  faultSummary=struct('path',{},'variable',{},'unit',{},'max_all',{},'max_fault_window',{});
  for q=1:numel(faultRows)
   [tt,vv]=normalizeLeaf(faultRows(q).time,faultRows(q).values);
   vq=interp1(tt,vv,tq,'linear','extrap');
   faultSummary(q)=struct('path',faultRows(q).path,'variable',faultRows(q).variable, ...
      'unit',faultRows(q).unit,'max_all',max(abs(vq)), ...
      'max_fault_window',max(abs(vq(faultMask))));
  end
  maxAdjacentFault=max(abs(adjacentCurrent(faultMask,:)),[],'all');
  maxAdjacentPref=max(abs(adjacentCurrent(pre,:)),[],'all');
  maxAdjacentPost=max(abs(adjacentCurrent(tq>=postStart,:)),[],'all');
  faultCurrentMax=0;
  if ~isempty(faultSummary),faultCurrentMax=max([faultSummary.max_fault_window]);end
  n=n+1;rows(n).method=method;rows(n).seed=seed;rows(n).fault_start_s=faultStart;
  rows(n).fault_duration_s=faultDuration;rows(n).bus_logical_ids=numel(busIds);
  rows(n).bus_physical_sections=sections;rows(n).branch_current_series=numel(branchRows);
  rows(n).fault_current_series=numel(faultRows);rows(n).fault_current_peak=faultCurrentMax;
  rows(n).max_bus_relative_deviation_during_fault=max(busDev(faultMask));
  rows(n).max_speed_normalized_during_fault=max(speedNorm(faultMask));
  rows(n).max_bus16_relative_deviation_during_fault=max(bus16Dev(faultMask));
  rows(n).max_faulted_bus16_1_relative_deviation_during_fault=max(faultedBus16Rel(faultMask));
  rows(n).bus16_exposed_during_fault=double(bus16Exposed);
  rows(n).faulted_bus16_1_exposed_during_fault=double(faultedBus16Exposed);
  rows(n).bus_voltage_exposed_during_fault=double(busVoltageExposed);
  rows(n).generator_speed_exposed_during_fault=double(generatorSpeedExposed);
  rows(n).bus16_physical_sections=numel(bus16Idx);
  rows(n).B16_B17_phase_current_series=numel(adjacentIdx);
  rows(n).adjacent_line_simscape_component=branchRows(adjacentIdx(1)).component;
  rows(n).adjacent_line_match_key=faultLineMatchKey;
  rows(n).max_B16_B17_current_A_during_fault=maxAdjacentFault;
  rows(n).max_B16_B17_current_A_prefault=maxAdjacentPref;
  rows(n).max_B16_B17_current_A_postfault=maxAdjacentPost;
  rows(n).max_generator_speed_deviation_pu_during_fault=max(abs(gen(faultMask,:)-genBase),[],'all');
  rows(n).generator_speed_channels=size(gen,2);
  rows(n).max_bus_relative_deviation_all=max(busDev);
  rows(n).max_speed_normalized_all=max(speedNorm);
  rows(n).exposed_during_fault=double(exposed);
  rows(n).recovered_after_fault=double(exposed && recovered);
  rows(n).recovery_time_s=recTime;
  rows(n).right_censored=double(exposed && ~recovered);
  rows(n).gate_closed_samples=sum(diagv(:,3)<0.5);
  rows(n).adaptation_accepted_samples=sum(diagv(:,10)>0.5);
  rows(n).gate_authorized_samples=sum(diagv(:,3)>0.5);
  rows(n).execution_released_samples=sum(diagv(:,14)>0.5);
  rows(n).backup_action_used_samples=sum(diagv(:,13)>0.5);
  rows(n).full_state_certified_samples=sum(diagv(:,12)>0.5);
  rows(n).proxy_contract_pass_samples=sum(diagv(:,15)>0.5);
  rows(n).max_pref_interposition_residual=max(abs(prefResidual),[],'all');
  rows(n).max_added_pref_correction=maxAddedPrefCorrection;
  rows(n).full_network_safety_certified=0;
  % Preserve bus-voltage, all-speed and controller time series for independent
  % post-run audit; branch-current series retained as per-branch envelopes.
  tracePath=fullfile(runDir,sprintf('seed_%02d.jsonl',seed));
  fid=fopen(tracePath,'w');assert(fid>0);c=onCleanup(@()fclose(fid)); %#ok<NASGU>
  for k=1:numel(tq)
   rec=struct('time',tq(k),'online_observations',obs(k,:), ...
     'bus_vt_sections',busV(k,:), ...
     'bus_relative_max_deviation',busDev(k), ...
     'bus16_voltage_sections',busV(k,bus16Idx), ...
     'bus16_relative_deviation_sections',bus16Rel(k,:), ...
     'faulted_bus16_1_voltage',busV(k,faultedBus16Idx), ...
     'faulted_bus16_1_relative_deviation',faultedBus16Rel(k), ...
     'adjacent_B16_B17_current_A',adjacentCurrent(k,:), ...
     'all_ten_generator_speed',gen(k,:), ...
     'all_ten_speed_normalized',speedNorm(k), ...
     'all_ten_speed_normalized_signed',genNormSigned(k,:), ...
     'all_ten_speed_abs_normalized',genNormAbs(k,:), ...
     'fault_active_window',logical(faultMask(k)), ...
     'recovery_set_satisfied',logical(busDev(k)<=busTol && ...
       speedNorm(k)<=speedBound), ...
     'trust',diagv(k,1),'risk',diagv(k,2),'gate_allowed',logical(diagv(k,3)>0.5), ...
     'proxy_intervention',diagv(k,6),'proxy_status',diagv(k,8), ...
     'adaptation_accepted',logical(diagv(k,10)>0.5), ...
      'execution_released',logical(diagv(k,14)>0.5), ...
      'backup_action_used',logical(diagv(k,13)>0.5), ...
      'full_state_certified',logical(diagv(k,12)>0.5), ...
      'proxy_contract_pass',logical(diagv(k,15)>0.5), ...
      'method_code',diagv(k,16), ...
     'shield_action',ushield(k,:),'post_shield_attack',upost(k,:), ...
     'original_governor_pref',basePref(k,:),'delivered_pref',delPref(k,:));
   fwrite(fid,jsonencode(rec),'char');fwrite(fid,sprintf('\n'),'char');
  end
  clear c; % onCleanup closes the JSONL trace exactly once
  saveSummary(fullfile(runDir,sprintf('seed_%02d.bus-map.json',seed)),busMap);
  saveSummary(fullfile(runDir,sprintf('seed_%02d.branch-current.json',seed)),branchSummary);
  saveSummary(fullfile(runDir,sprintf('seed_%02d.fault-current.json',seed)),faultSummary);
  bus16LineDiag=struct('logical_bus_id',16,'physical_sections',busMap(bus16Idx), ...
      'faulted_physical_section',faultBus,'faulted_section_path',busRows(faultedBus16Idx).path, ...
      'time_s',tq,'bus16_voltage_pu',busV(:,bus16Idx), ...
      'bus16_relative_deviation',bus16Rel,'faulted_bus16_1_voltage_pu',busV(:,faultedBus16Idx), ...
      'faulted_bus16_1_relative_deviation',faultedBus16Rel, ...
      'adjacent_line',faultLine,'adjacent_line_simscape_component',branchRows(adjacentIdx(1)).component, ...
      'adjacent_line_match_key',faultLineMatchKey, ...
      'adjacent_line_current_variables',{adjacentPhaseLabels}, ...
      'adjacent_line_current_A',adjacentCurrent, ...
      'adjacent_line_current_max_abs_A_during_fault_by_phase',max(abs(adjacentCurrent(faultMask,:)),[],1), ...
      'adjacent_line_current_max_abs_A_prefault_by_phase',max(abs(adjacentCurrent(pre,:)),[],1), ...
      'adjacent_line_current_max_abs_A_postfault_by_phase',max(abs(adjacentCurrent(tq>=postStart,:)),[],1));
  saveSummary(fullfile(runDir,sprintf('seed_%02d.bus16-adjacent-line.json',seed)),bus16LineDiag);
  genSpeedDiag=struct('generator_index',1:10,'time_s',tq,'generator_speed_pu',gen, ...
      'prefault_baseline_speed_pu',genBase,'speed_normalized_signed',genNormSigned, ...
      'speed_normalized_abs',genNormAbs, ...
      'max_abs_deviation_pu_during_fault_by_generator',max(abs(gen(faultMask,:)-genBase),[],1), ...
      'max_abs_normalized_deviation_during_fault_by_generator',max(genNormAbs(faultMask,:),[],1));
  saveSummary(fullfile(runDir,sprintf('seed_%02d.generator-speed.json',seed)),genSpeedDiag);
  saveSummary(fullfile(runDir,sprintf('seed_%02d.summary.json',seed)),rows(n));
 end
end
try,set_param(model,'FastRestart','off');catch,end
T=struct2table(rows);writetable(T,fullfile(outRoot,'summary.csv'));
manifest=struct('protocol',p,'execution_mode','strict_fail_closed', ...
 'exploratory_mode',false, ...
 'backend','MATLAB R2024b original IEEE39-derived native Simulink/Simscape', ...
 'model',model,'fault_parameters_verified_at_runtime',true,'rows',height(T), ...
 'methods',{methods},'seeds',seedList(:)', ...
 'online_observation_generator_keys',{obsKeys}, ...
 'bus16_logical_id',16,'bus16_physical_section_count',numel(bus16Idx), ...
 'faulted_bus16_physical_section',faultBus, ...
 'adjacent_line',faultLine,'adjacent_line_simscape_component',branchRows(adjacentIdx(1)).component, ...
 'adjacent_line_match_key',faultLineMatchKey, ...
 'adjacent_line_current_phase_variables',{adjacentPhaseLabels}, ...
 'generator_speed_channels',10, ...
 'verified_fault_bus_section',faultBus,'verified_adjacent_line',faultLine, ...
 'full_network_safety_certified',false, ...
 'added_pref_correction_expected',false, ...
 'original_governor_reference_retained',true, ...
 'independent_governor_viability_certified',false, ...
 'offline_simscape_oracle_only',true,'online_controller_inputs',4,'bus_voltage_section_map_saved_per_episode',true, ...
 'offline_generator_speed_channels',10,'branch_current_limits_validated',false, ...
 'DAE_reachability_verified',false,'intersample_tube_verified',false);
saveSummary(fullfile(outRoot,'manifest.json'),manifest);
pairExposure=struct('seed',{},'AEFC_Full_exposed',{},'Supervisor_only_exposed',{}, ...
    'jointly_exposed',{},'AEFC_Full_recovered',{},'Supervisor_only_recovered',{});
for seedIndex=1:numel(seedList)
 seed=seedList(seedIndex);
 fullIdx=find(strcmp({rows.method},'AEFC-Full') & [rows.seed]==seed,1);
 supervisorIdx=find(strcmp({rows.method},'Supervisor-only') & [rows.seed]==seed,1);
 assert(~isempty(fullIdx) && ~isempty(supervisorIdx),'AEFC:PilotPairMissing', ...
    'A same-seed AEFC-Full/Supervisor-only pair is missing.');
 fullExposed=logical(rows(fullIdx).exposed_during_fault);
 supervisorExposed=logical(rows(supervisorIdx).exposed_during_fault);
 pairExposure(seedIndex)=struct('seed',seed,'AEFC_Full_exposed',fullExposed, ...
    'Supervisor_only_exposed',supervisorExposed,'jointly_exposed',fullExposed && supervisorExposed, ...
    'AEFC_Full_recovered',logical(rows(fullIdx).recovered_after_fault), ...
    'Supervisor_only_recovered',logical(rows(supervisorIdx).recovered_after_fault));
end
allNoAddedPref=all([rows.max_added_pref_correction]<1e-12);
allNoRelease=all([rows.execution_released_samples]==0);
allNoBackupAction=all([rows.backup_action_used_samples]==0);
allCommonExposure=all([pairExposure.jointly_exposed]);
allRecovered=all([pairExposure.AEFC_Full_recovered] & [pairExposure.Supervisor_only_recovered]);
strictGate=struct('criterion','Strict execution must fail closed without the reviewed full-state certificate; original governor reference remains, and paired fault episodes are audited for common exposure and sampled post-fault recovery.', ...
 'passed',allNoAddedPref && allNoRelease && allNoBackupAction && allCommonExposure && allRecovered, ...
 'all_added_pref_corrections_zero',allNoAddedPref, ...
 'all_execution_releases_zero',allNoRelease, ...
 'all_backup_actions_zero',allNoBackupAction, ...
 'all_pairs_common_exposed',allCommonExposure, ...
 'all_pairs_recovered_after_fault',allRecovered, ...
 'paired_seed_exposure',pairExposure, ...
 'formal_confirmatory_seeds',double(p.confirmatory_seeds(:)'), ...
 'confirmatory_experiment_started',false,'thresholds_changed',false, ...
 'fault_parameters_changed',false,'pilot_episode_count',height(T), ...
 'full_network_safety_certified',false, ...
 'interpretation','Zero added Pref correction and unchanged native governor reference are empirical sampled facts; this does not certify continuous-time backup viability or complete IEEE39 safety.');
saveSummary(fullfile(outRoot,'strict_refusal_gate.json'),strictGate);
close_system(model,0);
end


function [bus,branch,fault]=extractPhysicalLeaves(root,model)
bus=struct('path',{},'logical_bus',{},'section',{},'unit',{},'time',{},'values',{});
branch=struct('path',{},'component',{},'variable',{},'unit',{},'time',{},'values',{});
fault=struct('path',{},'variable',{},'unit',{},'time',{},'values',{});
stack={root};paths={model};head=1;visited=0;
while head<=numel(stack) && visited<80000
 nd=stack{head};parent=paths{head};head=head+1;visited=visited+1;
 pp=properties(nd);
 for j=1:numel(pp)
  key=pp{j};child=[];
  try,child=nd.(key);catch,end
  if isa(child,'simscape.logging.Node')
   stack{end+1}=child;paths{end+1}=[parent '/' key]; %#ok<AGROW>
  elseif isa(child,'simscape.logging.Series')
   if ~contains(parent,[model '/Grid/']),continue;end
   unit='';t=[];v=[];
   try
    unit=char(child.unit);t=double(time(child));v=double(values(child));
   catch
    continue
   end
   if isempty(t)||isempty(v),continue;end
   % Capture only fault-block current series; voltage variables are not
   % combined with current values.
   if contains(parent,'Fault_Three_Phase')
    var=regexp(parent,'/([^/]+)$','tokens','once');
    if ~isempty(var) && any(strcmp(var{1},{'I','i','i1','i2','i_a','i_b','i_c'})) ...
        && strcmp(unit,'A')
     fault(end+1)=struct('path',[parent '/' key],'variable',var{1}, ...
       'unit',unit,'time',t,'values',v); %#ok<AGROW>
    end
    continue
   end
   % Original model logs each physical bus section as BusNN or BusNN_1.
   tok=regexp(parent,'/Grid/Bus([^/]+)/Vt$','tokens','once');
   if ~isempty(tok)
    parts=strsplit(tok{1},'_');logicalBus=parts{1};section='';
    if numel(parts)>1,section=parts{2};end
    if strcmp(unit,'1')
     bus(end+1)=struct('path',[parent '/' key],'logical_bus',logicalBus, ...
       'section',section,'unit',unit,'time',t,'values',v); %#ok<AGROW>
    end
    continue
   end
   % The IEEE39 native line model exposes three phase currents through
   % transmission_line/inductor_{a,b,c}/i. Do not count shunt capacitor
   % currents as the series branch current.
   tok=regexp(parent,'/Grid/([^/]+)/transmission_line/(inductor_[abc])/i/amplitude$','tokens','once');
   if ~isempty(tok) && strcmp(unit,'A')
    branch(end+1)=struct('path',[parent '/' key],'component',tok{1}, ...
       'variable',[tok{2} '/i/amplitude'],'unit',unit,'time',t,'values',v); %#ok<AGROW>
    continue
   end
   % Both transformer winding currents are logged natively in amperes.
   tok=regexp(parent,'/Grid/(TF_[^/]+)/(i1|i2)$','tokens','once');
   if ~isempty(tok) && strcmp(unit,'A')
    branch(end+1)=struct('path',[parent '/' key],'component',tok{1}, ...
       'variable',tok{2},'unit',unit,'time',t,'values',v); %#ok<AGROW>
   end
  end
 end
end
end

function [t,v]=normalizeLeaf(t,v)
t=double(t(:));v=double(v);
if ~isreal(v),v=abs(v);end
if numel(v)==numel(t),v=v(:);
else
 sz=size(v);td=find(sz==numel(t),1,'last');
 assert(~isempty(td),'AEFC:LeafTimeDimension','Cannot align Simscape series values and time.');
 perm=[td setdiff(1:ndims(v),td,'stable')];v=permute(v,perm);
 v=reshape(v,numel(t),[]);
 v=max(abs(v),[],2);
end
[t,ia]=unique(t,'stable');v=v(ia,:);
if size(v,2)>1,v=max(abs(v),[],2);end
assert(numel(t)>=2 && numel(v)==numel(t) && all(isfinite(t)) && all(isfinite(v)), ...
 'AEFC:LeafSeries','Invalid Simscape physical series.');
end

function X=sampleOutput(out,name,tq,dim)
try,v=out.get(name);catch,v=[];end
assert(~isempty(v),'AEFC:OutputMissing','Missing output %s',name);
[t,d]=extractSeries(v);t=double(t(:));d=double(d);
if ~isreal(d),d=abs(d);end
d=normalizeTimeMajor(d,numel(t),dim,name);[t,ia]=unique(t,'stable');d=d(ia,:);
if numel(t)==1 && startsWith(name,'AEFC_NATIVE_PREF_BASE_')
 assert(abs(t(1)-tq(1))<1e-8 && all(isfinite(d),'all'), ...
     'AEFC:OriginalPrefSingleSample','Single original Pref sample invalid');
 X=repmat(d(1,1:dim),numel(tq),1);return;
end
assert(numel(t)>=2,'AEFC:OutputSamples','Too few samples for %s',name);
X=interp1(t,d(:,1:dim),tq,'nearest','extrap');
assert(isequal(size(X),[numel(tq),dim])&&all(isfinite(X),'all'));
end
function d=normalizeTimeMajor(d,nT,dim,name)
if isvector(d)&&dim==1,assert(numel(d)==nT);d=d(:);return;end
assert(numel(d)==nT*dim,'AEFC:OutputDimension','Bad shape %s',name);
sz=size(d);td=find(sz==nT,1,'last');assert(~isempty(td));
d=permute(d,[td setdiff(1:ndims(d),td,'stable')]);d=reshape(d,nT,[]);
assert(size(d,2)==dim);
end
function [t,d]=extractSeries(v)
if isa(v,'timeseries'),t=v.Time;d=v.Data;
elseif isa(v,'Simulink.SimulationData.Dataset'),el=v.getElement(1);[t,d]=extractSeries(el.Values);
elseif isa(v,'Simulink.SimulationData.Signal'),[t,d]=extractSeries(v.Values);
elseif isstruct(v)&&isfield(v,'time')&&isfield(v,'signals'),t=v.time;d=v.signals.values;
else,try,t=v.Time;d=v.Data;catch,error('AEFC:OutputFormat','Unsupported %s',class(v));end,end
end
function s=getSimParam(p,n)
s=char(get_param(p,n));
end
function saveSummary(path,obj)
fid=fopen(path,'w');assert(fid>0);c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(obj,'PrettyPrint',true),'char');fwrite(fid,sprintf('\n'),'char');
end
