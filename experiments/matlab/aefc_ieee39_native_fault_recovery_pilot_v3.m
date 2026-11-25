function aefc_ieee39_native_fault_recovery_pilot_v3
% Run the ORIGINAL MathWorks IEEE39 three-phase fault (5.0s, 0.1s) without
% synthetic cyber/Pref attacks. Compare the four-dimensional AEFC mechanism
% prototype with Supervisor-only. Offline Simscape logs expose 39 logical
% bus Vt channels and branch currents for post-hoc physical evaluation only.
repo=pwd;protocolPath=fullfile(repo,'configs','ieee39_native_fault_recovery_protocol_r1.json');
p=jsondecode(fileread(protocolPath));
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
outRoot=fullfile(repo,'results','ieee39_fault_recovery_r1','pilot_v3');
if exist(outRoot,'dir')==7 && ~isempty(dir(fullfile(outRoot,'**','*.jsonl')))
 error('AEFC:Overwrite','Refuse to overwrite prior native fault trajectories');
end
if ~exist(outRoot,'dir'),mkdir(outRoot);end
methods=p.methods;codes=p.method_codes;seeds=p.pilot_seeds;
rows=struct([]);n=0;
set_param(ctrl,'MethodCode','7','ExploratoryMode','true');
set_param(harness,'ScenarioCode','1','Seed','0','AttackScale','1','StressAmplitude','0');
try,set_param(model,'SimulationCommand','update');catch,end
try,set_param(model,'FastRestart','on');catch ME,rethrow(ME);end
for mi=1:numel(methods)
 method=methods{mi};mc=codes(mi);
 runDir=fullfile(outRoot,method);if ~exist(runDir,'dir'),mkdir(runDir);end
 for seed=seeds
  in=Simulink.SimulationInput(model);
  in=in.setBlockParameter(ctrl,'MethodCode',num2str(mc), ...
       'ExploratoryMode','true');
  in=in.setBlockParameter(harness,'ScenarioCode','1','Seed',num2str(seed), ...
       'AttackScale','1','StressAmplitude','0');
  in=in.setModelParameter('StopTime',num2str(stop,'%.17g'), ...
       'ReturnWorkspaceOutputs','on','SimscapeLogType','all', ...
       'SimscapeLogName','AEFC_FAULT_SIMLOG');
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
  gen=sampleOutput(out,'AEFC_NATIVE_GEN_ALL_10',tq,10);
  genBase=mean(gen(pre,:),1);
  speedNorm=max(abs((gen-genBase)/0.02),[],2);
  % Native Simscape logging is an offline plant oracle, never an online
  % sensor supplied to the controller.
  logNode=[];
  try,logNode=out.get('AEFC_FAULT_SIMLOG');catch,end
  if isempty(logNode),try,logNode=simscape.logging.getSimulationLog(model);catch,end,end
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
  exposed=any(busDev(faultMask)>p.bus_voltage_recovery_tolerance+1e-9 | ...
              speedNorm(faultMask)>p.generator_speed_recovery_bound+1e-9);
  recovered=false;recIdx=NaN;
  postCandidates=find(tq>=postStart-1e-10);
  for q=1:numel(postCandidates)
   i=postCandidates(q);j=i+p.hold_samples-1;
   if j<=numel(tq) && all(busDev(i:j)<=p.bus_voltage_recovery_tolerance+1e-9) && ...
        all(speedNorm(i:j)<=p.generator_speed_recovery_bound+1e-9)
      recovered=true;recIdx=i;break;
   end
  end
  if recovered,recTime=tq(recIdx)-postStart;else,recTime=NaN;end
  branchSummary=struct('path',{},'component',{},'variable',{},'unit',{}, ...
       'max_current_all',{},'max_current_fault',{},'max_current_prefault',{},'max_current_postfault',{});
  for q=1:numel(branchRows)
   [tt,vv]=normalizeLeaf(branchRows(q).time,branchRows(q).values);
   vq=interp1(tt,vv,tq,'linear','extrap');
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
  faultCurrentMax=0;
  if ~isempty(faultSummary),faultCurrentMax=max([faultSummary.max_fault_window]);end
  n=n+1;rows(n).method=method;rows(n).seed=seed;rows(n).fault_start_s=faultStart;
  rows(n).fault_duration_s=faultDuration;rows(n).bus_logical_ids=numel(busIds);
  rows(n).bus_physical_sections=sections;rows(n).branch_current_series=numel(branchRows);
  rows(n).fault_current_series=numel(faultRows);rows(n).fault_current_peak=faultCurrentMax;
  rows(n).max_bus_relative_deviation_during_fault=max(busDev(faultMask));
  rows(n).max_speed_normalized_during_fault=max(speedNorm(faultMask));
  rows(n).max_bus_relative_deviation_all=max(busDev);
  rows(n).max_speed_normalized_all=max(speedNorm);
  rows(n).exposed_during_fault=double(exposed);
  rows(n).recovered_after_fault=double(exposed && recovered);
  rows(n).recovery_time_s=recTime;
  rows(n).right_censored=double(exposed && ~recovered);
  rows(n).gate_closed_samples=sum(diagv(:,3)<0.5);
  rows(n).deployment_accepted_samples=sum(diagv(:,10)>0.5);
  rows(n).proxy_release_samples=sum(diagv(:,14)>0.5);
  rows(n).max_pref_interposition_residual=max(abs(prefResidual),[],'all');
  rows(n).full_network_safety_certified=0;
  % Preserve bus-voltage, all-speed and controller time series for independent
  % post-run audit; branch-current series retained as per-branch envelopes.
  tracePath=fullfile(runDir,sprintf('seed_%02d.jsonl',seed));
  fid=fopen(tracePath,'w');assert(fid>0);c=onCleanup(@()fclose(fid)); %#ok<NASGU>
  for k=1:numel(tq)
   rec=struct('time',tq(k),'bus_vt_sections',busV(k,:), ...
     'bus_relative_max_deviation',busDev(k),'all_ten_generator_speed',gen(k,:), ...
     'all_ten_speed_normalized',speedNorm(k), ...
     'fault_active_window',logical(faultMask(k)), ...
     'recovery_set_satisfied',logical(busDev(k)<=p.bus_voltage_recovery_tolerance && ...
       speedNorm(k)<=p.generator_speed_recovery_bound), ...
     'trust',diagv(k,1),'risk',diagv(k,2),'gate_allowed',logical(diagv(k,3)>0.5), ...
     'proxy_intervention',diagv(k,6),'proxy_status',diagv(k,8), ...
     'deployment_accepted',logical(diagv(k,10)>0.5), ...
     'shield_action',ushield(k,:),'post_shield_attack',upost(k,:), ...
     'original_governor_pref',basePref(k,:),'delivered_pref',delPref(k,:));
   fwrite(fid,jsonencode(rec),'char');fwrite(fid,sprintf('\n'),'char');
  end
  clear c; % onCleanup closes the JSONL trace exactly once
  saveSummary(fullfile(runDir,sprintf('seed_%02d.bus-map.json',seed)),busMap);
  saveSummary(fullfile(runDir,sprintf('seed_%02d.branch-current.json',seed)),branchSummary);
  saveSummary(fullfile(runDir,sprintf('seed_%02d.fault-current.json',seed)),faultSummary);
  saveSummary(fullfile(runDir,sprintf('seed_%02d.summary.json',seed)),rows(n));
 end
end
try,set_param(model,'FastRestart','off');catch,end
T=struct2table(rows);writetable(T,fullfile(outRoot,'summary.csv'));
manifest=struct('protocol',p,'backend','MATLAB R2024b original IEEE39-derived native Simulink/Simscape', ...
 'model',model,'fault_parameters_verified_at_runtime',true,'rows',height(T), ...
 'methods',{methods},'seeds',seeds,'full_network_safety_certified',false, ...
 'offline_simscape_oracle_only',true,'online_controller_inputs',4,'bus_voltage_section_map_saved_per_episode',true, ...
 'offline_generator_speed_channels',10,'branch_current_limits_validated',false, ...
 'DAE_reachability_verified',false,'intersample_tube_verified',false);
saveSummary(fullfile(outRoot,'manifest.json'),manifest);
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
