# AxonAI 多功能域康复评估逻辑

## 1. 临床推理主链

系统采用与康复治疗师一致的分层推理，不把单个动作失败直接等同于诊断：

1. 明确患者与安全参数：诊断、发病阶段、患侧、身高、体重、生命体征限制、疼痛、辅助器具、认知/沟通状态、跌倒风险。
2. 记录临床观察：Brunnstrom、MMT、改良 Ashworth、MBI，以及治疗师确认的坐位/站立平衡和转移能力。
3. 完成功能任务：上肢、手、下肢和平衡包均按步骤采集；每个失败步骤只生成该步骤预先声明的功能表型。
4. 解释机制：结合关节轨迹、时序、对称性、代偿代理指标，以及可用时的肌骨模型估计。
5. 建立问题清单：`身体功能损伤 -> 活动限制 -> 参与限制/安全风险`。
6. 制定目标：以患者有意义的活动为主，设定时间范围、帮助等级、任务条件和复测指标。
7. 生成训练建议：每项训练必须对应一个已识别问题，并受安全等级约束；处方由康复师确认。

## 2. 四类证据必须分开

| 证据层 | 可报告内容 | 不可声称内容 |
| --- | --- | --- |
| 临床观察 | MMT、MAS、Brunnstrom、MBI、帮助等级 | 不应伪装为自动视觉测量 |
| 视觉直接/派生 | 关节角、轨迹、时序、完成率、躯干代偿角 | 真实肌力、肌张力、神经信号、绝对足底压力 |
| 视觉代理 | 重心相对支撑面的偏移、患侧负荷趋势、步态时相趋势 | CoP、GRF、足底压力图或精确承重百分比 |
| 肌骨模型估计 | 关节净力矩、肌肉激活和肌肉力需求估计 | 患者最大肌力、直接 EMG、神经网络重组程度 |

## 3. 患者参数如何确定并固定模型

- 几何参数：身高、可见肢段长度和标定姿势用于缩放骨段长度与关节中心。
- 惯性参数：体重与人体测量先验用于缩放骨段质量、质心和转动惯量。
- 关节约束：临床 ROM、疼痛和挛缩信息用于限制可行关节范围。
- 能力参数：MMT、Brunnstrom 和 MAS 只能形成宽范围先验或安全约束，不能直接映射为某块肌肉的确定 `Fmax`。
- 患侧参数：左右侧分别保留容量缩放、ROM 和控制约束；不得用健康侧参数直接替代患侧。
- 不可辨识参数：没有 EMG、测力或影像时，激活延迟、共同收缩、肌腱顺应性等不能可靠个体化，应使用群体先验并输出不确定性。

患者参数一旦通过标定，应在同一评估周期内冻结；只有在重新标定、体重明显变化、矫形器改变或治疗师确认 ROM/能力状态变化时更新。

## 4. 肌骨优化形式

建议使用 OpenSim 逆运动学、逆动力学和静态优化或 Moco inverse：

```text
min  sum_t [
       w_q ||q_model(t) - q_observed(t)||^2
     + w_r ||residual(t)||^2
     + w_a sum_m activation_m(t)^p
     + w_theta ||theta_patient - theta_prior||^2
]

subject to:
  M(q, theta) qdd + C(q, qd, theta) + G(q, theta)
    = R(q, theta) F_muscle + J(q)^T F_external + residual
  0 <= activation_m <= 1
  F_muscle = activation_m * Fmax_m(theta) * f_l * f_v + F_passive
  q_min(theta) <= q <= q_max(theta)
```

患者参数 `theta_patient` 进入骨段几何、惯性、关节范围、最大等长肌力先验和左右侧约束。临床参数通过正则项、边界或先验分布进入，不应被硬编码为唯一解。

## 5. 无设备条件下的实际产品路线

1. 核心 MVP：单目视频用于任务完成、关节运动、时序、对称性和代偿筛查。
2. 3D 层：优先多视角；单目 3D 必须输出深度不确定性和可用帧质量。
3. 肌骨层：非承重动作可先做重力主导的力矩需求估计；承重、站立和步行必须测量或显式建模外力。
4. 足底层：无压力鞋垫/测力台时只输出“足底负荷分配代理指标”，不输出压力图或绝对 CoP。
5. 验证层：与 MMT/测力计、压力鞋垫/测力台、EMG 和治疗师评分进行分域验证；阈值在验证前仅为筛查规则。

## 6. 结果到康复目标

- 肌群能力不足且选择性控制尚可：渐进抗阻、重复任务和负荷剂量管理。
- 激活/时序异常但完成能力尚可：慢速分解、节律提示、反馈和任务特异性重复。
- 代偿明显：降低任务难度，约束代偿，优先恢复目标关节策略。
- 平衡或患侧负荷不足：从坐位中线、坐位移重、辅助站立、站立移重逐级进阶。
- 手功能严重受限：先保护关节、维持活动度和诱发主动运动，再进入抓握、释放和精细操作。

任何站立、步行和动态平衡建议均受治疗师安全判断、近旁保护和固定支持条件约束。

## 7. 主要依据

- Canadian Stroke Best Practices, Lower Extremity, Balance, Mobility and Aerobic Training: https://www.strokebestpractices.ca/recommendations/stroke-rehabilitation-delivery/4-lower-extremity-balance-mobility-and-aerobic-training
- Stroke Recovery and Rehabilitation Roundtable balance/mobility core recommendations: https://pubmed.ncbi.nlm.nih.gov/37824730/
- OpenSim Static Optimization: https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53089624/Getting+Started+with+Static+Optimization
- OpenSim Scaling, Inverse Kinematics and Inverse Dynamics: https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53089741/Tutorial+3+-+Scaling+Inverse+Kinematics+and+Inverse+Dynamics
