function aefc_native_interval_observer_selftest
% Randomized conditional *12-state* inclusion test, four measured outputs.
% This is not an IEEE39 physical transition model. It tests an algorithm
% that may later consume a rigorously validated native linear/interval model.
rng(20261125);
n=12;m=4;p=4;
A=0.92*eye(n)+0.035/n*ones(n);
B=0.02*randn(n,m);
H=zeros(p,n);
H(1,1)=1;H(2,4)=1;H(3,7)=1;H(4,10)=1;
mdl=struct('A',A,'B',B,'c',zeros(n,1), ...
    'w_bound',0.003*ones(n,1), ...
    'input_attack_bound',0.015*ones(m,1), ...
    'H',H,'sensor_error',0.002*ones(p,1),...
    'full_state_dynamics_verified',true,...
    'measurement_map_verified',true);
tested=0;maxExcess=-inf;
for seed=1:80
    radius=0.05*ones(n,1);
    x=(2*rand(n,1)-1).*radius;
    state=struct('center',zeros(n,1),'error',radius,...
        'coverage_verified',true);
    assert(all(abs(x-state.center)<=state.error), ...
        'AEFC:ObserverInit','Initial interval invalid');
    for t=1:24
        u=0.025*randn(m,1);
        a=(2*rand(m,1)-1).*mdl.input_attack_bound;
        w=(2*rand(n,1)-1).*mdl.w_bound;
        x=A*x+B*(u+a)+w;
        y=H*x+(2*rand(p,1)-1).*mdl.sensor_error;
        [next,status,diagnostic]=aefc_native_interval_observer( ...
            state,mdl,u,y,struct('max_passes',4,'roundoff_inflation',1e-12));
        assert(status==1 && diagnostic.consistent && next.coverage_verified, ...
            'AEFC:ObserverTest','A true state was incorrectly excluded');
        excess=max(abs(x-next.center)-next.error);
        maxExcess=max(maxExcess,excess);
        assert(excess<=1e-9, ...
            'AEFC:ObserverTest','Full state escaped sound interval');
        assert(numel(next.center)==n && numel(next.error)==n);
        state=next;
        tested=tested+1;
    end
end
state.coverage_verified=false;
[~,status]=aefc_native_interval_observer(state,mdl,zeros(m,1),zeros(p,1),struct);
assert(status==-90,'AEFC:ObserverTest','Unverified initial set must fail closed');
state.coverage_verified=true;
mdl.measurement_map_verified=false;
[~,status]=aefc_native_interval_observer(state,mdl,zeros(m,1),zeros(p,1),struct);
assert(status==-90,'AEFC:ObserverTest','Unverified sensor map must fail closed');
mdl.measurement_map_verified=true;
bad=1e6*ones(p,1);
[~,status]=aefc_native_interval_observer(state,mdl,zeros(m,1),bad,struct);
assert(status==-93,'AEFC:ObserverTest','Physically impossible packet must be rejected');
fprintf('SOUND CONDITIONAL INTERVAL OBSERVER: %d random 12-state transitions, max inclusion excess %.6g; IEEE39 physical model not verified.\\n',tested,maxExcess);
end
