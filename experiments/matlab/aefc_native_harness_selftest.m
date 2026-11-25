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
    [p,v]=step(o,x);
    assert(isequal(size(p),[67 1]),'AEFC:PacketSize','Packet must have 67 fields');
    assert(isequal(size(v),[4 1]),'AEFC:AttackSize','Postattack vector must have four fields');
    assert(all(isfinite(p)) && all(isfinite(v)), ...
        'AEFC:HarnessFinite','Nonfinite harness output');
    for t=2:105
        [p,v]=step(o,x+0.00002*sin(t));
        assert(isequal(size(p),[67 1]) && isequal(size(v),[4 1]), ...
            'AEFC:HarnessDynamicDims','Wrong packet shape on %d',t);
        assert(all(isfinite(p)) && all(isfinite(v)));
    end
    release(o);
end
fprintf('OFFLINE ATTACK HARNESS DIRECT SELFTEST PASSED.\\n');
end
