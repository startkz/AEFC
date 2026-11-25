classdef AEFCNativeController < matlab.System
% TDSC-R1 experimental native IEEE39 controller (new audit branch only).
% ONLINE interface: (trusted local FOUR rotor-speed sensors, received packet).
% No scenario/seed/attack-active, malicious label, true state or clean shadow.
% An offline AEFCNativeAttackHarness alone handles attacker instrumentation.
%
% MethodCode: 1 FedRL; 2 RobustAgg; 3 no-PATBU; 4 no-Gate;
% 5 no-TGOPA; 6 no-Shield (excluded from equal-shield comparison);
% 7 AEFC-Full; 8 fixed Supervisor-only.
% ExploratoryMode=false is STRICT: do not release corrections because
% complete native-plant state coverage is unavailable. Existing internal
% governors are not certified by the supervisor and continue to operate.
% ExploratoryMode=true releases only four-speed SURROGATE-screened actions.
properties(Nontunable)
    ConfigPath = 'configs/ieee39_joint20.json'
    MappingPath = 'results/ieee39_r2024b/interface_mapping.json'
end
properties
    MethodCode = 7
    ExploratoryMode = false
end
properties(Access=private)
    cfg
    mapping
    Bn
    center
    scale
    belief
    theta
end
methods(Access=protected)
    function setupImpl(obj,~,~)
        obj.loadRuntimeConfig();
        obj.resetRuntimeState();
    end
    function resetImpl(obj)
        obj.resetRuntimeState();
    end
    function [uShield,diagOut]=stepImpl(obj,localPhysical,packet)
        zNative=double(localPhysical(:));
        packet=double(packet(:));
        assert(numel(zNative)==4 && numel(packet)==67 && ...
            all(isfinite(zNative)) && all(isfinite(packet)), ...
            'AEFC:OnlinePacket','Invalid finite four-speed and 67-field online packet');
        c=obj.cfg;
        n=double(c.clients);f=double(c.byzantine_clients);
        assert(n==7 && f==2,'AEFC:OnlinePacketShape','Expected seven reported clients');
        zLocal=(zNative-obj.center)./obj.scale;
        obsReceived=packet(1:4);
        updates=reshape(packet(5:32),[4 n]);
        evidence=reshape(packet(33:60),[4 n]);
        ages=packet(61:67);
        mc=round(double(obj.MethodCode));
        assert(mc>=1 && mc<=8,'AEFC:MethodCode','Unsupported method code');
        % Age and numerical residuals are receiver-visible. A Byzantine
        % sender can lie about its content; no ground-truth label is read.
        ages=max(0,ages);
        weights=zeros(n,1);
        for j=1:n
            ageTerm=exp(-c.patbu.beta_age*ages(j));
            residual=norm(evidence(:,j)-obj.belief,2);
            consistency=1/(1+(residual/max(c.patbu.residual_scale,1e-9))^2);
            weights(j)=ageTerm*consistency;
        end
        trust=min(max(mean(weights),0),1);
        if mc==1
            agg=mean(updates,2);
        else
            agg=obj.robustAggregate(updates,f,c.common_support_k);
        end
        if any(mc==[1 2 3])
            beliefNow=obsReceived;
        elseif mc==8
            beliefNow=zLocal;
        else
            weighted=evidence.*reshape(weights,[1 n]);
            k=obj.trimmedMean(weighted,f);
            beliefNow=c.patbu.lambda_b*obj.belief+ ...
                c.patbu.obs_gain*obsReceived+c.patbu.knowledge_gain*k;
            beliefNow=min(max(beliefNow,-2),2);
        end
        obj.belief=beliefNow;
        discrepancy=norm(obsReceived-beliefNow,2);
        backup=obj.clipVec(-0.05*(obj.Bn')*zLocal,c.action_limit);
        if mc==8
            proposal=backup;
            gateAllowed=false;
            risk=0;dangerous=false;adaptAccepted=false;
            trust=1;
        else
            proposal=obj.clipVec(-0.20*(obj.Bn')*beliefNow+1.5*obj.theta,c.action_limit);
            pred=beliefNow+obj.Bn*proposal;
            safetyShortfall=max(0,max(abs(pred))-0.85);
            recoveryShortfall=max(0,max(abs(beliefNow))-c.normalized_recovery_limit);
            uncertainty=min(1,discrepancy);
            risk=0.62*safetyShortfall+0.16*recoveryShortfall+ ...
                 0.14*uncertainty+0.08*(1-trust);
            gateAllowed=(risk<=c.gate.rho_max-c.gate.risk_margin) && ...
                        (trust>=c.gate.q_min);
            dangerous=max(abs(pred))>c.normalized_safe_limit;
            if any(mc==[1 2 4]),gateAllowed=true;end
            if ~gateAllowed,proposal=backup;end
            % All compared methods retain identical terminal safety checker.
            g=agg;
            if norm(g,2)>c.adaptation.clip_norm
                g=g*(c.adaptation.clip_norm/norm(g,2));
            end
            delta=-c.adaptation.eta*trust*g;
            if norm(delta,2)>c.adaptation.trust_region
                delta=delta*(c.adaptation.trust_region/norm(delta,2));
            end
            candidate=obj.theta+delta;
            valBefore=norm(beliefNow,2)+0.08*norm(obj.theta,2);
            valAfter=norm(beliefNow,2)+0.08*norm(candidate,2);
            adaptAccepted=trust>=c.adaptation.q_min && gateAllowed && ...
                valAfter<=valBefore+c.adaptation.validation_slack;
            if any(mc==[1 2 5])
                obj.theta=obj.theta-0.12*agg;adaptAccepted=true;
            elseif adaptAccepted
                obj.theta=candidate;
            end
        end
        [uShield,status,proxyMargin,~,proxyPass]= ...
            aefc_native_execution_contract(zLocal,proposal,backup,obj.Bn, ...
            c,~logical(obj.ExploratoryMode));
        proxyRecordedMargin=-1e6;
        if isfinite(proxyMargin),proxyRecordedMargin=proxyMargin;end
        intervention=norm(uShield-proposal,2);
        released=status>0;
        backupUsed=(status==2 || status==3 || mc==8);
        % Full-state coverage flags stay 0: four speeds cannot certify the
        % native power-network safety set.  Strict no-release means only
        % null additional Pref correction; original generator PI loops remain.
        diagOut=[trust;risk;double(gateAllowed);discrepancy; ...
            norm(obj.theta,2);intervention;proxyRecordedMargin; ...
            double(status);double(dangerous);double(adaptAccepted); ...
            0;0;double(backupUsed);double(released);double(proxyPass);double(mc)];
    end
    function sts=getSampleTimeImpl(obj)
        c=jsondecode(fileread(obj.ConfigPath));
        sts=createSampleTime(obj,'Type','Discrete','SampleTime',double(c.sample_time));
    end
    function [s1,s2]=getOutputSizeImpl(~)
        s1=[4 1];s2=[16 1];
    end
    function [a,b]=getOutputDataTypeImpl(~)
        a='double';b='double';
    end
    function [a,b]=isOutputComplexImpl(~)
        a=false;b=false;
    end
    function [a,b]=isOutputFixedSizeImpl(~)
        a=true;b=true;
    end
    function s=saveObjectImpl(obj)
        s=saveObjectImpl@matlab.System(obj);
        s.cfg=obj.cfg;s.mapping=obj.mapping;s.Bn=obj.Bn;
        s.center=obj.center;s.scale=obj.scale;
        s.belief=obj.belief;s.theta=obj.theta;
    end
    function loadObjectImpl(obj,s,wasLocked)
        if isfield(s,'cfg'),obj.cfg=s.cfg;end
        if isfield(s,'mapping'),obj.mapping=s.mapping;end
        if isfield(s,'Bn'),obj.Bn=s.Bn;end
        if isfield(s,'center'),obj.center=s.center;end
        if isfield(s,'scale'),obj.scale=s.scale;end
        if isfield(s,'belief'),obj.belief=s.belief;end
        if isfield(s,'theta'),obj.theta=s.theta;end
        loadObjectImpl@matlab.System(obj,s,wasLocked);
    end
end
methods(Access=private)
    function loadRuntimeConfig(obj)
        obj.cfg=jsondecode(fileread(obj.ConfigPath));
        obj.mapping=jsondecode(fileread(obj.MappingPath));
        assert(isfield(obj.cfg,'native_contract') && ...
            isfield(obj.mapping,'validated') && obj.mapping.validated, ...
            'AEFC:OnlineContract','Missing native contract and mapping');
        obj.center=double(obj.mapping.baseline_observation(:));
        B=double(obj.mapping.sensitivity_matrix);
        assert(isequal(size(B),[4 4]) && numel(obj.center)==4,...
            'AEFC:OnlineMapping','Four-speed paired Pref mapping required');
        obj.scale=zeros(4,1);
        for i=1:4
            reason=lower(char(obj.mapping.observation_edges(i).observation_reason));
            if contains(reason,'rotor-speed')
                obj.scale(i)=0.02;
            elseif contains(reason,'terminal-voltage')
                obj.scale(i)=0.10;
            elseif contains(reason,'rotor-angle')
                obj.scale(i)=0.35;
            else
                obj.scale(i)=max(0.02,0.10*max(abs(obj.center(i)),1e-3));
            end
        end
        obj.Bn=diag(1./obj.scale)*B;
    end
    function resetRuntimeState(obj)
        obj.belief=zeros(4,1);
        obj.theta=zeros(4,1);
    end
    function y=trimmedMean(~,X,f)
        n=size(X,2);
        assert(n>2*f,'AEFC:OnlineTrim','Insufficient updates');
        X=sort(X,2);
        if f>0,X=X(:,f+1:n-f);end
        y=mean(X,2);
    end
    function agg=robustAggregate(obj,X,f,k)
        med=median(X,2);
        [~,ord]=sort(abs(med),'descend');
        k=max(1,min(k,numel(med)));
        support=ord(1:k);
        agg=zeros(4,1);
        agg(support)=obj.trimmedMean(X(support,:),f);
    end
    function v=clipVec(~,v,lim)
        v=min(max(v,-lim),lim);
    end
end
end
