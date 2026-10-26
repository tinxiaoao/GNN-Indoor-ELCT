function [sigma_cpl, sigma_diag, roomIDs] = computeRoomCouplings( ...
    wideTbl, topoTbl, frequency, px2m, ...
    height_wall, height_door, height_window, ...
    epsilon_params, door_is_open)
% 室内/室外耦合：
%   - 外侧 i→Outside：按 (Dir ∈ {H,V,U}, Wpx) 分桶，高度加权扣减（墙扣门/窗），无 Open
%   - 内侧 i↔j：按 Wpx 分桶；墙扣门/窗；Opening 独立通道（T=1）
%
% ΣT = Area * res.SUM_Solid_Angle_mean_T （multi_layer_model 已含 1/2）
% Open/开门：ΣT = Area * 0.5

% 保持与上游一致的 RoomID 类型（数值或字符串）
roomIDs = wideTbl.RoomID;

N = numel(roomIDs);
F = numel(frequency);

sigma_cpl  = zeros(N,N,F);
sigma_diag = zeros(N,F);

% —— 新增：垂直对外耦合开关（默认开启）——
enable_vertical_outside = false;   % 顶/地向 outside 的 ΣT_iO true
t_mid_cf = 0.12;                  % 与 computeRoomSelfLoss 中保持一致

% 材料枚举
MAT_EXTERIOR    = 1;
MAT_INTERIOR    = 2;
MAT_CF   = 3;                     % 顶/地材料枚举（与 multi_layer_model 一致）
MAT_WINDOW      = 4;
MAT_DOOR_CLOSED = 5;

% RoomID -> index（键用字符串，兼容数值/分类）
id2idx = containers.Map('KeyType','char','ValueType','int32');
for i = 1:N
    id2idx(char(string(roomIDs(i)))) = int32(i);
end

%% ---------- 1) 外侧：T_{iO}，按 Dir+Wpx ----------
varNames  = wideTbl.Properties.VariableNames;
typeNames = varNames(startsWith(varNames,'WallType'));
% 稳定构造 kList（只收集存在的 k）
kList = [];
for ii = 1:numel(typeNames)
    n = sscanf(typeNames{ii}, 'WallType%d');
    if ~isempty(n), kList(end+1) = n; end %#ok<AGROW>
end
kList = sort(kList);

for i = 1:N
    row = wideTbl(i,:);

    % 三个方向桶：H/V/U（U=未知方向，不与 H/V 混桶）
    dirs = {'H','V','U'};
    S = struct();
    for d = 1:numel(dirs)
        dk = dirs{d};
        S.(dk).wall = containers.Map('KeyType','double','ValueType','double');
        S.(dk).door = containers.Map('KeyType','double','ValueType','double');
        S.(dk).win  = containers.Map('KeyType','double','ValueType','double');
    end

    for k = kList
        tname = sprintf('WallType%d',      k);
        dname = sprintf('WallDir%d',       k);
        lname = sprintf('WallLength%d_px', k);
        wname = sprintf('WallWidth%d_px',  k);
        if ~all(ismember({tname,lname,wname}, varNames)), continue; end

        wt = getStr(row{1,tname}); if strlength(wt)==0 || ismissing(wt), continue; end
        wtl = lower(strtrim(wt));

        Lpx = toNum(row{1,lname});
        Wpx = toNum(row{1,wname});
        if ~(isfinite(Lpx)&&isfinite(Wpx)&&Lpx>0&&Wpx>0), continue; end

        % 方向 -> H/V/U
        dirKey = 'U';
        if ismember(dname, varNames)
            ds = lower(strtrim(getStr(row{1,dname})));
            if ds=="horizontal", dirKey='H';
            elseif ds=="vertical", dirKey='V';
            end
        end

        switch wtl
            case 'exterior'
                S.(dirKey).wall = add_len(S.(dirKey).wall, Wpx, Lpx);
            case 'exteriordoor'
                S.(dirKey).door = add_len(S.(dirKey).door, Wpx, Lpx);
            case 'exteriorwindow'
                S.(dirKey).win  = add_len(S.(dirKey).win,  Wpx, Lpx);
            otherwise
                % 非外侧类型忽略（内侧/Opening）
        end
    end

    % 逐方向累加 T_iO
    TiO = zeros(1,F);
    for dk = {'H','V','U'}
        D = S.(dk{1});
        Wkeys = union_keys(D.wall, D.door, D.win);
        for m = 1:numel(Wkeys)
            Wpx = Wkeys(m);  Wm = Wpx * px2m;
            Lw  = get_len(D.wall, Wpx);
            Ld  = get_len(D.door, Wpx);
            Lh  = get_len(D.win,  Wpx);

            % 同一方向桶内做高度加权扣减
            Lw_eff = max(0, Lw - Ld*(height_door/height_wall) - Lh*(height_window/height_wall));

            % Exterior 有效墙
            if Lw_eff > 0
                area_m2 = (Lw_eff * px2m) * height_wall;
                res = multi_layer_model(frequency, MAT_EXTERIOR, Wm, epsilon_params);
                TiO = TiO + area_m2 .* (res.SUM_Solid_Angle_mean_T(:)).';
            end
            % Exterior 门
            if Ld > 0
                area_m2 = (Ld * px2m) * height_door;
                if door_is_open
                    TiO = TiO + 0.5 * area_m2 * ones(1,F);  % 开门：T=1 → Area/2
                else
                    res = multi_layer_model(frequency, MAT_DOOR_CLOSED, Wm/4, epsilon_params);
                    TiO = TiO + area_m2 .* (res.SUM_Solid_Angle_mean_T(:)).';
                end
            end
            % Exterior 窗
            if Lh > 0
                area_m2 = (Lh * px2m) * height_window;
                res = multi_layer_model(frequency, MAT_WINDOW, Wm/4, epsilon_params);
                TiO = TiO + area_m2 .* (res.SUM_Solid_Angle_mean_T(:)).';
            end
        end
    end

    sigma_diag(i,:) = sigma_diag(i,:) + TiO;
        % === ADD: ceiling/floor coupling to outside (默认开启) ===
    if enable_vertical_outside
        area_room_m2 = double(wideTbl.Area_px(i)) * (px2m^2);

        % 计算顶/地的 0.5*<T>（与 ΣA 的顶/地一致使用 MAT_CF、t_mid_cf）
        res_cf = multi_layer_model(frequency, MAT_CF, t_mid_cf, epsilon_params);
        T_half = (res_cf.SUM_Solid_Angle_mean_T(:)).';   % 1 x F  (= 0.5*<T>)

        % 顶 + 地 两面 → 向 outside 透射：ΣT_iO += (A_ceiling + A_floor) * 0.5*<T>
        % 其中 A_ceiling = A_floor = area_room_m2
        TiO_vertical = 2 * area_room_m2 .* T_half;       % 1 x F

        sigma_diag(i,:) = sigma_diag(i,:) + TiO_vertical;
    end

end

%% ---------- 2) 内侧：T_{ij}（按 Wpx；不使用方向） ----------
pairAgg = containers.Map('KeyType','char','ValueType','any');

if ~isempty(topoTbl)
    vnamesT = topoTbl.Properties.VariableNames;
    lenMask = startsWith(vnamesT, 'Length_');
    widMask = startsWith(vnamesT, 'Width_');
    connType = lower(string(topoTbl.ConnectionType));

    for r = 1:height(topoTbl)
        typ = strtrim(connType(r));
        if ~ismember(typ, ["wall","door","window","opening"]), continue; end

        ra = string(topoTbl.RoomA(r));
        rb = string(topoTbl.RoomB(r));
        if ~(isKey(id2idx, char(ra)) && isKey(id2idx, char(rb))), continue; end
        ia = double(id2idx(char(ra)));
        ib = double(id2idx(char(rb)));
        if ia == ib, continue; end

        if ia < ib, key = sprintf('%d|%d', ia, ib);
        else,       key = sprintf('%d|%d', ib, ia);
        end

        Ls = table2array(topoTbl(r, lenMask));
        Ws = table2array(topoTbl(r, widMask));

        if ~isKey(pairAgg, key)
            S = struct();
            S.wall = containers.Map('KeyType','double','ValueType','double');
            S.door = containers.Map('KeyType','double','ValueType','double');
            S.win  = containers.Map('KeyType','double','ValueType','double');
            S.open = containers.Map('KeyType','double','ValueType','double');
            pairAgg(key) = S;
        else
            S = pairAgg(key);
        end

        for k = 1:numel(Ls)
            Lpx = double(Ls(k)); Wpx = double(Ws(k));
            if ~(isfinite(Lpx)&&isfinite(Wpx)&&Lpx>0&&Wpx>0), continue; end
            switch typ
                case 'wall',    S.wall = add_len(S.wall, Wpx, Lpx);
                case 'door',    S.door = add_len(S.door, Wpx, Lpx);
                case 'window',  S.win  = add_len(S.win,  Wpx, Lpx);
                case 'opening', S.open = add_len(S.open, Wpx, Lpx);
            end
        end
        pairAgg(key) = S;
    end
end

% 对每个房间对，构造 T_ij 并对称写入
Pkeys = pairAgg.keys;
for p = 1:numel(Pkeys)
    key = Pkeys{p};
    ab  = sscanf(key, '%d|%d');  ia = ab(1); ib = ab(2);
    S   = pairAgg(key);
    Wkeys = union_keys(S.wall, S.door, S.win, S.open);
    Tij = zeros(1,F);

    for m = 1:numel(Wkeys)
        Wpx = Wkeys(m);  Wm = Wpx * px2m;
        Lw = get_len(S.wall, Wpx);
        Ld = get_len(S.door, Wpx);
        Lh = get_len(S.win,  Wpx);
        Lo = get_len(S.open, Wpx);

        Lw_eff = max(0, Lw - Ld*(height_door/height_wall) - Lh*(height_window/height_wall));

        % 内墙（有效墙）
        if Lw_eff > 0
            area_m2 = (Lw_eff * px2m) * height_wall;
            res = multi_layer_model(frequency, MAT_INTERIOR, Wm, epsilon_params);
            Tij = Tij + area_m2 .* (res.SUM_Solid_Angle_mean_T(:)).';
        end
        % 内门（开/关）
        if Ld > 0
            area_m2 = (Ld * px2m) * height_door;
            if door_is_open
                Tij = Tij + 0.5 * area_m2 * ones(1,F);   % 开门：T=1
            else
                res = multi_layer_model(frequency, MAT_DOOR_CLOSED, Wm/4, epsilon_params);
                Tij = Tij + area_m2 .* (res.SUM_Solid_Angle_mean_T(:)).';
            end
        end
        % 内窗
        if Lh > 0
            area_m2 = (Lh * px2m) * height_window;
            res = multi_layer_model(frequency, MAT_WINDOW, Wm/4, epsilon_params);
            Tij = Tij + area_m2 .* (res.SUM_Solid_Angle_mean_T(:)).';
        end
        % 开敞（Open）
        if Lo > 0
            area_m2 = (Lo * px2m) * height_wall;   % H_open = H_wall
            Tij = Tij + 0.5 * area_m2 * ones(1,F); % T=1 → Area/2
        end
    end

    % —— 稳定的 1×1×F 写法（避免 squeeze 隐式扩展）——
    Tij3 = reshape(Tij, 1, 1, F);
    sigma_cpl(ia,ib,:) = sigma_cpl(ia,ib,:) + Tij3;
    sigma_cpl(ib,ia,:) = sigma_cpl(ia,ib,:);
end

% ΣT 行和：加上室内 Σ_j T_ij
for i = 1:N
    Ti_sum = sum(sigma_cpl(i,[1:i-1,i+1:N],:), 2);  % 1×1×F
    Ti_sum = reshape(Ti_sum, 1, F);                 % 1×F
    sigma_diag(i,:) = sigma_diag(i,:) + Ti_sum;     % 1×F
end

% 保险：强制对角为 0（防后续维护误写）
for f = 1:F
    A = sigma_cpl(:,:,f);
    A(1:N+1:end) = 0;
    sigma_cpl(:,:,f) = A;
end

end

% --------- 小工具 ---------
function m = add_len(m, Wpx, Lpx)
if isKey(m, Wpx), m(Wpx) = m(Wpx) + Lpx; else, m(Wpx) = Lpx; end
end

function L = get_len(m, Wpx)
if isKey(m, Wpx), L = m(Wpx); else, L = 0; end
end

function keys_out = union_keys(varargin)
S = [];
for k = 1:numel(varargin)
    if ~isempty(varargin{k})
        S = [S, cell2mat(keys(varargin{k}))];
    end
end
keys_out = unique(S);
end

function s = getStr(x)
if iscell(x), x = x{1}; end
s = string(x);
end

function d = toNum(x)
if iscell(x), x = x{1}; end
if isstring(x) || ischar(x)
    d = str2double(string(x));
else
    d = double(x);
end
end
