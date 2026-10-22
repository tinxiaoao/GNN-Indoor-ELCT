function E_V_per_m = calculateRoomPowerLevels(M, P_in_dBm)
% 计算各房间稳态平均电场强度 (V/m)
% M: (N x N x F) 传播矩阵
% P_in_dBm: (N x 1) 或 (1 x N)，各房间输入功率(dBm)，频率无关

% 暂时关闭奇异性警告
warnState1 = warning('off', 'MATLAB:singularMatrix');
warnState2 = warning('off', 'MATLAB:nearlySingularMatrix');

Z0 = 377;  % 自由空间波阻抗 (Ω)

% 统一成列向量 N x 1
P_in_dBm = P_in_dBm(:);

% dBm -> W，-Inf 视为 0
P_in_W = 10.^((P_in_dBm - 30)/10);
P_in_W(isinf(P_in_W)) = 0;

[N, ~, F] = size(M);

S_out_W_m2 = zeros(N, F);
E_V_per_m  = zeros(N, F);

for fIdx = 1:F
    M_f = M(:, :, fIdx);

    % 解 M_f * S_out = P_in_W
    % 数值稳定性处理
    if rcond(M_f) < 1e-8
        % 病态/近奇异：用最小范数的广义解，数值更稳
        S = pinv(M_f) * P_in_W;
    else
        S = M_f \ P_in_W;
    end
    S(S < 0) = 0;         % 物理上功率密度不应为负；只做非负钳位
    S(S == 0) = realmin;  % 数值安全


    S_out_W_m2(:, fIdx) = S;
    E_V_per_m(:, fIdx)  = sqrt(S * Z0);
end

% 恢复原警告状态
warning(warnState1);
warning(warnState2);
end
