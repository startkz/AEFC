function aefc_ieee39_frozen_confirm(scenarioCode,seedStart,seedEnd)
% FROZEN v3 native IEEE39 confirmatory reproduction, source controller and config unchanged.
% Holdout 80:119 divided into four disjoint fixed shards, no tuning.; 436 post-stop steps; do not claim G3 from proxy convergence.
% scenarioCode: clean(1), knowledge(2), joint(4).
% Main Experiment results/ieee39_joint20 is read-only and never modified.
%
% kind/value:
%   intensity : joint attack scale gamma; methods 1,2,3,4,7
%   gate      : targeted unsafe learned-proposal blend alpha; methods 4,7
%   qmin      : AEFC-Full QMinOverride
%   rho       : AEFC-Full RhoMaxOverride
%   trust     : AEFC-Full TrustRegionOverride (Delta_theta)

repo=pwd; scenarioCode=double(scenarioCode);
assert(ismember(scenarioCode,[1 2 4]),'AEFC:Scenario','Expected scenario 1, 2 or 4');
kind='frozen_v3_confirmatory_80_119'; value=scenarioCode;
assert(ismember(seedStart,[80 90 100 110]) && seedEnd==seedStart+9, 'AEFC:HoldoutShard','Only frozen ten-seed shards 80:89,90:99,100:109,110:119.');
cfgPath=fullfile(repo,'configs','ieee39_joint20.json'); cfg=jsondecode(fileread(cfgPath));
mapPath=fullfile(repo,cfg.mapping_path); mapping=jsondecode(fileread(mapPath));
assert(mapping.validated,'AEFC:MappingInvalid','Supplemental native runs require validated mapping.');
assert(strcmp(mapping.selection_policy,'paired-generator-physical-speed-v2'), ...
    'AEFC:MappingPolicy','Supplemental native runs require authoritative paired mapping.');

attackScale=1.0; stressAlpha=0.0; rhoOverride=-1.0; qOverride=-1.0; trustOverride=-1.0;
methodCodes=[7 7 7 7];
modeCodes=[0 2 3 4];
methodNames={'AEFC-Unprivileged','AEFC-Checkpoint','AEFC-OnlineRelearn','AEFC-ContractiveReentry'};
assert(attackScale>=0,'AEFC:SupplementalValue','Attack scale must be nonnegative.');
assert(stressAlpha>=0 && stressAlpha<=1,'AEFC:SupplementalValue','Gate stress alpha must be in [0,1].');

tag=sprintf('scenario_%d',scenarioCode); outRoot=fullfile(repo,'results','p0_native_v3_confirmation',tag,sprintf('seeds_%03d_%03d',seedStart,seedEnd));
if ~exist(outRoot,'dir'), mkdir(outRoot); end

model=char(cfg.model); modelPath=fullfile(repo,'results','ieee39_r2024b',[model '.slx']);
if exist(modelPath,'file')~=2, aefc_ieee39_build_native_model; end
load_system(modelPath);
try, set_param(model,'ReturnWorkspaceOutputs','on'); catch, end
try, set_param(model,'SignalLogging','off'); catch, end
ctrl=[model '/AEFC_NATIVE_CONTROLLER'];
set_param(ctrl,'System','AEFCNativeOnlineRecoveryController','SimulateUsing','Interpreted execution');
try, set_param(model,'SimulationCommand','update'); catch ME, close_system(model,0); rethrow(ME); end

center=double(mapping.baseline_observation(:)); scale=deriveScale(mapping.observation_edges,center);
commitSha=getenv('GITHUB_SHA'); if isempty(commitSha), commitSha='LOCAL'; end
experimentId=sha16text(sprintf('%s|%.17g|%s',kind,value,commitSha));
dt=double(cfg.sample_time); stopTime=(double(cfg.attack_end_step)+436)*dt;
tq=(0:double(cfg.attack_end_step)+436)'*dt;
if scenarioCode==1, scenario='clean'; elseif scenarioCode==2, scenario='knowledge'; else, scenario='joint'; end
rows=struct([]); rowIdx=0;

set_param(ctrl,'MethodCode',num2str(methodCodes(1)),'RecoveryMode','0','ScenarioCode',num2str(scenarioCode),'Seed','0', ...
    'AttackScale',num2str(attackScale,'%.17g'),'ProposalStressAlpha',num2str(stressAlpha,'%.17g'), ...
    'RhoMaxOverride',num2str(rhoOverride,'%.17g'),'QMinOverride',num2str(qOverride,'%.17g'), ...
    'TrustRegionOverride',num2str(trustOverride,'%.17g'));
try, set_param(model,'SimulationCommand','update'); catch, end
fastRestart=false;
try, set_param(model,'FastRestart','on'); fastRestart=true; catch, end
assert(fastRestart,'AEFC:FastRestart','Supplemental native cell requires Fast Restart.');

for mi=1:numel(methodCodes)
    mc=methodCodes(mi); method=methodNames{mi};
    runDir=fullfile(outRoot,method); if ~exist(runDir,'dir'), mkdir(runDir); end
    for seed=seedStart:seedEnd
        simIn=Simulink.SimulationInput(model);
        simIn=simIn.setBlockParameter(ctrl,'MethodCode',num2str(mc));
        simIn=simIn.setBlockParameter(ctrl,'RecoveryMode',num2str(modeCodes(mi)));
        simIn=simIn.setBlockParameter(ctrl,'ScenarioCode',num2str(scenarioCode));
        simIn=simIn.setBlockParameter(ctrl,'Seed',num2str(seed));
        simIn=simIn.setBlockParameter(ctrl,'AttackScale',num2str(attackScale,'%.17g'));
        simIn=simIn.setBlockParameter(ctrl,'ProposalStressAlpha',num2str(stressAlpha,'%.17g'));
        simIn=simIn.setBlockParameter(ctrl,'RhoMaxOverride',num2str(rhoOverride,'%.17g'));
        simIn=simIn.setBlockParameter(ctrl,'QMinOverride',num2str(qOverride,'%.17g'));
        simIn=simIn.setBlockParameter(ctrl,'TrustRegionOverride',num2str(trustOverride,'%.17g'));
        simIn=simIn.setModelParameter('StopTime',num2str(stopTime,'%.17g'),'ReturnWorkspaceOutputs','on');
        out=sim(simIn);

        obs=zeros(numel(tq),4);
        for q=1:4, obs(:,q)=sampleOutput(out,sprintf('AEFC_NATIVE_OBS_%02d',q),tq,1); end
        diagv=sampleOutput(out,'AEFC_DIAG',tq,40);
        ushield=sampleOutput(out,'AEFC_SHIELD_VECTOR',tq,4);
        upost=sampleOutput(out,'AEFC_POST_ATTACK_VECTOR',tq,4);
        validateEvidence(diagv,upost,mc,cfg,attackScale,scenarioCode);
        % Stable intact local commissioning checkpoint captured at t=10;
        % no malware identity or attack schedule may enter its action rule.
        assert(all(diagv(11:end,33)>0.5),'AEFC:CheckpointEnrollment','Missing commissioning snapshot');
        assert(all(isfinite(diagv(:))),'AEFC:TraceFinite','Nonfinite controller diagnostics');
        assert(all(abs(diagv(:,24))>=0),'AEFC:ReportDetector','Bad report distance');
        checkpointDistance=diagv(:,31);
        checkpointValid=diagv(:,33)>0.5;
        detAlert=diagv(:,25)>0.5;
        phase=diagv(:,26);
        alertDetected=any(detAlert(16:44));
        falseAlarm=any(detAlert(1:15)) || ...
            (scenarioCode==1 && any(detAlert));
        pidx=find(detAlert,1,'first');
        cidx=find(phase==3,1,'first');
        if isempty(pidx), pidx=NaN; end
        if isempty(cidx), cidx=NaN; end
        errTheta=sqrt(sum((diagv(:,11:14)-diagv(:,15:18)).^2,2));
        assert(max(errTheta(1:cfg.attack_start_step))<1e-9,'AEFC:ShadowPreAttack','Clean shadow differs before attack');
        postIdx=(double(cfg.attack_end_step)+2):numel(tq);
        assert(numel(postIdx)>=120,'AEFC:PostWindow','Need at least 120 post-poison steps');
        epsTarget=1e-3; holdSteps=20;
        attained=NaN;
        for pi=1:numel(postIdx)-holdSteps+1
            if all(errTheta(postIdx(pi:pi+holdSteps-1))<=epsTarget)
                attained=pi-1; break;
            end
        end
        exposed=errTheta(double(cfg.attack_end_step)+2)>epsTarget;

        z=(obs-center')./scale'; maxabs=max(abs(z),[],2);
        safe=maxabs<=double(cfg.normalized_safe_limit)+1e-9;
        gate=diagv(:,3)>0.5; dangerous=diagv(:,9)>0.5;
        dangerousCount=sum(dangerous); dangerousAuth=sum(gate & dangerous);
        far=dangerousAuth/max(dangerousCount,1);
        attackEnd=double(cfg.attack_end_step)*dt;
        recIdx=findRecovery(tq,maxabs,attackEnd,double(cfg.normalized_recovery_limit),5);
        if isempty(recIdx), recSuccess=0; recTime=stopTime-attackEnd; else, recSuccess=1; recTime=tq(recIdx)-attackEnd; end

        tracePath=fullfile(runDir,sprintf('seed_%02d.jsonl',seed));
        fid=fopen(tracePath,'w'); assert(fid>0,'AEFC:IO','Cannot open trace file.');
        cleanup=onCleanup(@()safeClose(fid)); %#ok<NASGU>
        for k=1:numel(tq)
            r=struct('commit_sha',commitSha,'experiment_id',experimentId,'experiment_kind',kind, ...
                'level_value',value,'mapping_policy',mapping.selection_policy,'seed',seed,'method',method, ...
                'scenario',scenario,'time',tq(k),'observation_native',obs(k,:),'observation_normalized',z(k,:), ...
                'trust_score',diagv(k,1),'risk_upper_bound',diagv(k,2),'gate_decision',logical(gate(k)), ...
                'belief_distortion',diagv(k,4),'policy_drift',diagv(k,5),'shield_intervention',diagv(k,6), ...
                'predicted_margin',diagv(k,7),'attack_active',logical(diagv(k,8)>0.5), ...
                'dangerous_proposal',logical(dangerous(k)),'adapt_accepted',logical(diagv(k,10)>0.5), ...
                'deployed_theta',diagv(k,11:14),'clean_shadow_theta',diagv(k,15:18), ...
                'theta_reference_error',errTheta(k),'shadow_adapt_accepted',logical(diagv(k,19)>0.5), ...
                'shadow_trust',diagv(k,20),'shadow_gate',logical(diagv(k,21)>0.5), ...
                'step_norm',diagv(k,22),'shadow_step_norm',diagv(k,23), ...
                'detector_scatter',diagv(k,24),'alert_latched',logical(detAlert(k)), ...
                'recovery_phase',phase(k),'checkpoint_theta',diagv(k,27:30), ...
                'checkpoint_distance',checkpointDistance(k), ...
                'rollback_step_norm',diagv(k,32),'checkpoint_valid',logical(checkpointValid(k)), ...
                'online_proxy_theta',diagv(k,34:37), ...
                'online_proxy_distance',diagv(k,38), ...
                'online_proxy_accepted',logical(diagv(k,39)>0.5), ...
                'online_proxy_inliers',diagv(k,40), ...
                'shield_action',ushield(k,:),'post_shield_attack',upost(k,:), ...
                'executed_correction',ushield(k,:)+upost(k,:),'safe_native_envelope',logical(safe(k)));
            fwrite(fid,jsonencode(r),'char'); fwrite(fid,sprintf('\n'),'char');
        end
        fclose(fid); fid=-1; clear cleanup;

        rowIdx=rowIdx+1; rows(rowIdx).commit_sha=commitSha; %#ok<AGROW>
        rows(rowIdx).experiment_id=experimentId; rows(rowIdx).experiment_kind=kind; rows(rowIdx).level_value=value;
        rows(rowIdx).mapping_policy=mapping.selection_policy; rows(rowIdx).seed=seed; rows(rowIdx).method=method;
        rows(rowIdx).scenario=scenario; rows(rowIdx).safety_violation=double(any(~safe));
        rows(rowIdx).min_native_margin=min(double(cfg.normalized_safe_limit)-maxabs);
        rows(rowIdx).false_authorization_rate=far; rows(rowIdx).dangerous_proposal_count=dangerousCount;
        rows(rowIdx).dangerous_authorization_count=dangerousAuth;
        rows(rowIdx).dangerous_proposal_rate=mean(dangerous);
        rows(rowIdx).gate_authorization_rate=mean(gate);
        rows(rowIdx).max_belief_distortion=max(diagv(:,4)); rows(rowIdx).max_policy_drift=max(diagv(:,5));
        rows(rowIdx).mean_trust=mean(diagv(:,1)); rows(rowIdx).max_risk=max(diagv(:,2));
        rows(rowIdx).recovery_success=recSuccess; rows(rowIdx).recovery_time=recTime;
        rows(rowIdx).shield_intervention_ratio=mean(diagv(:,6)>1e-8);
        rows(rowIdx).mean_shield_intervention=mean(diagv(:,6)); rows(rowIdx).max_shield_intervention=max(diagv(:,6));
        rows(rowIdx).theta_error_at_stop=errTheta(postIdx(1));
        rows(rowIdx).theta_error_at_end=errTheta(end);
        rows(rowIdx).theta_error_max_post=max(errTheta(postIdx));
        rows(rowIdx).theta_error_initially_outside_epsilon=double(exposed);
        rows(rowIdx).time_to_epsilon20=attained;
        rows(rowIdx).post_updates_accepted=sum(diagv(postIdx,10)>0.5);
        rows(rowIdx).post_updates_rejected=sum(diagv(postIdx,10)<=0.5);
        rows(rowIdx).post_proxy_updates_accepted=sum(diagv(postIdx,39)>0.5);
        rows(rowIdx).post_relearn_accepted=sum(diagv(postIdx,10)>0.5 & diagv(postIdx,26)>=2);
        rows(rowIdx).online_proxy_distance_final=diagv(end,38);
        rows(rowIdx).post_online_proxy_inliers_min=min(diagv(postIdx,40));
        rows(rowIdx).post_clean_updates_accepted=sum(diagv(postIdx,19)>0.5);
        rows(rowIdx).post_step_norm_max=max(diagv(postIdx,22));
        rows(rowIdx).post_deployment_step_count=sum(diagv(postIdx,22)>1e-12);
        rows(rowIdx).post_nondecrease_count=sum(diff(errTheta(postIdx))>1e-10);
        rows(rowIdx).sampled_state_safety_violations=sum(~safe);
        rows(rowIdx).mode_code=modeCodes(mi);
        rows(rowIdx).alarm_seen=double(alertDetected);
        rows(rowIdx).false_alarm=double(falseAlarm);
        rows(rowIdx).first_alarm_sample=double(pidx)-1;
        rows(rowIdx).first_rollback_complete_sample=double(cidx)-1;
        rows(rowIdx).checkpoint_distance_at_last_attack=checkpointDistance(44);
        rows(rowIdx).checkpoint_distance_post_first=checkpointDistance(45);
        rows(rowIdx).checkpoint_distance_final=checkpointDistance(end);
        rows(rowIdx).shadow_error_final=errTheta(end);
        rows(rowIdx).rollback_steps=sum(diagv(:,32)>1e-9 & phase>=2);
        rows(rowIdx).mean_normalized_state_l1=mean(sum(abs(z),2));
        rows(rowIdx).mean_executed_correction_l2=mean(sqrt(sum((ushield+upost).^2,2)));
        rows(rowIdx).backend='native_R2024b_true_AEFC_four_coefficient_online_proxy_pilot';
        saveSummary(fullfile(runDir,sprintf('seed_%02d.summary.json',seed)),rows(rowIdx));
    end
end

try, set_param(model,'FastRestart','off'); catch, end
T=struct2table(rows); writetable(T,fullfile(outRoot,'summary.csv'));
manifest=struct('backend','mathworks_ieee39_r2024b_native_supplemental','commit_sha',commitSha, ...
    'experiment_id',experimentId,'experiment_kind',kind,'level_value',value,'mapping_policy',mapping.selection_policy, ...
    'seeds',seedEnd-seedStart+1,'methods',{methodNames},'scenario',scenario,'rows',height(T),'attack_scale',attackScale, ...
    'proposal_stress_alpha',stressAlpha,'rho_override',rhoOverride,'qmin_override',qOverride, ...
    'trust_region_override',trustOverride,'main_experiment_untouched',true,'sample_time_s',dt, ...
    'post_poison_steps',numel(postIdx),'epsilon',epsTarget,'hold_steps',holdSteps, ...
    'new_seed_range',sprintf('%d:%d FROZEN CONFIRMATORY; no parameter tuning',seedStart,seedEnd), ...
    'modes',{methodNames},'detector_threshold',0.35,'checkpoint_sample',10, ...
    'relearn_description','online majority-consensus proxy; matching clean-shadow trim and historical innovation operators; no offline shadow access', ...
    'relearn_step_fraction',0.25,'relearn_step_maxnorm',0.01, ...
    'contractive_reentry_step_fraction',1.0,'contractive_reentry_maxnorm',0.01, ...
    'contractive_anchor_prox_gain',0.08, ...
    'contractive_anchor_condition','pre-attack commissioning checkpoint assumed isolated, no independent attestation', ...
    'status','FROZEN HOLDOUT CONFIRMATORY; results require independent full-trace audit', ...
    'clean_streak_required',3,'rollback_factor',0.5, ...
    'checkpoint_integrity','local commissioning snapshot assumed intact, not cryptographically attested', ...
    'shadow_reference','offline same operator, same physical observation path, no feedback', ...
    'parameter_kind','actual four-dimensional deployed recovery coefficients, not neural backbone', ...
    'experiment_not_main',true, ...
    'evidence_capture','full theta + clean shadow + deployment acceptance at every original sample');
saveSummary(fullfile(outRoot,'manifest.json'),manifest);
close_system(model,0);
end

function X=sampleOutput(out,name,tq,dim)
try, v=out.get(name); catch, v=[]; end
assert(~isempty(v),'AEFC:OutputMissing','Missing SimulationOutput variable %s',name);
[t,d]=extractSeries(v); t=double(t(:)); d=double(d); if ~isreal(d), d=abs(d); end
d=normalizeTimeMajor(d,numel(t),dim,name); [t,ia]=unique(t,'stable'); d=d(ia,:);
assert(numel(t)>=2,'AEFC:OutputSamples','Signal %s has fewer than two samples.',name);
if numel(t)==numel(tq) && max(abs(t-tq))<=1e-9, X=d(:,1:dim);
else, X=interp1(t,d(:,1:dim),tq,'nearest','extrap'); end
assert(isequal(size(X),[numel(tq) dim]),'AEFC:OutputShape','Signal %s shape mismatch.',name);
assert(all(isfinite(X),'all'),'AEFC:OutputFinite','Signal %s contains non-finite values.',name);
end

function d=normalizeTimeMajor(d,nT,dim,name)
sz=size(d);
if isvector(d) && dim==1
    assert(numel(d)==nT,'AEFC:OutputSamples','Scalar signal %s sample count mismatch.',name); d=d(:); return;
end
if numel(d)~=nT*dim, error('AEFC:OutputDimension','Signal %s value count mismatch.',name); end
nd=ndims(d); timeDim=find(sz==nT,1,'last');
assert(~isempty(timeDim),'AEFC:OutputTimeDimension','Cannot identify time dimension for %s.',name);
perm=[timeDim setdiff(1:nd,timeDim,'stable')]; d=permute(d,perm); d=reshape(d,nT,[]);
assert(size(d,2)==dim,'AEFC:OutputDimension','Signal %s channel count mismatch.',name);
end

function validateEvidence(diagv,upost,mc,cfg,attackScale,scenarioCode)
tol=1e-10; assert(size(diagv,2)==40 && size(upost,2)==4,'AEFC:EvidenceShape','Evidence shape mismatch.');
if any(mc==[1 2 6]), assert(max(abs(diagv(:,6)))<=tol,'AEFC:InterventionSemantics','Method must have zero shield intervention.'); end
if any(mc==[1 2 3]), assert(max(abs(diagv(:,1)-0.5))<=tol,'AEFC:TrustSemantics','Method must retain fixed trust 0.5.'); end
active=false(size(upost,1),1); active(double(cfg.attack_start_step)+1:double(cfg.attack_end_step)+1)=true;
amp=max(abs(upost),[],2); bound=double(cfg.post_shield_control_attack)*attackScale;
if attackScale<=tol || any(scenarioCode==[1 2])
    assert(max(amp)<=tol,'AEFC:PostAttackSemantics','Zero-scale run contains post-shield attack.');
else
    assert(all(amp(~active)<=tol),'AEFC:PostAttackWindow','Post-shield attack appears outside configured window.');
    assert(all(amp(active)>tol),'AEFC:PostAttackWindow','Post-shield attack missing inside configured window.');
    assert(max(amp)<=bound+1e-10,'AEFC:PostAttackBound','Post-shield attack exceeds scaled bound.');
end
assert(sum(diagv(:,8)>0.5)==double(cfg.attack_end_step-cfg.attack_start_step+1),'AEFC:AttackFlag','Attack flag length mismatch.');
end

function [t,d]=extractSeries(v)
if isa(v,'timeseries'), t=v.Time; d=v.Data;
elseif isa(v,'Simulink.SimulationData.Dataset'), assert(v.numElements>0,'AEFC:DatasetEmpty','Dataset is empty.'); el=v.getElement(1); [t,d]=extractSeries(el.Values);
elseif isa(v,'Simulink.SimulationData.Signal'), [t,d]=extractSeries(v.Values);
elseif isstruct(v)
    if isfield(v,'time') && isfield(v,'signals') && isfield(v.signals,'values'), t=v.time; d=v.signals.values;
    elseif isfield(v,'Time') && isfield(v,'Data'), t=v.Time; d=v.Data;
    else, error('AEFC:OutputFormat','Unsupported struct output.'); end
else
    try, t=v.Time; d=v.Data; catch, error('AEFC:OutputFormat','Unsupported output class %s.',class(v)); end
end
end

function safeClose(fid)
if isnumeric(fid) && isscalar(fid) && fid>0, try, fclose(fid); catch, end, end
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

function tag=safeTag(v)
tag=strrep(sprintf('%.6g',v),'.','p'); tag=strrep(tag,'-','m'); tag=strrep(tag,'+','');
end

function id=sha16text(txt)
md=java.security.MessageDigest.getInstance('SHA-256'); md.update(uint8(txt)); d=typecast(md.digest(),'uint8');
hex=lower(reshape(dec2hex(d,2).',1,[])); id=hex(1:16);
end

function saveSummary(path,obj)
fid=fopen(path,'w'); assert(fid>0,'AEFC:IO','Cannot open %s',path); c=onCleanup(@()fclose(fid)); %#ok<NASGU>
fwrite(fid,jsonencode(obj,'PrettyPrint',true),'char'); fwrite(fid,sprintf('\n'),'char');
end
