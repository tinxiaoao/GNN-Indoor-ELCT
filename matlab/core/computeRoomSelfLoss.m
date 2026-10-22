function [sigma_loss, roomIDs] = computeRoomSelfLoss( ...
    wideTbl, frequency, px2m, height_wall, epsilon_params, ...
    height_door, height_window, door_is_open)
% 计算对角吸收项 A_i(f)，单位 m^2
% 规则：
%   - 外侧：按 (Dir∈{H,V,U}, Wpx) 分桶；同桶内做高度加权扣减（墙扣门/窗）；无 Open
%   - 内侧：按 (Wpx) 分桶；同桶内做高度加权扣减（墙扣门/窗）；Opening/开门 A=0
%   - multi_layer_model 已含 1/2 半空间因子 ⇒ 此处不再乘 0.5

roomIDs = wideTbl.RoomID;
N = height(wideTbl);
F = numel(frequency);
sigma_loss = zeros(N, F);

% 材料枚举（与 multi_layer_model 保持一致）
MAT_EXTERIOR    = 1;  % 外墙
MAT_INTERIOR    = 2;  % 内墙
MAT_CF          = 3;  % 顶/地
MAT_WINDOW      = 4;  % 窗
MAT_DOOR_CLOSED = 5;  % 关门

% 收集段索引 k
vn  = wideTbl.Properties.VariableNames;
tns = vn(startsWith(vn,'WallType'));
kList = [];
for ii = 1:numel(tns)
    n = sscanf(tns{ii}, 'WallType%d');
    if ~isempty(n), kList(end+1) = n; end
end
kList = sort(kList);

for i = 1:N
    row = wideTbl(i,:);

    % ---------- 外侧：Dir+W 桶 ----------
    D = struct();
    for d = ["H","V","U"]
        dk = char(d);
        D.(dk).wall = containers.Map('KeyType','double','ValueType','double');
        D.(dk).door = containers.Map('KeyType','double','ValueType','double');
        D.(dk).win  = containers.Map('KeyType','double','ValueType','double');
    end

    % ---------- 内侧：仅 W 桶 ----------
    int_wall = containers.Map('KeyType','double','ValueType','double');
    int_door = containers.Map('KeyType','double','ValueType','double');
    int_win  = containers.Map('KeyType','double','ValueType','double');
    % opening/开门：A=0，不聚合

    for k = kList
        tname = sprintf('WallType%d',      k);
        lname = sprintf('WallLength%d_px', k);
        wname = sprintf('WallWidth%d_px',  k);
        dname = sprintf('WallDir%d',       k);   % 方向列（外侧可能有）

        if ~all(ismember({tname,lname,wname}, vn)), continue; end
        wt = getStr(row{1,tname}); if strlength(wt)==0 || ismissing(wt), continue; end
        wtl = lower(strtrim(wt));

        Lpx = toNum(row{1,lname});
        Wpx = toNum(row{1,wname});
        if ~(isfinite(Lpx) && isfinite(Wpx) && Lpx>0 && Wpx>0), continue; end

        % 外侧才取方向；内侧不看方向
        dirKey = 'U';
        if ismember(dname, vn)
            ds = lower(strtrim(getStr(row{1,dname})));
            if ds=="horizontal", dirKey='H';
            elseif ds=="vertical", dirKey='V';
            end
        end

        switch wtl
            % ---- 外侧 ----
            case 'exterior'
                D.(dirKey).wall = add_len(D.(dirKey).wall, Wpx, Lpx);
            case 'exteriordoor'
                D.(dirKey).door = add_len(D.(dirKey).door, Wpx, Lpx);
            case 'exteriorwindow'
                D.(dirKey).win  = add_len(D.(dirKey).win,  Wpx, Lpx);

            % ---- 内侧 ----
            case 'interior'
                int_wall = add_len(int_wall, Wpx, Lpx);
            case 'interiordoor'
                int_door = add_len(int_door, Wpx, Lpx);
            case 'interiorwindow'
                int_win  = add_len(int_win,  Wpx, Lpx);

            case 'interioropening'
                % Open/开敞：A=0，不计自损耗
            otherwise
                error('computeRoomSelfLoss:UnknownType', ...
                      'Unknown WallType "%s" at RoomID=%s', wt, string(row.RoomID));
        end
    end

    % ===== 累计本房间吸收 ΣA_i(f) =====
    sig_room = zeros(1,F);

    % ---- 外侧：按每个方向桶做高度加权扣减（墙扣门/窗） ----
    for dk = {'H','V','U'}
        S = D.(dk{1});
        Wkeys = union_keys(S.wall, S.door, S.win);
        for m = 1:numel(Wkeys)
            Wpx = Wkeys(m);  Wm = Wpx * px2m;

            Lw = get_len(S.wall, Wpx);
            Ld = get_len(S.door, Wpx);
            Lh = get_len(S.win,  Wpx);

            Lw_eff_px = max(0, Lw - Ld*(height_door/height_wall) - Lh*(height_window/height_wall));
            if Lw_eff_px > 0
                area_m2 = (Lw_eff_px * px2m) * height_wall;
                res = multi_layer_model(frequency, MAT_EXTERIOR, Wm, epsilon_params);
                sig_room = sig_room + area_m2 .* (res.SUM_Solid_Angle_mean_R_T(:)).';
            end

            if (~door_is_open) && (Ld > 0)
                area_m2 = (Ld * px2m) * height_door;
                res = multi_layer_model(frequency, MAT_DOOR_CLOSED, Wm/4, epsilon_params);
                sig_room = sig_room + area_m2 .* (res.SUM_Solid_Angle_mean_R_T(:)).';
            end

            if Lh > 0
                area_m2 = (Lh * px2m) * height_window;
                res = multi_layer_model(frequency, MAT_WINDOW, Wm/4, epsilon_params);
                sig_room = sig_room + area_m2 .* (res.SUM_Solid_Angle_mean_R_T(:)).';
            end
        end
    end

    % ---- 内侧：按 W 桶做高度加权扣减（墙扣门/窗） ----
    Wkeys = union_keys(int_wall, int_door, int_win);
    for m = 1:numel(Wkeys)
        Wpx = Wkeys(m);  Wm = Wpx * px2m;

        Lw = get_len(int_wall, Wpx);
        Ld = get_len(int_door, Wpx);
        Lh = get_len(int_win,  Wpx);

        Lw_eff_px = max(0, Lw - Ld*(height_door/height_wall) - Lh*(height_window/height_wall));
        if Lw_eff_px > 0
            area_m2 = (Lw_eff_px * px2m) * height_wall;
            res = multi_layer_model(frequency, MAT_INTERIOR, Wm, epsilon_params);
            sig_room = sig_room + area_m2 .* (res.SUM_Solid_Angle_mean_R_T(:)).';
        end

        if (~door_is_open) && (Ld > 0)
            area_m2 = (Ld * px2m) * height_door;
            res = multi_layer_model(frequency, MAT_DOOR_CLOSED, Wm/4, epsilon_params);
            sig_room = sig_room + area_m2 .* (res.SUM_Solid_Angle_mean_R_T(:)).';
        end

        if Lh > 0
            area_m2 = (Lh * px2m) * height_window;
            res = multi_layer_model(frequency, MAT_WINDOW, Wm/4, epsilon_params);
            sig_room = sig_room + area_m2 .* (res.SUM_Solid_Angle_mean_R_T(:)).';
        end
    end

    % 顶 + 地（两面）
    enable_cf_absorption = false;   % true false
    if enable_cf_absorption
        area_room_m2 = double(wideTbl.Area_px(i)) * (px2m^2);
        S_cf         = 2 * area_room_m2;
        t_mid_cf     = 0.12;
        res_cf       = multi_layer_model(frequency, MAT_CF, t_mid_cf, epsilon_params);
        sigma_loss(i,:) = sig_room + S_cf .* (res_cf.SUM_Solid_Angle_mean_R_T(:)).';
    else
        sigma_loss(i,:) = sig_room;  % 关闭顶/地吸收，仅保留墙/门/窗吸收
    end
end
end

% ===== 小工具 =====
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
