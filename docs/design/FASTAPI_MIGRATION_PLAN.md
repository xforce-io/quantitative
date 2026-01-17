# FastAPI + 原生前端迁移方案

**创建日期**: 2026-01-16  
**状态**: 进行中  
**参考项目**: Alfred 论文 Bot (`~/lab/alfred`)

---

## 🎯 目标

将 AI 分析师从 Streamlit 迁移到 FastAPI + 原生 HTML/JS 架构，实现：
- ✅ 真正的 SSE 流式输出（而非 Queue 模拟）
- ✅ 精美现代化 UI（TailwindCSS + 玻璃拟态）
- ✅ 快速提问按钮等交互增强
- ✅ 响应式体验（无 rerun 卡顿）

---

## 📐 架构设计

### 整体架构

```
┌────────────────────────────────────────────────────────────────┐
│                        前端 (Browser)                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │      static/analyst.html (TailwindCSS + JavaScript)      │  │
│  │  ┌─────────────────┐  ┌─────────────────────────────┐   │  │
│  │  │   页面数据展示   │  │     AI 对话面板             │   │  │
│  │  │  (Stock Data)    │  │  - 快速提问按钮            │   │  │
│  │  │                  │  │  - 流式消息展示            │   │  │
│  │  │                  │  │  - 工具调用可视化          │   │  │
│  │  └─────────────────┘  └─────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │ SSE                              │
│                              ▼                                  │
├────────────────────────────────────────────────────────────────┤
│                        后端 (FastAPI)                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   analyst_api.py                          │  │
│  │  POST /api/analyst/chat     (SSE 流式响应)                │  │
│  │  GET  /api/analyst/history  (对话历史)                    │  │
│  │  POST /api/analyst/clear    (清空会话)                    │  │
│  │  GET  /api/stocks/data      (页面股票数据)                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  agent_manager.py                         │  │
│  │           (Dolphin SDK 封装，async 原生)                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### 新增文件清单

```
web/
├── api/
│   ├── __init__.py          # FastAPI 应用入口
│   ├── analyst_api.py       # AI 分析师 API
│   └── stocks_api.py        # 股票数据 API
├── static/
│   ├── analyst.html         # AI 分析师页面
│   ├── analyst.css          # 自定义样式
│   └── analyst.js           # 交互逻辑
└── server.py                # FastAPI 主服务
```

---

## 🔧 实现步骤

### Phase 1: FastAPI 后端框架 (Day 1)

1. **创建 FastAPI 应用骨架**
   - `web/api/__init__.py` - 应用工厂
   - `web/server.py` - 主入口，CORS、静态文件挂载

2. **迁移 agent_manager.py 为纯 async**
   - 去掉 threading + Queue 模拟
   - 使用 asyncio.Queue 实现真正流式

3. **实现 /api/analyst/chat SSE 端点**
   - StreamingResponse
   - 真正的 Server-Sent Events

### Phase 2: 前端 HTML/JS 实现 (Day 2)

1. **创建 analyst.html 主页面**
   - TailwindCSS (CDN 引入)
   - 固定布局：左侧数据展示，右侧 AI 面板

2. **实现 AI 对话面板组件**
   - 快速提问按钮区域
   - 消息气泡（用户/AI 区分）
   - 工具调用展开卡片
   - 流式打字效果

3. **JavaScript SSE 处理**
   - EventSource 或 fetch + ReadableStream
   - Markdown 渲染 (marked.js)
   - 自动滚动控制

### Phase 3: 功能完善 (Day 3)

1. **股票数据 API**
   - 复用现有 data_service.py 逻辑
   - 提供 JSON 接口

2. **页面数据联动**
   - AI 能感知当前查看的股票
   - 快速提问按钮动态化

3. **样式优化**
   - 响应式适配
   - 动画微调
   - 主题统一

---

## 🎨 UI 设计规范

### 色彩系统 (参考 Alfred)

```css
/* 主色调 - 紫蓝渐变 */
--primary-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
--accent-violet: #7c3aed;
--accent-purple: #a855f7;

/* 背景 */
--bg-base: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
--bg-glass: rgba(255, 255, 255, 0.8);

/* 文字 */
--text-primary: #1e293b;
--text-secondary: #64748b;

/* 状态色 */
--success: #10b981;
--warning: #f59e0b;
--error: #ef4444;
```

### 玻璃拟态 (Glassmorphism)

```css
.glass-card {
    background: rgba(255, 255, 255, 0.8);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
}
```

### 快速提问按钮

```html
<div class="quick-questions">
    <button>🎯 核心投资逻辑</button>
    <button>⚠️ 主要风险点</button>
    <button>📊 技术面分析</button>
    <button>💡 操作建议</button>
</div>
```

---

## 📝 API 设计

### POST /api/analyst/chat

**请求体**:
```json
{
    "message": "分析一下贵州茅台",
    "session_id": "abc123",
    "context": {
        "symbols": ["600519.SH"],
        "page": "ranking"
    }
}
```

**SSE 响应流**:
```
data: {"type": "progress", "stage": "init", "content": "正在初始化..."}

data: {"type": "tool_call", "name": "get_stock_data", "args": {"symbol": "600519.SH"}}

data: {"type": "tool_result", "name": "get_stock_data", "result": "..."}

data: {"type": "delta", "content": "根据"}

data: {"type": "delta", "content": "分析"}

data: {"type": "done", "content": "完整回复内容"}

data: {"type": "end", "session_id": "abc123"}
```

---

## ✅ 验收标准

1. **流式输出**: 文字逐字显示，无卡顿
2. **多轮对话**: 上下文保持，第 N 轮对话流畅
3. **快速提问**: 一键触发预设问题
4. **工具可视化**: 工具调用清晰展示
5. **响应速度**: 首字节 < 1s
6. **视觉效果**: 精美程度不输 Alfred

---

## 📋 开发日志

### 2026-01-16

- [x] 完成设计文档
- [x] 创建 FastAPI 骨架 (`web/api/__init__.py`)
- [x] 迁移 agent_manager 为纯 async (`web/api/analyst_api.py`)
- [x] 实现 /api/analyst/chat SSE 流式端点
- [x] 创建 analyst.html 精美页面 (TailwindCSS + 玻璃拟态)
- [x] 创建启动脚本 `scripts/run_api.sh`
- [x] 测试 SSE 流式输出 ✅ 工作正常

**访问地址**: http://localhost:8080

---

**Author**: AI + xupeng  
**Last Updated**: 2026-01-16
