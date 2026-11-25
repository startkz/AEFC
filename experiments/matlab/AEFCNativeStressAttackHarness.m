classdef AEFCNativeStressAttackHarness < matlab.System
% OFFLINE, EXPLORATORY PHYSICAL PRESSURE source. Independent of original P0.
% The signed held Pref perturbation deliberately spans a separate noncertified
% stress envelope. It MUST NOT be presented as covered by the original
% postshield certified-upper-bound 0.024 or IEEE39 full safety proof.
% OFFLINE ATTACK SOURCE. It alone receives scenario, seed, attack schedule.
% Real native rotor-speed observation goes to local trusted telemetry.
% Its packet contains only potentially adversarial messages, not
% attacker identities, clean trajectories or attack-on flags.
properties(Nontunable)
    ConfigPath = 'configs/ieee39_unpriv_r1.json'
    MappingPath = 'results/ieee39_r2024b/interface_mapping.json'
end
properties
    ScenarioCode = 1
    Seed = 0
    AttackScale = 1
    StressAmplitude = 0.024
end
properties(Access=private)
    cfg
    center
    scale
    stepCount
end
methods(Access=protected)
    function setupImpl(obj,~)
        obj.loadRuntimeConfig();
        obj.stepCount=0;
    end
    function resetImpl(obj)
        if ~isstruct(obj.cfg) || numel(obj.center)~=4 || numel(obj.scale)~=4
            obj.loadRuntimeConfig();
        end
        obj.stepCount=0;
    end
    function [packet,uPost]=stepImpl(obj,obsPhysical)
        % Simulink Fast Restart may instantiate an interpreted System block
        % without preserving private runtime fields from an earlier compile.
        % Initialize lazily and retain the attack window counter per episode.
        if ~isstruct(obj.cfg) || numel(obj.center)~=4 || numel(obj.scale)~=4
            obj.loadRuntimeConfig();
        end
        % Every stage is dimension checked so Simulink runtime failures
        % produce falsifiable diagnostics instead of opaque size errors.
        phase='input';
        try
            x=double(obsPhysical(:));
            ctr=double(obj.center(:)); scl=double(obj.scale(:));
            assert(numel(x)==4 && numel(ctr)==4 && numel(scl)==4, ...
                'AEFC:HarnessDim','Input/center/scale must all have 4 elements');
            assert(all(isfinite(x)) && all(isfinite(ctr)) && ...
                all(isfinite(scl)) && all(scl>0), ...
                'AEFC:HarnessFinite','Invalid physical input or mapping');
            z=(x-ctr)./scl;
            cfg=obj.cfg;t=double(obj.stepCount);
            n=round(double(cfg.clients));f=round(double(cfg.byzantine_clients));
            assert(n==7 && f==2,'AEFC:NativePacketShape', ...
                'Expected 7 clients and 2 Byzantine in offline generator');
            scenario=round(double(obj.ScenarioCode));
            active=t>=double(cfg.attack_start_step) && t<=double(cfg.attack_end_step);
            physical=(scenario==3 || scenario==4) && active;
            knowledge=(scenario==2 || scenario==4) && active;
            strength=max(0,double(obj.AttackScale));
            phase='received_observation';
            received=z;
            if physical
                noise=obj.detNoise(t,97);noise=double(noise(:));
                assert(numel(noise)==4,'AEFC:HarnessNoiseShape','Observation noise wrong dimension');
                received=z+strength*double(cfg.observation_attack_fraction_of_scale)*noise;
            end
            phase='client_generation';
            updates=zeros(4,n);evidence=zeros(4,n);ages=zeros(n,1);
            for j=1:n
                noise_g=double(obj.detNoise(t,10+j));noise_g=noise_g(:);
                noise_e=double(obj.detNoise(t,30+j));noise_e=noise_e(:);
                assert(numel(noise_g)==4 && numel(noise_e)==4, ...
                    'AEFC:HarnessNoiseShape','Client noise vector wrong dimension');
                g=0.65*z+0.15*noise_g;
                ev=-0.55*z+0.08*noise_e;
                if knowledge && j<=f
                    noise_a=double(obj.detNoise(t,50+j));noise_a=noise_a(:);
                    assert(numel(noise_a)==4,'AEFC:HarnessNoiseShape','Attack noise vector wrong dimension');
                    g=-strength*double(cfg.model_replacement_scale)*g + ...
                        0.8*strength*noise_a;
                    ev=strength*double(cfg.model_replacement_scale)*ev+0.6*strength;
                    ages(j)=double(cfg.stale_delay);
                end
                updates(:,j)=g;evidence(:,j)=ev;
            end
            phase='packet_assembly';
            packet=[received(:);updates(:);evidence(:);ages(:)];
            assert(isequal(size(packet),[67 1]) && all(isfinite(packet)), ...
                'AEFC:HarnessPacket','Expected finite [67 1] receiver packet');
            phase='post_shield_attack';
            uPost=zeros(4,1);
            if physical
                % Frozen per-seed signed held Pref attack from t=start..end.
                % Opposite to sinusoidal original attack: nonzero net
                % mechanical energy over the whole 75-step window.
                amp=double(obj.StressAmplitude);
                assert(isfinite(amp) && amp>=0 && amp<=0.24, ...
                    'AEFC:StressEnvelope','Exploratory Pref amplitude must be in [0,0.24]');
                signs=double(obj.detNoise(0,211));signs=signs(:);
                assert(numel(signs)==4,'AEFC:StressDimension','Four Pref signs required');
                uPost=amp*sign(signs);
            end
            assert(isequal(size(uPost),[4 1]) && all(isfinite(uPost)), ...
                'AEFC:HarnessPost','Expected finite [4 1] post-shield corruption');
            obj.stepCount=t+1;
        catch ME
            error('AEFC:HarnessStage', ...
                'Offline harness failed in phase %s, native input size=%s, center=%s, scale=%s; cause: %s', ...
                phase,mat2str(size(obsPhysical)),mat2str(size(obj.center)), ...
                mat2str(size(obj.scale)),ME.message);
        end
    end
    function s=saveObjectImpl(obj)
        s=saveObjectImpl@matlab.System(obj);
        s.cfg=obj.cfg;
        s.center=obj.center;
        s.scale=obj.scale;
        s.stepCount=obj.stepCount;
    end
    function loadObjectImpl(obj,s,wasLocked)
        if isfield(s,'cfg'),obj.cfg=s.cfg;end
        if isfield(s,'center'),obj.center=s.center;end
        if isfield(s,'scale'),obj.scale=s.scale;end
        if isfield(s,'stepCount'),obj.stepCount=s.stepCount;end
        loadObjectImpl@matlab.System(obj,s,wasLocked);
        if ~isstruct(obj.cfg) || numel(obj.center)~=4 || numel(obj.scale)~=4
            obj.loadRuntimeConfig();
        end
    end
    function sts=getSampleTimeImpl(obj)
        c=jsondecode(fileread(obj.ConfigPath));
        sts=createSampleTime(obj,'Type','Discrete','SampleTime',double(c.sample_time));
    end
    function [a,b]=getOutputSizeImpl(~)
        a=[67 1]; b=[4 1];
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
end
methods(Access=private)
    function loadRuntimeConfig(obj)
        obj.cfg=jsondecode(fileread(obj.ConfigPath));
        mapping=jsondecode(fileread(obj.MappingPath));
        assert(mapping.validated && numel(mapping.baseline_observation)==4, ...
            'AEFC:NativePacketMapping','Causal 4-speed mapping invalid');
        obj.center=double(mapping.baseline_observation(:));
        obj.scale=obj.deriveScale(mapping.observation_edges,obj.center);
        assert(all(isfinite(obj.scale)) && all(obj.scale>0), ...
            'AEFC:NativePacketScale','Positive normalized speed scales required');
        if isempty(obj.stepCount),obj.stepCount=0;end
    end
    function v=detNoise(obj,t,salt)
        idx=(1:4)';
        v=sin((idx+salt)*(t+1)*0.731 + (double(obj.Seed)+1)*0.193+salt*0.017);
        v=v/max(norm(v,inf),1e-12);
    end
    function s=deriveScale(~,edges,center)
        s=zeros(4,1);
        for i=1:4
            reason=lower(char(edges(i).observation_reason));
            if contains(reason,'rotor-speed')
                s(i)=0.02;
            elseif contains(reason,'terminal-voltage')
                s(i)=0.10;
            elseif contains(reason,'rotor-angle')
                s(i)=0.35;
            else
                s(i)=max(0.02,0.10*max(abs(center(i)),1e-3));
            end
        end
    end
end
end
