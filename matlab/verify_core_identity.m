function identity = verify_core_identity
% VERIFY_CORE_IDENTITY Hash actual candidate core files before computation.
% The identity file is provenance metadata and never supplies solver values.
thisDir = fileparts(mfilename('fullpath'));
identity = jsondecode(fileread(fullfile(thisDir,'source_identity.json')));
for k = 1:numel(identity.modules)
    item = identity.modules(k);
    file = fullfile(thisDir,item.file);
    fid = fopen(file,'rb');
    assert(fid >= 0, 'verify_core_identity:MissingFile', 'A candidate core file is missing.');
    cleaner = onCleanup(@() fclose(fid));
    bytes = fread(fid,Inf,'*uint8');
    digest = java.security.MessageDigest.getInstance('SHA-256');
    digest.update(bytes);
    actual = lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2).',1,[]));
    clear cleaner;
    assert(strcmp(actual,item.candidate_sha256), 'verify_core_identity:ChangedFile', 'A candidate core file does not match its recorded source identity.');
    identity.modules(k).runtime_sha256 = actual;
    identity.modules(k).runtime_sha256_verified = true;
end
end
