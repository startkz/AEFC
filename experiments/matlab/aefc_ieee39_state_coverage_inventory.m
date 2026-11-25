function aefc_ieee39_state_coverage_inventory
% Offline discovery of state logging in the ORIGINAL native IEEE39 model.
% No logged simulator state is fed to the online controller.
% A full state logging inventory would still NOT prove trusted online
% observer coverage or robust nonlinear dynamics/hold-interval bounds.
repo=pwd;cfg=jsondecode(fileread(fullfile(repo,'configs','ieee39_unpriv_r1.json')));
model=char(cfg.model);
fp=fullfile(repo,'results','ieee39_r2024b',[model '.slx']);
assert(exist(fp,'file')==2,'AEFC:StateInventory','Unprivileged model missing');
load_system(fp);
info=struct('model',model,'source','Simulink state logging only', ...
    'online_trusted_observations',4,'full_state_online_coverage',false,...
    'verified_full_state_observer',false,'verified_model_error_tube',false, ...
    'warning','Offline simulator states are not online physical measurements or a certified state observer');
try
    set_param(model,'SaveState','on','StateSaveName','AEFC_NATIVE_XOUT', ...
        'SaveFormat','Dataset','ReturnWorkspaceOutputs','on');
    in=Simulink.SimulationInput(model);
    in=in.setBlockParameter([model '/AEFC_NATIVE_CONTROLLER'], ...
        'MethodCode','8','ExploratoryMode','false');
    in=in.setBlockParameter([model '/AEFC_NATIVE_ATTACK_SOURCE'], ...
        'ScenarioCode','1','Seed','0','AttackScale','1');
    in=in.setModelParameter('StopTime','0.1');
    out=sim(in);
    x=[];
    try,x=out.get('AEFC_NATIVE_XOUT');catch,end
    info.saved_state_available=~isempty(x);
    info.logged_elements=0;
    info.element_info={};
    if isa(x,'Simulink.SimulationData.Dataset')
        info.logged_elements=x.numElements;
        records=cell(x.numElements,1);
        for k=1:x.numElements
            element=x.getElement(k);
            nm='';try,nm=char(element.Name);catch,end
            shape=[];try,shape=size(element.Values.Data);catch,end
            records{k}=struct('name',nm,'recorded_shape',shape);
        end
        info.element_info=records;
    end
catch ME
    info.saved_state_available=false;
    info.state_logging_error=ME.message;
end
outdir=fullfile(repo,'results','ieee39_unpriv_r1');
if ~exist(outdir,'dir'),mkdir(outdir);end
path=fullfile(outdir,'state_coverage_inventory.json');
fid=fopen(path,'w');
assert(fid>0,'AEFC:StateInventory','Cannot write inventory');
fwrite(fid,jsonencode(info,'PrettyPrint',true));
fwrite(fid,sprintf('\n'));
fclose(fid);
try,set_param(model,'SaveState','off');catch,end
close_system(model,0);
end
