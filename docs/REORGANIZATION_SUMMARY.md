# Documentation Reorganization Summary

**Date**: 2026-01-15  
**Status**: Completed ✅

## What Changed

Reorganized documentation structure to follow `AGENTS.md` best practices:

### Previous Structure (Flat)
```
docs/
├── AI_ANALYST_RIGHT_PANEL_AGENT_DESIGN.md
├── AGENT_MANAGER_V2_MIGRATION.md
├── GETTING_STARTED.md
├── CONFIGURATION.md
└── ... (all files in root)
```

### New Structure (Organized)
```
docs/
├── README.md                           # Documentation navigation hub
├── ARCHITECTURE.md                     # System architecture
├── DIRECTORY_STRUCTURE.md              # Project layout
├── design/                             # Design docs (Chinese) 中文设计文档
│   ├── PORTFOLIO_VALUATION_FEATURE.md
│   └── WILLIAM_ONEIL_CANSLIM_ENHANCEMENT.md
└── usage/                              # Usage docs (English) 英文使用文档
    ├── quick_start/
    │   └── GETTING_STARTED.md
    ├── guides/
    │   ├── AGENT_MANAGER_V2_MIGRATION.md
    │   ├── TRADING_GUIDE.md
    │   └── USER_PORTFOLIO_GUIDE.md
    ├── configuration/
    │   └── CONFIGURATION.md
    └── concepts/                       # (Empty, for future use)
```

## Language Policy

Following `AGENTS.md` documentation standards:

- `docs/usage/` - **English** documentation for all users and developers
- `docs/design/` - **Chinese** documentation for internal technical discussions
- Exception: Detailed technical guides may remain in Chinese with English quick reference

## Web-Specific Documentation

Web-related temporary/process documents remain in `web/` directory:
- `web/AI_PANEL_ALL_PAGES_INTEGRATION.md`
- `web/AI_PANEL_OPTIMIZATION_CHANGELOG.md`

These are working documents and will be consolidated into formal docs when stable.

## Navigation

All documentation can be accessed through:
- **Primary**: `docs/README.md` - Central navigation hub
- **Quick Start**: `docs/usage/quick_start/GETTING_STARTED.md`
- **Web App**: See `AGENTS.md` → Web Application section

## Impact on Links

If you have bookmarks or references to old paths, update them:

| Old Path | New Path |
|----------|----------|
| `docs/GETTING_STARTED.md` | `docs/usage/quick_start/GETTING_STARTED.md` |
| `docs/CONFIGURATION.md` | `docs/usage/configuration/CONFIGURATION.md` |
| `docs/AGENT_MANAGER_V2_MIGRATION.md` | `docs/usage/guides/AGENT_MANAGER_V2_MIGRATION.md` |
| `docs/TRADING_GUIDE.md` | `docs/usage/guides/TRADING_GUIDE.md` |

## Next Steps

1. ✅ Documentation structure reorganized
2. ✅ README.md updated with navigation
3. ✅ AGENTS.md updated with Web Application section
4. 🔲 Future: Add concept documentation in `docs/usage/concepts/`
5. 🔲 Future: Consolidate web/ working documents into formal docs

---

**Note**: This reorganization follows the documentation best practices defined in `AGENTS.md` Section "文档架构最佳实践".
