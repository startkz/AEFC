function aefc_ieee39_stress_recovery(mode)
% NEW preregistered physical pressure evidence, new results directory, no original P0 source overwritten.
% Persistent Pref attacks above 0.024 are explicitly OUTSIDE original certified bound.
% This does not prove full IEEE39 electrical network safety or FL training gains.
% Supported "smoke", "pilot", "strict"; all report four-speed proxy scope.
if nargin<1,mode='stress_pilot';end
assert(any(strcmp(mode,{'stress_pilot','stress_six','stress_strict'})), ...
    'AEFC:StressMode','Unrecognized separately preregistered pressure protocol');
repo=pwd;cfgPath=fullfile(repo,'configs','ieee39_unpriv_r1.json');
cfg=jsondecode(fileread(cfgPath));
stressPath=fullfile(repo,'configs','ieee39_stress_protocol_r1.json');
stressCfg=jsondecode(fileread(stressPath));
mapping=jsondecode(fileread(fullfile(repo,cfg.mapping_path)));
assert(mapping.validated && strcmp(mapping.selection_policy,'paired-generator-physical-speed-v2'), ...
    'AEFC:StressMapping','Require original causal native 4 Pref/4-speed mapping');
model=char(stressCfg.model);
modelPath=fullfile(repo,'results','ieee39_r2024b',[model '.slx']);
if exist(modelPath,'file')~=2,aefc_ieee39_build_stress;end
load_system(modelPath);
try,set_param(model,'ReturnWorkspaceOutputs','on');catch,end
try,set_param(model,'SignalLogging','off');catch,end
ctrl=[model '/AEFC_NATIVE_CONTROLLER'];
harness=[model '/AEFC_NATIVE_ATTACK_SOURCE'];
if strcmp(mode,'stress_pilot')
    methods={'AEFC-Full','Supervisor-only'};mCodes=[7 8];
    scenarios={'physical','joint'};scCodes=[3 4];
    seeds=0:1;scales=[0.024 0.06 0.12 0.24];
elseif strcmp(mode,'stress_strict')
    methods={'AEFC-Full','Supervisor-only'};mCodes=[7 8];
    scenarios={'physical','joint'};scCodes=[3 4];
    seeds=0:1;scales=[0.024 0.12 0.24];
else
    methods={'AEFC-Full','Supervisor-only','RobustAgg', ...
             'AEFC-no-PATBU','AEFC-no-Gate','AEFC-no-TGOPA'};
    mCodes=[7 8 2 3 4 5];
    scenarios={'physical','joint'};scCodes=[3 4];
    seeds=80:89;scales=[0.06 0.12 0.24];
end
strictMode=strcmp(mode,'stress_strict');
dt=double(cfg.sample_time);stopTime=double(cfg.stop_time);
tq=(0:dt:stopTime)';
center=double(mapping.baseline_observation(:));
scale=deriveScale(mapping.observation_edges,center);
outRoot=fullfile(repo,'results','ieee39_stress_r1',mode);
if exist(outRoot,'dir')==7 && ~isempty(dir(fullfile(outRoot,'**','*.jsonl')))
    error('AEFC:Overwrite','Refuse to overwrite prior raw unprivileged trajectories');
end
if ~exist(outRoot,'dir'),mkdir(outRoot);end
commitSha=getenv('GITHUB_SHA');if isempty(commitSha),commitSha='LOCAL';end
configId=sha16(cfgPath);stressId=sha16(stressPath);
rows=struct([]);counter=0;
set_param(ctrl,'MethodCode','7','ExploratoryMode',mat2str(~strictMode));
set_param(harness,'ScenarioCode','1','Seed','0','AttackScale','1');
try,set_param(model,'SimulationCommand','update');catch,end
fastRestart=false;
try,set_param(model,'FastRestart','on');fastRestart=true;catch,end
assert(fastRestart,'AEFC:FastRestart','Native experiment requires Fast Restart');
for ai=1:numel(scales)
    attackScale=scales(ai);
    % Separate noncertified exploratory physical stress envelope. The
    % original native 0.024 contract is NOT applied to higher pressures.
    assert(any(abs(attackScale-[0.024 0.06 0.12 0.24])<1e-12) && ...
        attackScale<=stressCfg.hard_constraints.this_stress_max+1e-12, ...
        'AEFC:StressBudget','Unregistered exploratory stress intensity');
    for si=1:numel(scenarios)
        for mi=1:numel(methods)
            method=methods{mi};scenario=scenarios{si};
            runDir=fullfile(outRoot,sprintf('scale_%g',attackScale),scenario,method);
            if ~exist(runDir,'dir'),mkdir(runDir);end
            for seed=seeds
                in=Simulink.SimulationInput(model);
                in=in.setBlockParameter(ctrl,'MethodCode',num2str(mCodes(mi)));
                in=in.setBlockParameter(ctrl,'ExploratoryMode',mat2str(~strictMode));
                in=in.setBlockParameter(harness,'ScenarioCode',num2str(scCodes(si)));
                in=in.setBlockParameter(harness,'Seed',num2str(seed));
                in=in.setBlockParameter(harness,'AttackScale','1');
                in=in.setBlockParameter(harness,'StressAmplitude',num2str(attackScale,'%.17g'));
                in=in.setModelParameter('StopTime',num2str(stopTime,'%.17g'), ...
                    'ReturnWorkspaceOutputs','on');
                out=sim(in);
                obs=zeros(numel(tq),4);
                for j=1:4
                    obs(:,j)=sampleOutput(out,sprintf('AEFC_NATIVE_OBS_%02d',j),tq,1);
                end
                diagv=sampleOutput(out,'AEFC_DIAG',tq,16);
                ushield=sampleOutput(out,'AEFC_SHIELD_VECTOR',tq,4);
                upost=sampleOutput(out,'AEFC_POST_ATTACK_VECTOR',tq,4);
                nativeBasePref=zeros(numel(tq),4);
                nativeDeliveredPref=zeros(numel(tq),4);
                for prefIndex=1:4
                    nativeBasePref(:,prefIndex)=sampleOutput(out,...
                        sprintf('AEFC_NATIVE_PREF_BASE_%02d',prefIndex),tq,1);
                    nativeDeliveredPref(:,prefIndex)=sampleOutput(out,...
                        sprintf('AEFC_NATIVE_PREF_DELIVERED_%02d',prefIndex),tq,1);
                end
                prefResidual=nativeDeliveredPref-nativeBasePref-ushield-upost;
                % Double precision physical edge identity, not a proof of
                % nonlinear grid-wide actuator dynamics or backup viability.
                prefTol=1e-6+1e-6*max(abs(nativeDeliveredPref),[],'all');
                assert(all(abs(prefResidual)<prefTol,'all'), ...
                    'AEFC:NativePrefInterposition', ...
                    'Actual delivered Pref must equal original + correction + downstream attack');
                allgen=sampleOutput(out,'AEFC_NATIVE_GEN_ALL_10',tq,10);
                rawGenSignal=out.get('AEFC_NATIVE_GEN_ALL_10');
                [tRaw,genRaw]=extractSeries(rawGenSignal);
                tRaw=double(tRaw(:));
                genRaw=normalizeTimeMajor(double(genRaw),numel(tRaw),10, ...
                    'AEFC_NATIVE_GEN_ALL_10_RAW');
                [tRaw,ia]=unique(tRaw,'stable');genRaw=genRaw(ia,:);
                assert(all(isfinite(tRaw)) && all(isfinite(genRaw),'all') && ...
                    all(diff(tRaw)>0),...
                    'AEFC:RawPhysicalTime','Nonfinite/unsorted native monitor samples');
                assert(isequal(size(allgen),[numel(tq),10]) && all(isfinite(allgen),'all'), ...
                    'AEFC:TenSpeedMissing','All ten real generator speed channels must be recorded');
                % Initial pre-attack operating reference is observed at t=0,
                % never a secret clean trajectory or an attack identity flag.
                allgenReference=allgen(1,:);
                zAll=(allgen-allgenReference)/0.02;
                allgenMax=max(abs(zAll),[],2);
                tenSafe=allgenMax<=cfg.normalized_safe_limit+1e-9;
                rawNorm=(genRaw-allgenReference)/0.02;
                rawSpeedMax=max(abs(rawNorm),[],2);
                rawSafe=rawSpeedMax<=cfg.normalized_safe_limit+1e-9;
                rawRecordName=sprintf('seed_%02d.raw-solver.jsonl',seed);
                rawRecordPath=fullfile(runDir,rawRecordName);
                assert(exist(rawRecordPath,'file')~=2,'AEFC:RawOverwrite', ...
                    'Native original physical solver samples already archived');
                rawFile=fopen(rawRecordPath,'w');
                assert(rawFile>0,'AEFC:RawIO','Cannot write unresampled physical monitor');
                for rawIndex=1:numel(tRaw)
                    rawRecord=struct('time',tRaw(rawIndex), ...
                        'all_ten_generator_speed_native',genRaw(rawIndex,:), ...
                        'all_ten_speed_normalized',rawNorm(rawIndex,:), ...
                        'all_ten_speed_inside_proxy',logical(rawSafe(rawIndex)));
                    fwrite(rawFile,jsonencode(rawRecord),'char');
                    fwrite(rawFile,sprintf('\n'),'char');
                end
                fclose(rawFile);
                assert(all(diagv(:,11)==0) && all(diagv(:,12)==0), ...
                    'AEFC:FalseCertification','Four-channel experiment must not mark full state certified');
                assert(all(abs(upost(:))<=attackScale+1e-9), ...
                    'AEFC:StressAttackExceeded','Actual post-shield corruption exceeds preregistered stress amplitude');
                assert(all(diagv(:,16)==mCodes(mi)),'AEFC:MethodIdentity','Wrong method selector');
                assert(all((diagv(:,8)>0)==(diagv(:,14)>0.5)),...
                    'AEFC:ReleaseSemantics','A correction cannot be released without a proxy status');
                if strictMode,assert(all(diagv(:,14)==0) && all(ushield(:)==0), ...
                    'AEFC:StrictNoRelease','Strict full-state mode must never release a correction');end
                z=(obs-center')./scale';
                maxabs=max(abs(z),[],2);
                safeObserved=maxabs<=cfg.normalized_safe_limit+1e-9;
                idxEnd=double(cfg.attack_end_step)+1;
                assert(idxEnd<=numel(tq),'AEFC:AttackHorizon','Attack outside evaluation horizon');
                exposed=maxabs(idxEnd)>cfg.normalized_recovery_limit;
                recIdx=[];
                if exposed
                    for t=idxEnd+1:numel(tq)-19
                        if all(maxabs(t:t+19)<=cfg.normalized_recovery_limit)
                            recIdx=t;break;
                        end
                    end
                end
                recovered=~isempty(recIdx);
                tenExposed=allgenMax(idxEnd)>cfg.normalized_recovery_limit;
                tenRecIdx=[];
                if tenExposed
                    for t=idxEnd+1:numel(tq)-19
                        if all(allgenMax(t:t+19)<=cfg.normalized_recovery_limit)
                            tenRecIdx=t;break;
                        end
                    end
                end
                tenRecovered=~isempty(tenRecIdx);
                tracePath=fullfile(runDir,sprintf('seed_%02d.jsonl',seed));
                assert(exist(tracePath,'file')~=2,'AEFC:TraceOverwrite','Existing evidence file');
                fid=fopen(tracePath,'w');assert(fid>0,'AEFC:IO','Cannot write trace');
                for k=1:numel(tq)
                    r=struct('experiment','ieee39_noncertified_persistent_pref_stress', ...
                        'commit_sha',commitSha,'config_id',configId,'stress_protocol_id',stressId, ...
                        'seed',seed,'attack_scale',attackScale,'method',method,...
                        'scenario',scenario,'time',tq(k),'native_speed',obs(k,:),...
                        'speed_normalized',z(k,:), ...
                        'trust',diagv(k,1),'risk',diagv(k,2),...
                        'gate_allowed',logical(diagv(k,3)>0.5), ...
                        'observable_discrepancy',diagv(k,4), ...
                        'policy_movement',diagv(k,5),...
                        'proxy_intervention',diagv(k,6),...
                        'proxy_margin',diagv(k,7), ...
                        'proxy_status',diagv(k,8), ...
                        'dangerous_proposal',logical(diagv(k,9)>0.5), ...
                        'deployment_accepted',logical(diagv(k,10)>0.5), ...
                        'full_state_coverage',false,'full_state_certified',false,...
                        'backup_used',logical(diagv(k,13)>0.5), ...
                        'surrogate_released',logical(diagv(k,14)>0.5),...
                        'proxy_pass',logical(diagv(k,15)>0.5),...
                        'shield_action',ushield(k,:),'post_shield_attack',upost(k,:),...
                        'executed_correction',ushield(k,:)+upost(k,:), ...
                        'original_governor_pref_reference',nativeBasePref(k,:), ...
                        'native_delivered_pref_reference',nativeDeliveredPref(k,:), ...
                        'pref_interposition_error',prefResidual(k,:), ...
                        'sampled_speed_inside_proxy',logical(safeObserved(k)),...
                        'all_ten_generator_speed_native',allgen(k,:), ...
                        'all_ten_generator_speed_normalized',zAll(k,:), ...
                        'sampled_all_ten_speed_inside_proxy',logical(tenSafe(k)));
                    fwrite(fid,jsonencode(r),'char');fwrite(fid,sprintf('\n'),'char');
                end
                fclose(fid);
                counter=counter+1;
                rows(counter).commit_sha=commitSha; %#ok<AGROW>
                rows(counter).config_id=configId;
                rows(counter).seed=seed;rows(counter).method=method;
                rows(counter).scenario=scenario;rows(counter).attack_scale=attackScale;
                rows(counter).exposed_at_attack_stop=double(exposed);
                rows(counter).strict_recovered=double(recovered);
                if recovered
                    rows(counter).time_from_attack_stop=tq(recIdx)-tq(idxEnd);
                else
                    rows(counter).time_from_attack_stop=NaN;
                end
                rows(counter).speed_proxy_violation_steps=sum(~safeObserved);
                rows(counter).proxy_release_count=sum(diagv(:,14)>0.5);
                rows(counter).proxy_refusal_count=sum(diagv(:,8)<0);
                rows(counter).backup_used_count=sum(diagv(:,13)>0.5);
                rows(counter).full_state_certified_count=0;
                rows(counter).max_abs_pref_interposition_error=max(abs(prefResidual),[],'all');
                rows(counter).original_governor_pref_path_logged=1;
                rows(counter).native_backup_governor_reachability_certified=0;
                rows(counter).mean_native_speed_error=mean(maxabs);
                rows(counter).all_ten_speed_exposed_at_attack_stop=double(tenExposed);
                rows(counter).all_ten_speed_strict_recovered=double(tenRecovered);
                if tenRecovered
                    rows(counter).all_ten_speed_recovery_time=tq(tenRecIdx)-tq(idxEnd);
                else
                    rows(counter).all_ten_speed_recovery_time=NaN;
                end
                rows(counter).all_ten_speed_sampled_violation_steps=sum(~tenSafe);
                rows(counter).raw_solver_speed_monitor_samples=numel(tRaw);
                rows(counter).raw_solver_max_ten_speed_normalized=max(rawSpeedMax);
                rows(counter).raw_solver_ten_speed_violation_count=sum(~rawSafe);
                rows(counter).raw_solver_intersample_coverage_proven=0;
                rows(counter).mean_all_ten_speed_error=mean(allgenMax);
                saveSummary(fullfile(runDir,sprintf('seed_%02d.summary.json',seed)),rows(counter));
            end
        end
    end
end
try,set_param(model,'FastRestart','off');catch,end
T=struct2table(rows);
writetable(T,fullfile(outRoot,'summary.csv'));
manifest=struct('backend','MATLAB R2024b original native IEEE39 instrumented persistent Pref pressure copy',...
    'scope','EXPLORATORY held physical Pref attack in true R2024b IEEE39; only sampled ten speeds, 4 online; no full DAE certified safety', ...
    'source_commit',commitSha,'config_id',configId, ...
    'stress_protocol_id',stressId,'model',model, ...
    'attack_shape','held seed-signed physical Pref downstream of shield for exactly steps 15-89', ...
    'stress_attack_not_original_certified_bound',true, ...
    'full_IEEE39_state_safety_verified',false, ...
    'methods',{methods},'scenarios',{scenarios},'seeds',seeds,...
    'attack_scales',scales,'rows',height(T),'sample_s',dt,...
    'strict_full_state_no_release',strictMode,...
    'recovery_criterion','outside 0.25 normalized speed at attack stop; then inside for 20 full samples', ...
    'statistical_unit','seed; deterministic phases are not iid independent trials', ...
    'full_state_certified',false,'all_ten_generators_speed_monitored',true, ...
    'pref_setpoint_interposition_monitored',true, ...
    'unaltered_native_solver_time_physical_monitor',true, ...
    'intersample_coverage_proven',false, ...
    'original_governor_backup_certified',false, ...
    'all_ten_speed_recovery_normalization','each generator preattack observed t=0 rotor-speed; divisor 0.02 p.u.', ...
    'proxy_bounds_unvalidated',true);
saveSummary(fullfile(outRoot,'manifest.json'),manifest);
close_system(model,0);
end

function X=sampleOutput(out,name,tq,dim)
try, v=out.get(name); catch, v=[]; end
assert(~isempty(v),'AEFC:OutputMissing','Missing SimulationOutput variable %s',name);
[t,d]=extractSeries(v);
t=double(t(:)); d=double(d);
if ~isreal(d), d=abs(d); end
d=normalizeTimeMajor(d,numel(t),dim,name);
[t,ia]=unique(t,'stable'); d=d(ia,:);
if numel(t)==1 && startsWith(name,'AEFC_NATIVE_PREF_BASE_')
    % In the official R2024b plant the ORIGINAL governor Pref source is a
    % true constant; To Workspace can save a single initial sample. A
    % zero-order held constant is the actual physical source behavior.
    % Deliberately DO NOT permit this exception for DELIVERED Pref,
    % attacks, protection decisions, or real physical measurements.
    assert(abs(t(1)-tq(1))<1e-8 && all(isfinite(d),'all'), ...
        'AEFC:OriginalPrefSingleSample','Single Pref source sample invalid');
    X=repmat(d(1,:),numel(tq),1);
    return;
end
assert(numel(t)>=2,'AEFC:OutputSamples','Dynamic signal %s has fewer than two samples.',name);
if numel(t)==numel(tq) && max(abs(t-tq))<=1e-9
    X=d(:,1:dim);
else
    X=interp1(t,d(:,1:dim),tq,'nearest','extrap');
end
assert(isequal(size(X),[numel(tq) dim]),'AEFC:OutputShape','Signal %s did not normalize to time-major %dx%d.',name,numel(tq),dim);
assert(all(isfinite(X),'all'),'AEFC:OutputFinite','Signal %s contains non-finite values.',name);
end

function d=normalizeTimeMajor(d,nT,dim,name)
sz=size(d);
if isvector(d) && dim==1
    assert(numel(d)==nT,'AEFC:OutputSamples','Scalar signal %s sample count mismatch.',name);
    d=d(:); return;
end
if numel(d)~=nT*dim
    error('AEFC:OutputDimension','Signal %s has %d values; expected %d samples x %d channels.',name,numel(d),nT,dim);
end
nd=ndims(d);
timeDim=find(sz==nT,1,'last');
assert(~isempty(timeDim),'AEFC:OutputTimeDimension','Cannot identify time dimension for %s.',name);
perm=[timeDim setdiff(1:nd,timeDim,'stable')];
d=permute(d,perm);
d=reshape(d,nT,[]);
assert(size(d,2)==dim,'AEFC:OutputDimension','Signal %s normalized to %d channels; expected %d.',name,size(d,2),dim);
end

function [t,d]=extractSeries(v)
if isa(v,'timeseries')
    t=v.Time; d=v.Data;
elseif isa(v,'Simulink.SimulationData.Dataset')
    assert(v.numElements>0,'AEFC:DatasetEmpty','Dataset output is empty.');
    el=v.getElement(1); [t,d]=extractSeries(el.Values);
elseif isa(v,'Simulink.SimulationData.Signal')
    [t,d]=extractSeries(v.Values);
elseif isstruct(v)
    if isfield(v,'time') && isfield(v,'signals') && isfield(v.signals,'values')
        t=v.time; d=v.signals.values;
    elseif isfield(v,'Time') && isfield(v,'Data')
        t=v.Time; d=v.Data;
    else
        error('AEFC:OutputFormat','Unsupported struct output for native evidence.');
    end
else
    try, t=v.Time; d=v.Data;
    catch, error('AEFC:OutputFormat','Unsupported output class %s.',class(v)); end
end
end

function safeClose(fid)
if isnumeric(fid) && isscalar(fid) && fid>0
    try, fclose(fid); catch, end
end
end

function idx=findRecovery(t,maxabs,attackEnd,lim,holdN)
idx=[]; candidates=find(t>attackEnd);
for k=1:numel(candidates)
    i=candidates(k); j=min(numel(t),i+holdN-1);
    if j-i+1==holdN && all(maxabs(i:j)<=lim), idx=i; return; end
end
end

function s=deriveScale(edges,center)
s=zeros(4,1);
for i=1:4
    reason=''; try, reason=lower(edges(i).observation_reason); catch, end
    if contains(reason,'rotor-speed'), s(i)=0.02;
    elseif contains(reason,'terminal-voltage'), s(i)=0.10;
    elseif contains(reason,'rotor-angle'), s(i)=0.35;
    else, s(i)=max(0.02,0.10*max(abs(center(i)),1e-3)); end
end
end

function id=sha16(path)
bytes=uint8(fileread(path)); md=java.security.MessageDigest.getInstance('SHA-256'); md.update(bytes); d=typecast(md.digest(),'uint8');
hex=lower(reshape(dec2hex(d,2).',1,[])); id=hex(1:16);
end

function saveSummary(path,obj)
fid=fopen(path,'w'); assert(fid>0,'AEFC:IO','Cannot open %s',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(obj,'PrettyPrint',true),'char'); fwrite(fid,sprintf('\n'),'char');
end
