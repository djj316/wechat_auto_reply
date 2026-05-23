# Web 面板改造计划 - Amadeus 风格 + Live2D 集成

## 一、改造目标

将现有微信自动回复管理面板改造为 **Amadeus 桌面助手 Web 面板**，采用《命运石之门》主题风格，集成 Live2D 形象展示。

## 二、视觉设计 - 命运石之门主题

### 色彩方案
```css
:root {
    --bg-dark: #0a0a0f;           /* 深空黑背景 */
    --bg-card: #12121a;           /* 卡片背景 */
    --bg-card-hover: #1a1a26;     /* 卡片悬停 */
    --primary: #c62828;           /* 命运石之门红 */
    --primary-glow: #e53935;      /* 红色发光 */
    --primary-dim: #8e0000;       /* 暗红 */
    --accent: #ff6f00;            /* 琥珀色点缀 */
    --text: #e0e0e0;              /* 主文字 */
    --text-dim: #808080;          /* 次要文字 */
    --text-bright: #ffffff;       /* 亮白文字 */
    --border: #1e1e2e;            /* 边框 */
    --success: #2e7d32;           /* 绿色 */
    --warning: #f57f17;           /* 警告黄 */
    --danger: #c62828;            /* 危险红 */
    --terminal-green: #00ff41;    /* 终端绿（Matrix风格点缀） */
    --font-mono: 'Courier New', monospace;
}
```

### 设计元素
- **背景**: 深色科技感，带微妙的网格线或电路纹理
- **标题栏**: 红色发光边框，显示 "Amadeus v1.0" + 状态指示灯
- **导航**: 左侧垂直导航栏（而非顶部），带图标
- **字体**: 等宽字体用于状态显示，无衬线字体用于内容
- **装饰**: 红色扫描线动画、终端风格日志、科技感边框

### 布局结构
```
┌──────────────────────────────────────────────┐
│  █████╗ ███╗   ███╗ █████╗ ██████╗ ███████╗ │  <- ASCII Art 标题
│  ██╔══██╗████╗ ████║██╔══██╗██╔══██╗██╔════╝ │     Amadeus v1.0
│  ███████║██╔████╔██║███████║██║  ██║█████╗   │
│  ██╔══██║██║╚██╔╝██║██╔══██║██║  ██║██╔══╝   │
│  ██║  ██║██║ ╚═╝ ██║██║  ██║██████╔╝███████╗ │
│  ╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝ │
│                                                    │
│  ┌──────────┐  ┌──────────────────────────────┐   │
│  │ 📊 仪表盘 │  │                              │   │
│  │ ⚙️ 配置   │  │     Live2D 显示区域          │   │
│  │ 👥 联系人 │  │     (Kurisu 形象)            │   │
│  │ 🧠 LLM   │  │                              │   │
│  │ 📋 日志   │  │                              │   │
│  │ 🎤 语音   │  └──────────────────────────────┘   │
│  │          │  ┌──────────────────────────────┐   │
│  │          │  │  状态栏 / 控制面板            │   │
│  └──────────┘  └──────────────────────────────┘   │
└──────────────────────────────────────────────┘
```

## 三、Live2D 集成方案

### 技术选型
- **Live2D Cubism WebGL SDK** - 官方 Web SDK
- **pixi-live2d-display** - PixiJS 插件，简化集成
- 使用 CDN 加载，无需本地构建

### 模型文件放置
```
live2d/kurisu/
├── kurisu.model3.json    # 模型配置文件
├── kurisu.moc3           # 模型数据
├── textures/             # 纹理
│   └── kurisu_00.png
├── motions/              # 动作
│   ├── idle.motion3.json
│   └── ...
└── expressions/          # 表情
    └── ...
```

### Live2D 交互功能
| 功能 | 触发条件 | 实现方式 |
|------|----------|----------|
| 待机动画 | 页面空闲 | 循环播放 idle 动作 |
| 说话口型 | LLM 回复时 | 触发 talking 动作 + 口型参数 |
| 情绪表达 | 回复内容分析 | 切换表情 (happy/sad/angry) |
| 鼠标跟随 | 鼠标移动 | 视线追踪 |
| 点击互动 | 点击模型 | 触发指定动作 |

### Web 面板集成
在 `index.html` 中新增 Live2D 容器：
```html
<div id="live2d-container">
    <canvas id="live2d-canvas"></canvas>
    <div class="live2d-controls">
        <button onclick="toggleLive2D()">显示/隐藏</button>
        <select onchange="changeExpression(this.value)">
            <option value="neutral">普通</option>
            <option value="happy">开心</option>
            <option value="sad">无奈</option>
        </select>
    </div>
</div>
```

## 四、页面功能改造

### 现有页面改造
| 页面 | 改造内容 |
|------|----------|
| 📊 仪表盘 | 重新设计状态卡片为终端风格，添加 Live2D 显示区域 |
| ⚙️ 配置 | 保持功能不变，样式适配暗色主题 |
| 👥 联系人 | 保持功能不变，样式适配 |
| 🧠 LLM 测试 | 聊天框改为终端风格，显示 Kurisu 头像 |
| 📋 日志 | 保持终端风格日志（已有，微调颜色） |

### 新增页面
| 页面 | 功能 |
|------|------|
| 🎤 语音 | 语音控制面板（预留，后续阶段实现） |

## 五、后端 API 扩展

### 新增 API 端点
| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/live2d/status` | 获取 Live2D 状态 |
| POST | `/api/live2d/expression` | 切换表情 |
| POST | `/api/live2d/motion` | 触发动作 |
| GET | `/api/live2d/model_info` | 获取模型信息 |

## 六、实施步骤

### 步骤 1: 创建 Amadeus 目录结构
- 创建 `amadeus/` 核心包目录
- 创建 `live2d/` 模型目录
- 创建 `web/` 服务目录（替代 web_admin/）

### 步骤 2: 重构 Web 面板前端
- 重写 `index.html` 为命运石之门暗色主题
- 左侧导航栏布局
- 终端风格状态显示
- ASCII Art 标题

### 步骤 3: 集成 Live2D
- 将模型文件放入 `live2d/kurisu/`
- 在 index.html 中加载 Live2D Cubism SDK
- 实现 Live2D 渲染容器
- 实现基本交互（待机动画、鼠标跟随）

### 步骤 4: 后端 API 适配
- 迁移 web_admin/app.py 到 web/app.py
- 新增 Live2D API 端点
- 确保向后兼容

### 步骤 5: 验证
- 启动 Web 面板模式
- 验证所有页面功能正常
- 验证 Live2D 显示正常
- 验证 LLM 测试对话正常

## 七、文件变更清单

### 新增文件
```
web/templates/index.html          # 完全重写
web/static/live2d.css             # Live2D 容器样式
live2d/kurisu/                    # 模型文件目录
```

### 修改文件
```
web_admin/app.py → web/app.py     # 迁移 + 扩展
web_admin/__init__.py → web/__init__.py
main.py                           # 更新导入路径
```

### 删除文件
```
web_admin/                        # 整个目录被 web/ 替代
```

## 八、命运石之门主题 CSS 示例

```css
/* 扫描线效果 */
body::after {
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(
        0deg,
        transparent,
        transparent 2px,
        rgba(0, 255, 65, 0.03) 2px,
        rgba(0, 255, 65, 0.03) 4px
    );
    pointer-events: none;
    z-index: 9999;
}

/* 红色发光边框 */
.card {
    border: 1px solid var(--border);
    box-shadow: 0 0 10px rgba(198, 40, 40, 0.1),
                inset 0 0 10px rgba(198, 40, 40, 0.05);
}

/* 终端风格状态 */
.status-item {
    font-family: var(--font-mono);
    border-left: 3px solid var(--primary);
}
```
