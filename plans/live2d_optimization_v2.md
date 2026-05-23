# Live2D 交互系统优化方案 v2.0

## 一、当前状态分析

### 模型参数（16个）
| 参数 ID | 名称 | 分组 | 范围 |
|---------|------|------|------|
| ParamEyeROpen | 眼睛睁开 | Eyes | 0-1.5 |
| Param | 睫毛摆动 R | Eyes | - |
| Param2 | 睫毛摆动 R 2 | Eyes | - |
| Param3 | 虹膜缩放 R | Eyes | 0-1 |
| ParamEyeBallX | 眼球 X | Eyes | -1~1 |
| ParamEyeBallY | 眼球 Y | Eyes | -1~1 |
| ParamBreath | 呼吸 | Breathing | - |
| Param4 | 手臂物理 | Breathing | - |
| Param5 | 头发物理 | Breathing | - |
| Param6 | 手臂思考动作 | Thinking | 0-1 |
| Param8 | 思考面部表情 | Thinking | 0-1 |
| Param7 | 手臂动作物理 | Thinking | - |
| ParamEyeRSmile | 眼睛微笑 | Smiling | 0-1 |
| Param9 | 脸红 | Smiling | 0-1 |
| ParamMouthOpenY | 嘴巴张开 | Mouth | 0-1 |
| ParamMouthForm | 嘴巴形状 | Mouth | -1~1 |

### 动作文件（4个）
| 文件 | 时长 | 循环 | 曲线数 | 说明 |
|------|------|------|--------|------|
| idle.motion3.json | 4s | 是 | 54 | 空闲循环 |
| mtn_01.motion3.json | 6s | 是 | 54 | 包含 ParamFlame/ParamMagic 特效参数 |
| mtn_02.motion3.json | 5s | 是 | 54 | 包含 ParamFlame/ParamMagic 特效参数 |
| mtn_03.motion3.json | 8s | 是 | 54 | 包含 ParamFlame/ParamMagic 特效参数 |

### 当前自动行为概率分布
| 行为 | 概率 | 说明 |
|------|------|------|
| 随机表情 | 25% | 7种表情随机选 |
| 播放动作 | 10% | 3个动作随机选 |
| 眨眼 | 10% | 快速闭眼再睁开 |
| 歪头 | 5% | 随机左右倾斜 |
| 空闲 | 50% | 无操作 |

### 当前问题
1. **动作触发概率太低**（仅10%），用户感觉不到动作变化
2. **没有组合行为**（表情+动作同时触发）
3. **空闲动画单调**，只有呼吸（由物理引擎驱动）和偶尔的眨眼/歪头
4. **点击交互反应类型不够丰富**
5. **没有条件触发机制**（如长时间无交互、交互频繁等）
6. **Live2D 不是默认首页**，需要手动点击导航

---

## 二、优化方案

### 方案一：Live2D 设为默认首页

**修改点：** [`web/templates/index.html`](../web/templates/index.html)

1. **HTML 结构**：将 `page-live2d` 的 `active` 类移到最前面
   - 原：`<div id="page-dashboard" class="page active">`
   - 改为：`<div id="page-live2d" class="page active">`
   - 同时 `page-dashboard` 去掉 `active`

2. **导航栏**：将 Live2D 导航项移到第一位
   ```html
   <div class="nav-item active" data-page="live2d"><span class="icon">🎭</span><span class="label">Live2D</span></div>
   <div class="nav-item" data-page="dashboard"><span class="icon">📊</span><span class="label">仪表盘</span></div>
   ```

3. **JS 初始化**：`currentPage` 默认值改为 `'live2d'`
   ```javascript
   let currentPage = 'live2d';
   ```

4. **页面标题**：默认显示 "Live2D"
   ```javascript
   const PAGE_NAMES = {live2d:'Live2D', dashboard:'仪表盘', ...};
   ```

---

### 方案二：重构自动行为系统

**修改点：** [`web/templates/index.html`](../web/templates/index.html) - `_l2dStartAutoBehavior` 函数

#### 新的概率分布（每 5-10 秒触发一次）

| 行为 | 概率 | 说明 |
|------|------|------|
| 随机表情 | 20% | 7种表情随机选，持续 3s |
| 播放动作 | 20% | 3个动作随机选（大幅提升！） |
| 组合行为（表情+动作） | 15% | 表情+动作联动触发 |
| 眨眼 | 10% | 自然眨眼 |
| 环顾四周 | 10% | 眼球+头部缓慢转动 |
| 歪头/整理头发 | 5% | 头部倾斜+手臂微动 |
| 深呼吸 | 5% | 大幅度呼吸+肩膀起伏 |
| 空闲 | 15% | 无操作 |

#### 组合行为表（表情+动作联动）

| 组合名称 | 表情 | 动作 | 适用场景 |
|---------|------|------|---------|
| 开心挥手 | smile | mtn_01 | 友好问候 |
| 思考托腮 | think | mtn_02 | 思考问题 |
| 惊讶捂嘴 | surprise | mtn_03 | 惊讶反应 |
| 害羞低头 | blush | mtn_02 | 害羞表现 |
| 兴奋雀跃 | excited | mtn_01 | 开心兴奋 |

---

### 方案三：新增空闲动画序列

**修改点：** [`web/templates/index.html`](../web/templates/index.html) - 新增函数

利用模型已有的物理参数（ParamBreath、Param4 手臂物理、Param5 头发物理、Param7 手臂动作物理）和 Parts（arm_think、arms_iddle_anim），实现更丰富的空闲动画：

1. **自然呼吸**：ParamBreath 周期性变化（0→1→0，周期 4s）
2. **头发飘动**：Param5 轻微随机波动
3. **手臂微动**：Param4/Param7 轻微随机变化
4. **眼睛自然运动**：ParamEyeBallX/Y 随机缓慢移动（不追踪鼠标时）
5. **书本翻页**：ParamBookPage 参数（mtn_01 中包含此参数，模型可能有书本道具）

---

### 方案四：优化点击交互反馈

**修改点：** [`web/templates/index.html`](../web/templates/index.html) - `_l2dSetupInteraction` 函数

#### 单击反应（友好型）- 增加更多种类

| 反应 | 概率 | 表情 | 动作概率 |
|------|------|------|---------|
| 微笑回应 | 25% | smile | 20% 配合动作 |
| 眨眼放电 | 20% | wink | 10% 配合动作 |
| 害羞脸红 | 20% | blush | 10% 配合动作 |
| 歪头疑惑 | 15% | think | 30% 配合动作 |
| 开心回应 | 10% | excited | 50% 配合动作 |
| 困倦打哈欠 | 10% | sleepy | 20% 配合动作 |

#### 双击反应（特殊型）

| 反应 | 概率 | 表情 | 动作 |
|------|------|------|------|
| 傲娇扭头 | 30% | tsundere | 必触发动作 |
| 兴奋跳跃 | 25% | excited | 必触发动作 |
| 假装生气 | 20% | angry | 必触发动作 |
| 超级害羞 | 15% | blush | 必触发动作 |
| 震惊捂嘴 | 10% | surprise | 必触发动作 |

#### 交互计数器反馈
- 每 5 次交互：触发一次特殊组合反应
- 每 10 次交互：触发一次"感谢陪伴"反应（smile + mtn_01）
- 交互次数显示在模型信息卡中

---

### 方案五：特殊条件触发系统

**修改点：** [`web/templates/index.html`](../web/templates/index.html) - 新增条件检测逻辑

| 条件 | 触发行为 | 说明 |
|------|---------|------|
| 长时间无交互（>30s） | 困倦表情 → 歪头 → 打哈欠 | 逐渐进入 idle 状态 |
| 长时间无交互（>60s） | 睡着表情（闭眼+低头） | 模拟睡着 |
| 交互频繁（5s内3次） | 困惑表情 | "你在干嘛？"的感觉 |
| 页面切换回来 | 微笑+挥手动作 | 欢迎回来 |
| 鼠标长时间停留在模型上 | 害羞脸红 | 被盯着看会害羞 |

---

### 方案六：动作系统增强

**修改点：** [`web/templates/index.html`](../web/templates/index.html) - `l2dPlayMotion` 函数

当前动作播放有 `_l2dMotionPlaying` 锁，导致动作无法连续播放。优化方案：

1. **移除动作播放锁** 或改为队列系统
2. **动作淡入淡出**：播放动作前先重置参数，播放后平滑恢复
3. **动作优先级**：
   - 高优先级：用户点击触发的动作
   - 中优先级：组合行为中的动作
   - 低优先级：自动行为中的动作
4. **动作中断**：高优先级动作可以中断低优先级动作

---

## 三、实现计划

### 第1步：Live2D 设为默认首页
- 修改 HTML 中 page 的 active 状态
- 修改导航栏顺序
- 修改 JS 中 currentPage 默认值
- 修改 PAGE_NAMES 顺序

### 第2步：重构自动行为系统
- 重写 `_l2dStartAutoBehavior` 函数
- 新增组合行为逻辑
- 调整概率分布
- 缩短触发间隔（5-10s）

### 第3步：新增空闲动画序列
- 新增 `_l2dIdleAnimation` 函数
- 利用 ParamBreath/Param4/Param5/Param7 实现自然动画
- 利用 ParamEyeBallX/Y 实现环顾四周

### 第4步：优化点击交互反馈
- 扩展单击/双击反应类型
- 新增交互计数器反馈
- 优化反应概率分布

### 第5步：实现特殊条件触发
- 新增 `_l2dCheckConditions` 函数
- 实现长时间无交互检测
- 实现交互频繁检测
- 实现页面切换欢迎

### 第6步：动作系统增强
- 移除动作播放锁
- 实现动作优先级队列
- 实现动作淡入淡出

---

## 四、技术要点

1. **参数范围**：
   - ParamEyeROpen: 0（闭眼）~ 1.5（睁大）
   - ParamMouthOpenY: 0（闭）~ 1（全开）
   - ParamMouthForm: -1（撇嘴）~ 1（微笑）
   - ParamAngleX: -30（左转）~ 30（右转）
   - ParamAngleY: -30（低头）~ 30（抬头）
   - Param9（脸红）: 0（无）~ 1（最红）
   - Param3（虹膜）: 0（缩小）~ 1（正常）

2. **动作文件特点**：
   - mtn_01（6s）：包含 ParamFlame（火焰）、ParamMagic（魔法阵）、ParamCharge（充能）等特效参数
   - mtn_02（5s）：包含 ParamFlame、ParamMagic 等特效参数
   - mtn_03（8s）：包含 ParamFlame、ParamMagic 等特效参数
   - 三个动作都包含完整的身体旋转（ParamBodyAngleX/Y/Z）、手臂（ParamArmR01-03/L01-03）、裙子（ParamSkirt）等参数

3. **Parts 可见性控制**：
   - `arm_think`：思考时的手臂姿势
   - `arms_iddle_anim`：空闲时的手臂动画
   - `blushing`：脸红图层
   - 可通过 `l2dModel.internalModel.coreModel.setPartOpacityById('blushing', 1)` 控制

---

## 五、预期效果

1. **页面打开即见 Live2D**，无需手动点击加载
2. **动作触发频率大幅提升**（从 10% 提升到 35%）
3. **表情+动作联动**，行为更自然
4. **空闲动画丰富**，模型不再呆板
5. **点击反馈多样化**，交互更有趣
6. **条件触发机制**，模型有"生命感"
7. **动作播放流畅**，不再被锁阻塞
