function report = aefc_r2022b_ci_entrypoint()
%AEFC_R2022B_CI_ENTRYPOINT GitHub-hosted migration/smoke entry point.
% Pre-stages the archive so initialization scripts populate the MATLAB base
% workspace before the conservative migration routine loads/compiles models.
archivePath='Figures/IEEE-39-bus-power.zip';
outDir='build/ieee39_r2022b';
preDir='build/ieee39_r2022b_prestage';
if exist(preDir,'dir'), rmdir(preDir,'s'); end
mkdir(preDir);
unzip(archivePath,preDir);
addpath(genpath(preDir));
files=[dir(fullfile(preDir,'**','*init*.m')); dir(fullfile(preDir,'**','*param*.m')); dir(fullfile(preDir,'**','*data*.m'))];
for k=1:numel(files)
    f=fullfile(files(k).folder,files(k).name);
    try
        evalin('base',sprintf('run(''%s'')',strrep(f,'''','''''')));
    catch ME
        fprintf(2,'INIT_SCRIPT_WARNING\t%s\t%s\n',f,ME.message);
    end
end
report=aefc_migrate_ieee39_r2022b(archivePath,outDir);
end
