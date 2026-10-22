function wideTbl = roomWallSegments(roomTbl, topoTbl)
% ROOMWALLSEGMENTS
% 只记录几何段：Exterior / ExteriorDoor / ExteriorWindow /
%               Interior / InteriorDoor / InteriorWindow / InteriorOpening
% 不生成任何 Fill；外侧段记录方向 Dir（horizontal/vertical），内侧段 Dir=""。
%
% 输入：
%   roomTbl : Rooms sheet（至少包含）
%       RoomID | Type | Area | Perimeter |
%       ExtWallLength_k | ExtWallWidth_k | ExtWallDir_k(或 ExtWallDirection_k) |
%       OpenType_k | OpenLength_k | OpenWidth_k | OpenDir_k
%   topoTbl : topology sheet（至少包含）
%       RoomA | RoomB | ConnectionType ∈ {Wall,Door,Window,Opening} |
%       Length_k | Width_k
%
% 输出：
%   wideTbl : 宽表
%       RoomID | Type | Area_px | Perimeter_px |
%       WallType1 | WallDir1 | WallLength1_px | WallWidth1_px | ...
%       （外侧段的 WallDirk 为 'horizontal'/'vertical'；内侧段的 WallDirk 为空字符串）

    % ---------- 基本 ----------
    N = height(roomTbl);

    % ---------- 从 topoTbl 采集“内部”段（不含方向） ----------
    intMap = struct( ...
        'Wall',    containers.Map('KeyType','char','ValueType','any'), ...
        'Door',    containers.Map('KeyType','char','ValueType','any'), ...
        'Window',  containers.Map('KeyType','char','ValueType','any'), ...
        'Opening', containers.Map('KeyType','char','ValueType','any') );
    if ~isempty(topoTbl)
        vnamesT   = topoTbl.Properties.VariableNames;end
lenNamesT = vnamesT(startsWith(vnamesT, 'Length_'));
widNamesT = vnamesT(startsWith(vnamesT, 'Width_'));

% 数字后缀解析 + 交集（避免 1/10 字典序错位）
idsLenT = local_parse_nums(lenNamesT, 'Length_%d');
idsWidT = local_parse_nums(widNamesT, 'Width_%d');
idsK    = sort(intersect(idsLenT, idsWidT));

connType = lower(string(topoTbl.ConnectionType));

for i = 1:height(topoTbl)
    typ0 = strtrim(connType(i));                   % 'wall'|'door'|'window'|'opening'
    if ~ismember(typ0, ["wall","door","window","opening"]), continue; end

    % 仅当 RoomA/RoomB 都是有效房间时才视作“内部”
    ra = topoTbl.RoomA(i); rb = topoTbl.RoomB(i);
    if ~isfinite(ra) || ~isfinite(rb) || (ra<=0) || (rb<=0)
        continue; % 对外留给外侧或耦合函数处理
    end

    switch typ0
        case 'wall',    typKey = 'Wall';
        case 'door',    typKey = 'Door';
        case 'window',  typKey = 'Window';
        case 'opening', typKey = 'Opening';
    end

    roomsAB = [ra, rb];

    for rr = 1:numel(roomsAB)
        rid_key = char(string(roomsAB(rr)));
        if ~isKey(intMap.(typKey), rid_key), intMap.(typKey)(rid_key) = []; end
        for k = idsK(:).'
            L = double(topoTbl{i, sprintf('Length_%d', k)});
            W = double(topoTbl{i, sprintf('Width_%d',  k)});
            if isfinite(L) && isfinite(W) && L>0 && W>0
                intMap.(typKey)(rid_key) = [intMap.(typKey)(rid_key); L, W]; 
            end
        end
    end
end


    % ---------- 从 roomTbl 采集“外侧”段（含方向） ----------
    vnames = roomTbl.Properties.VariableNames;

    % 外墙列号集合
    lenNamesExt = vnames(startsWith(vnames, 'ExtWallLength_'));
    widNamesExt = vnames(startsWith(vnames, 'ExtWallWidth_'));
    idsExtL     = local_parse_nums(lenNamesExt, 'ExtWallLength_%d');
    idsExtW     = local_parse_nums(widNamesExt, 'ExtWallWidth_%d');
    idsExt      = sort(intersect(idsExtL, idsExtW));  % dir 在逐段时取

    % 对外门/窗列号集合
    typeNamesO  = vnames(startsWith(vnames, 'OpenType_'));
    lenNamesO   = vnames(startsWith(vnames, 'OpenLength_'));
    widNamesO   = vnames(startsWith(vnames, 'OpenWidth_'));
    idsOT       = local_parse_nums(typeNamesO, 'OpenType_%d');
    idsOL       = local_parse_nums(lenNamesO,  'OpenLength_%d');
    idsOW       = local_parse_nums(widNamesO,  'OpenWidth_%d');
    idsOpen     = sort(intersect(intersect(idsOT, idsOL), idsOW));

    % ---------- 逐房间拼装 ----------
    segData = cell(N,1);
    maxSeg  = 0;

    for i = 1:N
        rid_key = char(string(roomTbl.RoomID(i)));
        entries = {};  % {Type, L_px, W_px, Dir}

        % 外墙：逐段原样 + Dir（若缺失则 Dir=""）
        for k = idsExt(:).'
            L = roomTbl{i, sprintf('ExtWallLength_%d', k)};
            W = roomTbl{i, sprintf('ExtWallWidth_%d',  k)};
            if ~(isfinite(L) && isfinite(W) && L > 0 && W > 0), continue; end
            dirStr = try_get_dir(roomTbl, i, k, 'ExtWallDir_%d', 'ExtWallDirection_%d');
            entries = [entries; {"Exterior", double(L), double(W), dirStr}]; %#ok<AGROW>
        end

        % 外门/窗：逐段原样 + Dir（若缺失则 Dir=""）
        for k = idsOpen(:).'
            typVal = roomTbl{i, sprintf('OpenType_%d', k)};
            typStr = strtrim(string(typVal));   % 'Door'|'Window'|空
            if strlength(typStr) == 0 || ismissing(typStr), continue; end
            Lopen = roomTbl{i, sprintf('OpenLength_%d', k)};
            Wopen = roomTbl{i, sprintf('OpenWidth_%d',  k)};
            if ~(isfinite(Lopen) && isfinite(Wopen) && Lopen > 0 && Wopen > 0), continue; end
            dirStr = try_get_dir(roomTbl, i, k, 'OpenDir_%d', '');

            if strcmpi(typStr,'Door')
                entries = [entries; {"ExteriorDoor",  double(Lopen), double(Wopen), dirStr}]; %#ok<AGROW>
            elseif strcmpi(typStr,'Window')
                entries = [entries; {"ExteriorWindow", double(Lopen), double(Wopen), dirStr}]; %#ok<AGROW>
            end
        end

        % 内部：Wall/Door/Window/Opening（Dir=""）
        if isKey(intMap.Wall, rid_key)
            M = intMap.Wall(rid_key);
            for r = 1:size(M,1), entries = [entries; {"Interior",        M(r,1), M(r,2), ""}]; end %#ok<AGROW>
        end
        if isKey(intMap.Door, rid_key)
            M = intMap.Door(rid_key);
            for r = 1:size(M,1), entries = [entries; {"InteriorDoor",    M(r,1), M(r,2), ""}]; end %#ok<AGROW>
        end
        if isKey(intMap.Window, rid_key)
            M = intMap.Window(rid_key);
            for r = 1:size(M,1), entries = [entries; {"InteriorWindow",  M(r,1), M(r,2), ""}]; end %#ok<AGROW>
        end
        if isKey(intMap.Opening, rid_key)
            M = intMap.Opening(rid_key);
            for r = 1:size(M,1), entries = [entries; {"InteriorOpening", M(r,1), M(r,2), ""}]; end %#ok<AGROW>
        end

        segData{i} = entries;
        maxSeg = max(maxSeg, size(entries,1));
    end

    % ---------- 生成宽表（Type/Dir=string；Length/Width=double） ----------
    base = roomTbl(:, {'RoomID','Type','Area','Perimeter'});
    base.Properties.VariableNames = {'RoomID','Type','Area_px','Perimeter_px'};

    T = base;
    for k = 1:maxSeg
        T.(sprintf('WallType%d',      k)) = strings(N,1);
        T.(sprintf('WallDir%d',       k)) = strings(N,1);   % 外侧段有 H/V；内侧段为空
        T.(sprintf('WallLength%d_px', k)) = nan(N,1);
        T.(sprintf('WallWidth%d_px',  k)) = nan(N,1);
    end

    for i = 1:N
        entries = segData{i};
        for s = 1:size(entries,1)
            T.(sprintf('WallType%d',      s))(i) = string(entries{s,1});
            T.(sprintf('WallDir%d',       s))(i) = string(entries{s,4});
            T.(sprintf('WallLength%d_px', s))(i) = double(entries{s,2});
            T.(sprintf('WallWidth%d_px',  s))(i) = double(entries{s,3});
        end
    end

    % ---------- 删除完全空的段列（以类型列是否全空为准） ----------
    keep = true(1, width(T));
    for k = 1:maxSeg
        colType = T.( sprintf('WallType%d',k) );
        if all(colType == "" | ismissing(colType))
            vlist = { ...
                sprintf('WallType%d',      k), ...
                sprintf('WallDir%d',       k), ...
                sprintf('WallLength%d_px', k), ...
                sprintf('WallWidth%d_px',  k) ...
            };
            keep( ismember(T.Properties.VariableNames, vlist) ) = false;
        end
    end
    wideTbl = T(:, keep);
end

% ------- 小工具 -------
function nums = local_parse_nums(names, pattern)
    nums = [];
    if isempty(names), return; end
    names = cellstr(names);
    for ii = 1:numel(names)
        n = sscanf(names{ii}, pattern);
        if ~isempty(n), nums(end+1) = n; end %#ok<AGROW>
    end
end

function dirStr = try_get_dir(tbl, i, k, primaryFmt, secondaryFmt)
    dirStr = "";
    if ~isempty(primaryFmt)
        vn = sprintf(primaryFmt, k);
        if any(strcmp(tbl.Properties.VariableNames, vn))
            v = tbl{i, vn};
            if ~(isstring(v) || ischar(v)), v = string(v); end
            dirStr = string(lower(strtrim(v)));
        end
    end
    if dirStr=="" && ~isempty(secondaryFmt)
        vn = sprintf(secondaryFmt, k);
        if any(strcmp(tbl.Properties.VariableNames, vn))
            v = tbl{i, vn};
            if ~(isstring(v) || ischar(v)), v = string(v); end
            dirStr = string(lower(strtrim(v)));
        end
    end
    % 只接受 horizontal/vertical；其它置空
    if ~(dirStr=="horizontal" || dirStr=="vertical")
        dirStr = "";
    end
end
