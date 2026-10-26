function M = assemblePropagationMatrix(sigma_loss, sigma_diag, sigma_cpl, eps_reg)
% ASSEMBLEPROPAGATIONMATRIX
% 装配 EMT/PWB 传播矩阵：
%   M(:,:,f) = diag( sigma_loss(:,f) + sigma_diag(:,f) + eps_reg ) - sigma_cpl(:,:,f)
% 其中：
%   - sigma_loss [N x F]     ：各房间吸收截面 ΣA（已含 1/2）
%   - sigma_diag [N x F]     ：各房间 ΣT 行和（含对外 ΣT_iO；已含 1/2）
%   - sigma_cpl  [N x N x F] ：房间间耦合 ΣT_ij，i≠j（已含 1/2）
%   - eps_reg (可选)         ：对角正则（默认 0）
%
% 输出：
%   - M [N x N x F]
%
% 能量平衡（对频点 f）：
%   (A_i + sum_j T_ij + T_iO) * S_i  -  sum_j T_ij * S_j  =  P_in_i
%
% 行和检查：
%   sum_j M(i,j,f) == sigma_loss(i,f) + T_iO(f), 其中 T_iO = sigma_diag - sum_j T_ij

if nargin < 4, eps_reg = 0; end

% 尺寸检查
[N, F] = size(sigma_loss);
if ~isequal(size(sigma_diag), [N, F])
    error('assemblePropagationMatrix:SizeMismatch', 'sigma_diag size mismatch.');
end
sz = size(sigma_cpl);
if numel(sz) ~= 3 || sz(1) ~= N || sz(2) ~= N || sz(3) ~= F
    error('assemblePropagationMatrix:SizeMismatch', 'sigma_cpl size mismatch.');
end

M = zeros(N, N, F);

for f = 1:F
    T = double(sigma_cpl(:,:,f));
    % 保险起见：强制清零对角，确保只在 diag(...) 里计入行和
    T(1:N+1:end) = 0;

    d = double(sigma_loss(:,f)) + double(sigma_diag(:,f));
    if eps_reg ~= 0
        d = d + eps_reg;
    end

    M(:,:,f) = diag(d) - T;
end
end
