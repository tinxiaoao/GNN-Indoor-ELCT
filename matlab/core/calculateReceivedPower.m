function P_rx_dBm = calculateReceivedPower(E_V_per_m, frequency_Hz)
% calculateReceivedPower - 从电场强度计算各房间接收功率 (dBm)
%
% 输入：
%   E_V_per_m     - 各房间电场强度矩阵 (NxF)，单位 V/m
%   frequency_Hz  - 仿真频率向量 (1xF)，单位 Hz
%
% 输出：
%   P_rx_dBm      - 各房间接收功率矩阵 (NxF)，单位 dBm

Z0 = 377;  % 自由空间波阻抗 (Ω)
c = 3e8;   % 光速 (m/s)

[N, F] = size(E_V_per_m);

% 初始化结果矩阵
P_rx_dBm = zeros(N, F);

for idx = 1:F
    % 计算当前频率的波长
    lambda = c / frequency_Hz(idx);
    
    % 有效接收面积 (Isotropic天线)
    A_e = lambda^2 / (4 * pi);

    % 当前频率下的功率密度
    S_W_m2 = (E_V_per_m(:, idx).^2) / Z0;

    % 计算接收功率 (W)
    P_rx_W = S_W_m2 * A_e;

    % 避免数值过小导致对数计算问题
    P_rx_W(P_rx_W <= 1e-20) = 1e-20;

    % 转换为 dBm
    P_rx_dBm(:, idx) = 10 * log10(P_rx_W / 1e-3);
end

end