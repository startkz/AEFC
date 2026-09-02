function aefc_ieee39_interface_discovery
% Discover candidate observation/control/fault interfaces in the native
% MathWorks IEEE39BusSystem example. This script does not guess an actuator
% mapping; it persists evidence that can be reviewed before enabling a
% closed-loop recovery experiment.
assert(~verLessThan('matlab','24.2'),'AEFC:ReleaseTooOld','R2024b required.');
model='IEEE39BusSystem';
try, load_system(model); catch, openExample('simscapeelectrical/IEEE39BusSystemExample'); load_system(model); end
repo=pwd; resDir=fullfile(repo,'results','ieee39_r2024b'); if ~exist(resDir,'dir'),mkdir(resDir);end
blocks=find_system(model,'LookUnderMasks','all','FollowLinks','on','Type','Block');
keys={'Measurements','Generator','AVR','Governor','Vref','Pref','Fault','Bus-16','Load'};
out=struct; out.model=model; out.release=version('-release'); out.mathworks_example=true; out.candidates=struct;
for k=1:numel(keys)
    hit={};
    for i=1:numel(blocks)
        if contains(lower(blocks{i}),lower(keys{k})), hit{end+1}=blocks{i}; end %#ok<AGROW>
    end
    name=matlab.lang.makeValidName(keys{k}); out.candidates.(name)=hit;
end
out.note='Discovery only: no control-channel injection point is assumed until candidate blocks are validated.';
writejson(fullfile(resDir,'interface_discovery.json'),out);
close_system(model,0);
end
function writejson(path,obj)
fid=fopen(path,'w'); assert(fid>0); c=onCleanup(@()fclose(fid)); fwrite(fid,jsonencode(obj,'PrettyPrint',true),'char'); fwrite(fid,sprintf('\n'),'char');
end
