function result = multi_layer_model(frequency, wall_type, t_mid, epsTab)
% MULTI_LAYER_MODEL  3-layer slab under oblique incidence (Balanis §5.4.4 风格)
% 输出两组值：
%   1) mean_R, mean_T, mean_A  —— 半球归一化方向平均 <·> ∈ [0,1]
%   2) SUM_Solid_Angle_mean_R   = 0.5 * mean_R   （已含“只有半空间朝向墙”的 1/2 因子）
%      SUM_Solid_Angle_mean_T   = 0.5 * mean_T
%      SUM_Solid_Angle_mean_R_T = 0.5 * mean_A   （= 0.5*(1-<R>-<T>)）
%      ⟨R⟩+⟨T⟩+⟨A⟩=1, 这里的 SUM_Solid_Angle_mean_R_T 实际上是 吸收 A 的半空间平均
% frequency : 列向量 [Hz]
% wall_type : 1-外墙 | 2-内墙 | 3-顶/地 | 4-窗 | 5-门关
% t_mid     : 中层/堆栈厚度 [m]
%    - case 4(窗)：t_mid 是“整窗堆栈厚度”（两片玻璃 + 空腔）
%    - case 3(顶/地)：传入 0.12（由调用者负责）
% epsTab    : Cole–Cole 参数表 [e_inf, e_s, sigma_s, tau, alpha]

mu0  = 4*pi*1e-7;
eps0 = 1/(36*pi)*1e-9;
f    = frequency(:);
F    = numel(f);

% ----- 层定义 -----
switch wall_type
    case 1      % 外墙 15-19-15
        id = [15 19 15];  t = [0.005 t_mid 0.005];
    case 2      % 内墙 15-16-15
        id = [15 16 15];  t = [0.005 t_mid 0.005];
    case 3      % 顶/地 15-19-15, 中层=t_mid (如0.22)
        id = [15 19 15];  t = [0.005 t_mid 0.005];
    case 4      % 窗：玻-气-玻 13-21-13, t_mid=整窗堆栈厚度
        id = [13 21 13];
        airGap = 0.001;                   % 空腔厚度 1 mm
        g      = max((t_mid - airGap)/2, 0);
        t      = [g airGap g];
    case 5      % 门关：空-木-空
        id = [21 5 21];   t = [0.001 t_mid 0.001];
    otherwise
        error('wall_type must be 1..5 (case 6 开门请在上层直接 A=0,T=1)');
end
L = 3;

% ----- 复介电常数 eps_r(f) -----
eps_r = zeros(F,L);
for k = 1:L
    p = epsTab(id(k),:);  % [e_inf e_s sigma_s tau alpha]
    eps_r(:,k) = p(1) + (p(2)-p(1))./(1 + (1i*2*pi*f*p(4)).^(1-p(5))) + p(3)./(1i*2*pi*f*eps0);
end

% ----- 角域积分 -----
Ntheta = 1000;
thetaV = linspace(0, pi/2, Ntheta);
dTheta = thetaV(2) - thetaV(1);

sumR = zeros(F,1);   % ∫ R_mean(θ) cosθ sinθ dθ
sumT = zeros(F,1);

epsAir = ones(F,1);
omega  = 2*pi*f;

for theta = thetaV
    epsFull = [epsAir eps_r epsAir];   % F x (L+2)
    dFull   = [0 t 0];                 % 1 x (L+2)

    gamma = 1i * omega .* sqrt(mu0 * eps0 .* epsFull);   % 传播常数

    % Snell 角（复角，递推）
    theta_j = zeros(F, L+2);
    theta_j(:,1) = theta;
    for n = 2:(L+2)
        theta_j(:,n) = asin( sqrt(epsFull(:,n-1))./sqrt(epsFull(:,n)) .* sin(theta_j(:,n-1)) );
    end

    phi = gamma .* (dFull .* cos(theta_j));   % 相位厚度

    Nst = L + 2;
    A = ones(F,Nst);  B = zeros(F,Nst);  % TE
    C = ones(F,Nst);  D = zeros(F,Nst);  % TM

    for n = Nst-1:-1:1
        Y = (cos(theta_j(:,n+1))./cos(theta_j(:,n))) .* sqrt(epsFull(:,n+1)./epsFull(:,n)); % TE
        Z = (cos(theta_j(:,n+1))./cos(theta_j(:,n))) .* sqrt(epsFull(:,n)./epsFull(:,n+1)); % TM

        eP = exp(phi(:,n));  eM = exp(-phi(:,n));

        % TE 更新
        A(:,n) = 0.5 .* eP .* ( A(:,n+1).*(1+Y) + B(:,n+1).*(1-Y) );
        B(:,n) = 0.5 .* eM .* ( A(:,n+1).*(1-Y) + B(:,n+1).*(1+Y) );
        % TM 更新
        C(:,n) = 0.5 .* eP .* ( C(:,n+1).*(1+Z) + D(:,n+1).*(1-Z) );
        D(:,n) = 0.5 .* eM .* ( C(:,n+1).*(1-Z) + D(:,n+1).*(1+Z) );
    end

    % ---- TE/TM 系数 ----
    RV = B(:,1)./A(:,1);   TV = 1./A(:,1);   % TE
    RH = D(:,1)./C(:,1);   TH = 1./C(:,1);   % TM（修正版）

    R_mean = 0.5*(abs(RV).^2 + abs(RH).^2);
    T_mean = 0.5*(abs(TV).^2 + abs(TH).^2);

    w = cos(theta)*sin(theta)*dTheta;
    sumR = sumR + R_mean.*w;
    sumT = sumT + T_mean.*w;
end

% 半球归一化
mean_R = 2 * sumR;
mean_T = 2 * sumT;
mean_A = max(0, 1 - mean_R - mean_T);

% —— 返回 —— %
result.mean_R = mean_R;
result.mean_T = mean_T;
result.mean_A = mean_A;

% 带 1/2 的“半空间平均”，直接用于 Σ = Area × result.SUM_*
result.SUM_Solid_Angle_mean_R   = 0.5 * mean_R;
result.SUM_Solid_Angle_mean_T   = 0.5 * mean_T;
result.SUM_Solid_Angle_mean_R_T = 0.5 * mean_A;
end
