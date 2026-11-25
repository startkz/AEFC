function aefc_ieee39_build_unprivileged
% Build SEPARATE IEEE39 native copy with isolated attacker System block.
% Legacy native original/model/560-run source remains available on base branch.
repo=pwd;
old='IEEE39BusSystem_AEFCNative';
fresh='IEEE39BusSystem_AEFCUnpriv';
res=fullfile(repo,'results','ieee39_r2024b');
if ~exist(res,'dir'),mkdir(res);end
oldFile=fullfile(res,[old '.slx']);
freshFile=fullfile(res,[fresh '.slx']);
% Existing official example resolution and tested causal instrumenter reused.
if exist(oldFile,'file')~=2
    aefc_ieee39_build_native_model;
end
if bdIsLoaded(old),close_system(old,0);end
if bdIsLoaded(fresh),close_system(fresh,0);end
load_system(oldFile);
save_system(old,freshFile);
try,close_system(old,0);catch,end
load_system(freshFile);
assert(bdIsLoaded(fresh),'AEFC:UnprivModel','New native model did not open');
obs=[fresh '/AEFC_OBS_MUX'];
ctrl=[fresh '/AEFC_NATIVE_CONTROLLER'];
attackDemux=[fresh '/AEFC_ATTACK_DEMUX'];
diagSink=[fresh '/AEFC_DIAG_TOWS'];
diagTerm=[fresh '/AEFC_DIAG_TERMINATOR'];
postSink=[fresh '/AEFC_POST_ATTACK_VECTOR_TOWS'];
% Restore original source paths in copy automatically by Simulink renaming.
ph=get_param(ctrl,'PortHandles');
assert(numel(ph.Outport)==3 && numel(ph.Inport)==1, ...
    'AEFC:UnprivOldPorts','Expected exactly one input and three old outputs');
for k=2:3
    ln=get_param(ph.Outport(k),'Line');
    if ln~=-1,delete_line(ln);end
end
% The original legacy controller System class is replaced IN THIS COPY.
set_param(ctrl,'System','AEFCNativeController');
try,set_param(ctrl,'ExploratoryMode','true','MethodCode','7');catch,end
harness=[fresh '/AEFC_NATIVE_ATTACK_SOURCE'];
add_block('simulink/User-Defined Functions/MATLAB System',harness, ...
    'System','AEFCNativeAttackHarness','SimulateUsing','Interpreted execution', ...
    'Position',[190 455 410 535]);
set_param(harness,'ScenarioCode','1','Seed','0','AttackScale','1');
set_param(fresh,'SimulationCommand','update');
ph=get_param(ctrl,'PortHandles');
ah=get_param(harness,'PortHandles');
omh=get_param(obs,'PortHandles');
assert(numel(ph.Inport)==2 && numel(ph.Outport)==2, ...
    'AEFC:UnprivControllerPorts','Expected two online inputs and two outputs');
assert(numel(ah.Inport)==1 && numel(ah.Outport)==2, ...
    'AEFC:UnprivAttackPorts','Expected one observed input and two offline outputs');
add_line(fresh,omh.Outport(1),ah.Inport(1),'autorouting','on');
add_line(fresh,ah.Outport(1),ph.Inport(2),'autorouting','on');
% Old shield output remains connected to original 4 Pref control paths.
add_line(fresh,ah.Outport(2),get_param(attackDemux,'PortHandles').Inport(1),'autorouting','on');
add_line(fresh,ah.Outport(2),get_param(postSink,'PortHandles').Inport(1),'autorouting','on');
add_line(fresh,ph.Outport(2),get_param(diagSink,'PortHandles').Inport(1),'autorouting','on');
add_line(fresh,ph.Outport(2),get_param(diagTerm,'PortHandles').Inport(1),'autorouting','on');
set_param(fresh,'ReturnWorkspaceOutputs','on');
save_system(fresh,freshFile);
audit=struct('model',fresh,'independent_model_file',freshFile, ...
    'separate_offline_attack_source',true,'online_controller_inputs',2, ...
    'trusted_local_channels',4,'untrusted_packet_length',67, ...
    'diagnostic_length',16,'full_state_certificate',false, ...
    'four_speed_surrogate_only',true, ...
    'original_plant_and_pref_edges_preserved',true);
fid=fopen(fullfile(res,'unprivileged_model_build.json'),'w');
assert(fid>0);fwrite(fid,jsonencode(audit,'PrettyPrint',true));fclose(fid);
close_system(fresh,0);
end
