function result = run_pwb_case(configPath)
% RUN_PWB_CASE Explicit, isolated adapter to the unchanged IndoorEMT core.
% Paths in JSON are resolved relative to the JSON file. Output must be new.
% See docs/matlab_interface.md for verified scope and preserved failures.

configPath = char(java.io.File(char(configPath)).getCanonicalPath());
configDir = fileparts(configPath);
cfg = jsondecode(fileread(configPath));
required = {'case_id','sample_id','room_table','topology_table','output_dir', ...
    'frequency_hz','px2m','heights_m','door_is_open','tx_room_ids','tx_power_dbm'};
assert(all(isfield(cfg, required)), 'run_pwb_case:Config', 'Missing required configuration fields.');
assert(all(isfield(cfg.heights_m, {'wall','door','window'})), ...
    'run_pwb_case:Config', 'heights_m requires wall, door, window.');
roomFile = resolvePath(configDir, cfg.room_table);
topoFile = resolvePath(configDir, cfg.topology_table);
outDir = resolvePath(configDir, cfg.output_dir);
assert(isfile(roomFile) && isfile(topoFile), 'run_pwb_case:Inputs', 'Both input tables must exist.');
assert(~isfolder(outDir) && ~isfile(outDir), 'run_pwb_case:OutputExists', 'Output path already exists; choose a new directory.');

thisDir = fileparts(mfilename('fullpath'));
coreDir = fullfile(thisDir, 'core');
runtimeCoreIdentity = verify_core_identity();
previousPath = path;
pathCleanup = onCleanup(@() path(previousPath)); %#ok<NASGU>
addpath(coreDir, '-begin');
coreFunctions = {'roomWallSegments','computeRoomSelfLoss','computeRoomCouplings', ...
    'multi_layer_model','assemblePropagationMatrix','calculateRoomPowerLevels', ...
    'calculateReceivedPower','compute_coverage_loss_from_list'};
for k = 1:numel(coreFunctions)
    actual = char(java.io.File(which(coreFunctions{k})).getCanonicalPath());
    expected = char(java.io.File(fullfile(coreDir,[coreFunctions{k} '.m'])).getCanonicalPath());
    assert(strcmpi(actual, expected), 'run_pwb_case:ExternalModule', 'A core function was resolved outside the candidate core.');
end

frequency = double(cfg.frequency_hz(:));
px2m = double(cfg.px2m);
height_wall = double(cfg.heights_m.wall);
height_door = double(cfg.heights_m.door);
height_window = double(cfg.heights_m.window);
door_is_open = cfg.door_is_open;
assert(all(isfinite(frequency) & frequency > 0) && ~isempty(frequency), 'Invalid frequency_hz.');
assert(isfinite(px2m) && px2m > 0, 'Invalid px2m.');
assert(all(isfinite([height_wall height_door height_window])) && all([height_wall height_door height_window] > 0), 'Invalid heights_m.');
assert(islogical(door_is_open) && isscalar(door_is_open), 'door_is_open must be a JSON boolean.');

roomTbl = readtable(roomFile, 'Sheet', 'Rooms', 'VariableNamingRule', 'preserve');
topoTbl = readtable(topoFile, 'VariableNamingRule', 'preserve');
epsilonFile = fullfile(coreDir, 'epsilon_paper_tabel.txt');
epsilon_params = load(epsilonFile);
wideTbl = roomWallSegments(roomTbl, topoTbl);
roomIDs = wideTbl.RoomID;
tx_room_ids = double(cfg.tx_room_ids(:));
tx_power_dbm = double(cfg.tx_power_dbm(:));
assert(numel(unique(roomIDs)) == numel(roomIDs), 'RoomID values must be unique.');
assert(numel(unique(tx_room_ids)) == numel(tx_room_ids), 'Tx RoomID values must be unique.');
assert(numel(tx_room_ids) == numel(tx_power_dbm) && all(isfinite(tx_power_dbm)), 'Invalid Tx powers.');
[found,tx_rows] = ismember(tx_room_ids, roomIDs);
assert(all(found), 'run_pwb_case:TxMapping', 'A Tx RoomID is absent from the Rooms table.');
S_in_dBm = -inf(height(wideTbl),1);
S_in_dBm(tx_rows) = tx_power_dbm;

mkdir(outDir);
report = struct('status','running','case_id',cfg.case_id,'sample_id',cfg.sample_id, ...
    'matlab_version',version,'frequency_hz',frequency,'px2m',px2m, ...
    'heights_m',cfg.heights_m,'door_is_open',door_is_open, ...
    'tx_room_ids',tx_room_ids,'tx_rows',tx_rows,'tx_power_dbm',tx_power_dbm);
report.input_room_table_sha256 = fileSha256(roomFile);
report.input_topology_table_sha256 = fileSha256(topoFile);
report.epsilon_sha256 = fileSha256(epsilonFile);
report.algorithm_identity = 'current_IndoorEMT_unmodified_core';
report.core_sources = runtimeCoreIdentity;
report.fixed_source_settings = struct('ceiling_floor_absorption',false,'vertical_outside_coupling',false, ...
    'ceiling_floor_mid_thickness_m',0.12,'angular_samples',1000,'window_state','fixed_glass_model');
report.known_issues = {'WallDir_k is not read as ExtWallDir_k; exterior wall direction buckets remain unknown.', ...
    'Ceiling/floor effects remain disabled. Layer-width and door/window conventions await author confirmation.', ...
    'The unchanged assembler rejects a singleton frequency dimension. Public multifrequency examples use two distinct frequencies; no frequency is repeated automatically.', ...
    'Migration equivalence does not establish correctness or reproduce all submitted results.'};
writetable(wideTbl, fullfile(outDir,'room_wall_segments.csv'));
try
    [sigma_loss, roomIDs] = computeRoomSelfLoss(wideTbl, frequency, px2m, height_wall, epsilon_params, height_door, height_window, door_is_open);
    [sigma_cpl, sigma_diag, roomIDs2] = computeRoomCouplings(wideTbl, topoTbl, frequency, px2m, height_wall, height_door, height_window, epsilon_params, door_is_open);
    assert(all(isfinite(sigma_cpl(:)) & sigma_cpl(:) >= 0), 'sigma_cpl has negative or nonfinite entries.');
    assert(isequal(roomIDs, roomIDs2), 'RoomID order mismatch.');
    save(fullfile(outDir,'preassembly.mat'), 'roomIDs','wideTbl','frequency','sigma_loss','sigma_cpl','sigma_diag','S_in_dBm');
    M = assemblePropagationMatrix(sigma_loss, sigma_diag, sigma_cpl);
    E_V_per_m = calculateRoomPowerLevels(M, S_in_dBm);
    P_rx_dBm = calculateReceivedPower(E_V_per_m, frequency);
    result = struct('roomIDs',roomIDs,'frequency',frequency,'sigma_loss',sigma_loss, ...
        'sigma_cpl',sigma_cpl,'sigma_diag',sigma_diag,'M',M,'S_in_dBm',S_in_dBm, ...
        'E_V_per_m',E_V_per_m,'P_rx_dBm',P_rx_dBm,'wideTbl',wideTbl);
    save(fullfile(outDir,'results.mat'), '-struct','result');
    [roomRow,freqIndex] = ndgrid((1:numel(roomIDs)).', (1:numel(frequency)).');
    outputTable = table(roomIDs(roomRow(:)),freqIndex(:),frequency(freqIndex(:)),E_V_per_m(:),P_rx_dBm(:), ...
        'VariableNames',{'RoomID','FrequencyColumn','Frequency_Hz','E_V_per_m','ARP_dBm'});
    writetable(outputTable,fullfile(outDir,'room_power.csv'));
    % Existing evaluator is independent of solver correctness and uses row IDs.
    metricData = [frequency(freqIndex(:)),roomRow(:),P_rx_dBm(:)];
    [Qc,Lmean,Lvar,~,Ptot] = compute_coverage_loss_from_list(metricData,numel(roomIDs),tx_power_dbm);
    report.coverage_diagnostic = struct('Qc_dB',Qc,'mean_loss_dB',Lmean,'variance_loss_dB2',Lvar,'total_tx_dBm',Ptot);
    report.status = 'completed';
    report.scope = 'Configured tables and frequencies only; numerical equivalence requires a separate original-core comparison.';
    writeJson(fullfile(outDir,'run_report.json'),report);
    fprintf('PWB completed: %d rooms, %d frequency columns. Known issues remain; see run_report.json.\n',numel(roomIDs),numel(frequency));
catch failure
    report.status = 'failed';
    report.error_identifier = failure.identifier;
    report.error_message = failure.message;
    writeJson(fullfile(outDir,'run_report.json'),report);
    rethrow(failure);
end
end

function value = resolvePath(base, value)
item = java.io.File(char(value));
if ~item.isAbsolute(), item = java.io.File(base,char(value)); end
value = char(item.getCanonicalPath());
end

function value = fileSha256(pathValue)
fid = fopen(pathValue,'rb');
assert(fid >= 0, 'Cannot read file for hashing.');
cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
bytes = fread(fid,Inf,'*uint8');
digest = java.security.MessageDigest.getInstance('SHA-256');
digest.update(bytes);
value = lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2).',1,[]));
end

function writeJson(file, value)
fid = fopen(file,'w','n','UTF-8');
assert(fid >= 0, 'Cannot create report.');
cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s\n',jsonencode(value,'PrettyPrint',true));
end
