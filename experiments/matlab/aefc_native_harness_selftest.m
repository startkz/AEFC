function aefc_native_harness_selftest
% Directly isolate MATLAB System dimension and packet contract before Simulink.
addpath('experiments/matlab');
cfg=jsondecode(fileread(fullfile(pwd,'configs','ieee39_unpriv_r1.json')));
mapping=jsondecode(fileread(fullfile(pwd,cfg.mapping_path)));
x=double(mapping.baseline_observation(:));
for scenario=1:4
    o=AEFCNativeAttackHarness;
    o.ScenarioCode=scenario;
    o.Seed=410;
    o.AttackScale=1;
    for trial=1:2
        if trial==2,reset(o);end
        physical_count=0;knowledge_count=0;
        for t=0:104
            [p,v]=step(o,x+0.00002*sin(t));
            assert(isequal(size(p),[67 1]) && isequal(size(v),[4 1]), ...
                'AEFC:HarnessDynamicDims','Wrong online packet or injection shape at %d',t);
            assert(all(isfinite(p)) && all(isfinite(v)), ...
                'AEFC:HarnessFinite','Nonfinite harness output');
            scheduled=t>=cfg.attack_start_step && t<=cfg.attack_end_step;
            activePhysical=scheduled && (scenario==3 || scenario==4);
            activeKnowledge=scheduled && (scenario==2 || scenario==4);
            gotPhysical=norm(v,inf)>1e-12;
            ages=p(61:67);
            gotKnowledge=any(ages>0);
            assert(gotPhysical==activePhysical, ...
                'AEFC:HarnessAttackWindow','Postshield attack schedule mismatch at step %d',t);
            assert(gotKnowledge==activeKnowledge, ...
                'AEFC:HarnessKnowledgeWindow','Model poisoning schedule mismatch at step %d',t);
            physical_count=physical_count+double(gotPhysical);
            knowledge_count=knowledge_count+double(gotKnowledge);
        end
        expectedCount=cfg.attack_end_step-cfg.attack_start_step+1;
        assert(physical_count==expectedCount*double(scenario==3 || scenario==4));
        assert(knowledge_count==expectedCount*double(scenario==2 || scenario==4));
    end
    release(o);
end
fprintf('OFFLINE ATTACK HARNESS DIRECT SELFTEST PASSED.\\n');
end
