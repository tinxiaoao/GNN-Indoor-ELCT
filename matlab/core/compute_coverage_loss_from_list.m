function [Qc_dB, L_mean_dB, L_var_dB2, L_dB, Ptot_dBm, ARP_mat_dBm, freqList] = ...
    compute_coverage_loss_from_list(data, numRooms, PTx_dBm)
% compute_coverage_loss_from_list
%   输入为 N×3 的列表形式: [freq_GHz, room_id, ARP_dBm]
%   以及每个 Tx 的发射功率 PTx_dBm (dBm)，
%   自动整理为 K×F 矩阵并计算 coverage-loss 指标。
%
% 输入:
%   data      : N×3 矩阵
%               第1列: 频率 (任意单位, 只用于区分)
%               第2列: 房间编号 (1..K)
%               第3列: ARP_dBm, 该房间该频率下的平均接收功率 (dBm)
%
%   numRooms  : K, 房间总数
%
%   PTx_dBm   : 每个 Tx 的发射功率 (dBm)
%               允许格式:
%               - 标量        : 单 Tx，所有频点相同功率
%               - 1×F         : 单 Tx，不同频点不同功率
%               - NTx×1       : 多 Tx，各 Tx 所有频点相同功率
%               - NTx×F       : 多 Tx，各频点功率可不同
%
% 输出:
%   Qc_dB      : 1×F, coverage-loss 指标 (dB)
%   L_mean_dB  : 1×F, 平均路径损耗 (dB)
%   L_var_dB2  : 1×F, 路径损耗方差 (dB^2)
%   L_dB       : K×F, 房间级路径损耗 (dB)
%   Ptot_dBm   : 1×F, 总发射功率 (dBm)，由 PTx_dBm 在线性域自动计算
%   ARP_mat_dBm: K×F, 房间×频点的 ARP 矩阵 (dBm)
%   freqList   : 1×F, 频率列表，与列对应

    % -------- 1. 拆分输入列 --------
    if size(data,2) ~= 3
        error('data 必须是 N×3: [freq, room_id, ARP_dBm].');
    end

    freqCol  = data(:,1);
    roomCol  = data(:,2);
    arpCol   = data(:,3);

    K = numRooms;

    if any(roomCol < 1) || any(roomCol > K)
        error('room_id 超出 1..numRooms 范围。');
    end

    % -------- 2. 找出所有频率并保持原始顺序 --------
    freqList = unique(freqCol, 'stable');
    F = numel(freqList);

    % -------- 3. 初始化 ARP 矩阵 K×F --------
    ARP_mat_dBm = nan(K, F);

    for n = 1:size(data,1)
        f_val   = freqCol(n);
        k_id    = roomCol(n);
        arp_val = arpCol(n);

        f_idx = find(freqList == f_val, 1, 'first');
        if isempty(f_idx)
            error('无法在 freqList 中找到频率 %.4g。', f_val);
        end

        ARP_mat_dBm(k_id, f_idx) = arp_val;
    end

    if any(isnan(ARP_mat_dBm), 'all')
        warning('ARP 矩阵中存在 NaN，请检查是否所有 (房间, 频率) 都有数据。');
    end

    % -------- 4. 处理 PTx_dBm，在线性域求和 -> Ptot_dBm --------
    % 目标是得到: Ptot_dBm (1×F)
    if isscalar(PTx_dBm)
        % 单 Tx，所有频点同功率
        Ptot_dBm = PTx_dBm * ones(1, F);  % 先当作单 Tx
    else
        [NTx_raw, Ftx_raw] = size(PTx_dBm);

        if NTx_raw == 1 && Ftx_raw == F
            % 1×F: 单 Tx，各频点不同功率
            P_lin_mW = 10.^(PTx_dBm/10);  % 1×F
            Ptot_lin_mW = P_lin_mW;       % 只有一个 Tx
            Ptot_dBm = 10*log10(Ptot_lin_mW);
        else
            % 多 Tx 情况
            if Ftx_raw == 1 && F > 1
                % NTx×1: 各 Tx 所有频点同功率 → 复制成 NTx×F
                PTx_dBm = repmat(PTx_dBm, 1, F);
            elseif Ftx_raw ~= F
                error('PTx_dBm 维度不合法：多 Tx 时列数必须为 1 或 F。');
            end
            % 现在是 NTx×F
            P_lin_mW = 10.^(PTx_dBm/10);     % 线性功率
            Ptot_lin_mW = sum(P_lin_mW, 1);  % 对 Tx 求和 -> 1×F
            Ptot_dBm = 10*log10(Ptot_lin_mW);
        end
    end


    % -------- 5. 房间级路径损耗 (dB) --------
    L_dB = Ptot_dBm - ARP_mat_dBm;          % K×F

    % -------- 6. 平均路径损耗 (dB) --------
    L_mean_dB = mean(L_dB, 1);              % 1×F

    % -------- 7. dB 域方差 (dB^2) --------
    L_centered_dB = L_dB - L_mean_dB;
    L_var_dB2     = mean(L_centered_dB.^2, 1);

    % -------- 8. coverage-loss 指标 Qc (dB) --------
    Qc_dB = sqrt(mean(L_dB.^2, 1));
end
