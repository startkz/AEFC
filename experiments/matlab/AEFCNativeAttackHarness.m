classdef AEFCNativeAttackHarness < matlab.System
% OFFLINE ATTACK SOURCE. It alone receives scenario, seed, attack schedule.
% Real native rotor-speed observation goes to local trusted telemetry.
% Its packet contains only potentially adversarial messages, not
% attacker identities, clean trajectories or attack-on flags.
properties(Nontunable)
    ConfigPath = 'configs/ieee39_joint20.json'
    MappingPath = 'results/ieee39_r2024b/interface_mapping.json'
end
properties
    ScenarioCode = 1
    Seed = 0
    AttackScale = 1
end
properties(Access=private)
    cfg
    center
    scale
    stepCount
end
methods(Access=protected)
    function setupImpl(obj,~)
        obj.cfg=jsondecode(fileread(obj.ConfigPath));
        mapping=jsondecode(fileread(obj.MappingPath));
        assert(mapping.validated && numel(mapping.baseline_observation)==4, ...
            'AEFC:NativePacketMapping','Native four-channel mapping invalid');
        obj.center=double(mapping.baseline_observation(:));
        obj.scale=obj.deriveScale(mapping.observation_edges,obj.center);
        obj.stepCount=0;
    end
    function resetImpl(obj)
        obj.stepCount=0;
    end
    function [packet,uPost]=stepImpl(obj,obsPhysical)
        x=double(obsPhysical(:));
        assert(numel(x)==4 && all(isfinite(x)),'AEFC:NativePacketInput', ...
            'Native physical observation must contain four finite real channels.');
        z=(x-obj.center)./obj.scale;
        cfg=obj.cfg; t=obj.stepCount;
        n=double(cfg.clients);f=double(cfg.byzantine_clients);
        assert(n==7 && f==2,'AEFC:NativePacketShape', ...
            'Experiment packet layout frozen to seven clients and two Byzantine.');
        scenario=round(double(obj.ScenarioCode));
        attack=t>=cfg.attack_start_step && t<=cfg.attack_end_step;
        physical=(scenario==3 || scenario==4) && attack;
        knowledge=(scenario==2 || scenario==4) && attack;
        strength=max(0,double(obj.AttackScale));
        received=z;
        if physical
            received=received+strength*cfg.observation_attack_fraction_of_scale*obj.detNoise(t,97);
        end
        updates=zeros(4,n); evidence=zeros(4,n); ages=zeros(n,1);
        for j=1:n
            g=0.65*z+0.15*obj.detNoise(t,10+j);
            ev=-0.55*z+0.08*obj.detNoise(t,30+j);
            if knowledge && j<=f
                g=-strength*cfg.model_replacement_scale*g + 0.8*strength*obj.detNoise(t,50+j);
                ev=strength*cfg.model_replacement_scale*ev + 0.6*strength;
                ages(j)=cfg.stale_delay;
            end
            updates(:,j)=g;evidence(:,j)=ev;
        end
        packet=[received;updates(:);evidence(:);ages];
        uPost=zeros(4,1);
        if physical
            uPost=strength*cfg.post_shield_control_attack*obj.detNoise(t,211);
        end
        obj.stepCount=obj.stepCount+1;
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
