# Documentation / 文档导航

Welcome to the Quantitative Trading System documentation. This page serves as the central navigation hub for all documentation.

欢迎来到量化交易系统文档。本页面是所有文档的中心导航。

## 📋 Language Policy / 语言政策

Following the project's documentation best practices defined in `AGENTS.md`:

- **Usage Documentation (`usage/`)**: English, for all users and developers
- **Design Documentation (`design/`)**: Chinese, for internal technical discussions
- **Exception**: Detailed technical guides may remain in Chinese, but should provide English quick reference

遵循 `AGENTS.md` 中定义的文档最佳实践：

- **使用文档 (`usage/`)**: 英文为主，面向所有使用者和开发者
- **设计文档 (`design/`)**: 中文为主，面向团队内部技术讨论
- **例外**: 详细技术指南可保留中文，但需提供英文快速参考版本

## 📚 Documentation Structure / 文档结构

```
docs/
├── README.md                           # This file / 本文件
├── ARCHITECTURE.md                     # System architecture overview
├── DIRECTORY_STRUCTURE.md              # Project directory layout
├── design/                             # Design documents (Chinese)
│   ├── AI_ANALYST_RIGHT_PANEL_AGENT_DESIGN.md
│   ├── AI_PANEL_FIX_VERIFICATION.md
│   ├── AI_PANEL_OUTPUT_FIX.md
│   ├── AI_PANEL_TECHNICAL_REVIEW.md
│   ├── PORTFOLIO_VALUATION_FEATURE.md
│   └── WILLIAM_ONEIL_CANSLIM_ENHANCEMENT.md
└── usage/                              # Usage documentation (English)
    ├── quick_start/
    │   └── GETTING_STARTED.md          # 5-minute quick start guide
    ├── guides/
    │   ├── AGENT_MANAGER_V2_MIGRATION.md
    │   ├── petri_experiments.md
    │   ├── TRADING_GUIDE.md
    │   └── USER_PORTFOLIO_GUIDE.md
    ├── configuration/
    │   └── CONFIGURATION.md            # Configuration reference
    └── concepts/                       # Core concepts (to be added)
```

## 🚀 Quick Links / 快速链接

### For New Users / 新用户

- [Getting Started Guide](usage/quick_start/GETTING_STARTED.md) - 5-minute setup and first run
- [Architecture Overview](ARCHITECTURE.md) - System design and components
- [Configuration Guide](usage/configuration/CONFIGURATION.md) - How to configure the system

### For Developers / 开发者

- [Agent Manager v2.0 Migration](usage/guides/AGENT_MANAGER_V2_MIGRATION.md) - Dolphin SDK v2.0 integration
- [Petri Experiments](usage/guides/petri_experiments.md) - Run Petri outside the project worktree and promote winning strategies
- [Trading Guide](usage/guides/TRADING_GUIDE.md) - Trading strategies and backtesting
- [User Portfolio Guide](usage/guides/USER_PORTFOLIO_GUIDE.md) - Portfolio management

### For Project Contributors / 项目贡献者

- [AI Analyst Design](design/AI_ANALYST_RIGHT_PANEL_AGENT_DESIGN.md) - AI analyst architecture
- [CANSLIM Enhancement](design/WILLIAM_ONEIL_CANSLIM_ENHANCEMENT.md) - CANSLIM strategy design
- [Portfolio Valuation Feature](design/PORTFOLIO_VALUATION_FEATURE.md) - Valuation module design
- [News Event Investment Probability Graph](design/NEWS_EVENT_INVESTMENT_PROBABILITY_GRAPH_DESIGN.md) - Event-driven investment inference design

## 📖 Essential Documentation / 核心文档

### 1. Quick Start / 快速开始

Start here if you're new to the system:
- [Getting Started](usage/quick_start/GETTING_STARTED.md) ✨

### 2. Configuration / 配置

Learn how to configure the system:
- [Configuration Reference](usage/configuration/CONFIGURATION.md)

### 3. User Guides / 使用指南

Step-by-step guides for common tasks:
- [Trading Guide](usage/guides/TRADING_GUIDE.md) - Trading strategies
- [Portfolio Guide](usage/guides/USER_PORTFOLIO_GUIDE.md) - Portfolio management
- [Petri Experiments](usage/guides/petri_experiments.md) - Isolated experiment workspaces and strategy publication boundary

### 4. Migration Guides / 迁移指南

Important updates and migrations:
- [Agent Manager v2.0](usage/guides/AGENT_MANAGER_V2_MIGRATION.md) - Dolphin SDK v2.0

### 5. Design Documents / 设计文档

Technical design and architecture (Chinese):
- [AI Analyst Design](design/AI_ANALYST_RIGHT_PANEL_AGENT_DESIGN.md)
- [AI Panel Technical Review](design/AI_PANEL_TECHNICAL_REVIEW.md)
- [News Event Investment Probability Graph](design/NEWS_EVENT_INVESTMENT_PROBABILITY_GRAPH_DESIGN.md)

## 🛠️ Web Application / Web 应用

The system includes a Streamlit-based web dashboard. See [Web Application](../AGENTS.md#web-application) section in AGENTS.md for details.

系统包含基于 Streamlit 的 Web 仪表板。详见 AGENTS.md 中的 [Web Application](../AGENTS.md#web-application) 章节。

**Quick Start**:
```bash
# Start web platform
scripts/run_web.sh start

# Access at http://localhost:8501
```

## 📝 Documentation Conventions / 文档约定

### File Naming / 文件命名
- Use lowercase with underscores: `getting_started.md`
- Clear, descriptive titles
- English for filenames in `usage/`, Chinese acceptable in `design/`

### Content Guidelines / 内容指南
- Clear heading hierarchy (`#`, `##`, `###`)
- Include table of contents for long documents
- Provide runnable code examples
- Use relative paths for links
- Avoid hardcoded personal paths

### Code Examples / 代码示例
```bash
# ✅ Good example
./scripts/run_web.sh start

# ❌ Avoid
cd /Users/alice/my-project  # Hardcoded path
```

## 🔍 Finding Documentation / 查找文档

### By Topic / 按主题

- **Installation & Setup**: `usage/quick_start/GETTING_STARTED.md`
- **Configuration**: `usage/configuration/CONFIGURATION.md`
- **Trading Strategies**: `usage/guides/TRADING_GUIDE.md`
- **Web Development**: `design/AI_ANALYST_RIGHT_PANEL_AGENT_DESIGN.md`

### By Type / 按类型

- **Quick Reference**: Start here for common commands and quick answers
- **Detailed Guides**: Comprehensive feature documentation
- **Design Docs**: Architecture decisions and technical specifications

## 🤝 Contributing to Documentation / 贡献文档

When adding or updating documentation:

1. ✅ Follow the language policy (English for usage, Chinese for design)
2. ✅ Place files in appropriate directories (`usage/` or `design/`)
3. ✅ Update this README.md with new document links
4. ✅ Ensure all links are valid and use relative paths
5. ✅ Provide code examples that can be executed
6. ✅ Check spelling and formatting

See [AGENTS.md](../AGENTS.md) for detailed documentation standards.

## 📞 Need Help? / 需要帮助？

- Check [Getting Started](usage/quick_start/GETTING_STARTED.md) first
- Review [Troubleshooting](usage/quick_start/GETTING_STARTED.md#troubleshooting) section
- Open an issue on GitHub

---

**Last Updated**: 2026-01-15
**Documentation Version**: 2.3.0
