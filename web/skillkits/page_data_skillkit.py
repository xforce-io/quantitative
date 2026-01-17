"""
Page Data Skillkit - 页面数据访问工具包（v2.2 - Dolphin SDK 版本）

基于 Dolphin SDK 的 Skillkit 机制实现，提供 Agent 可调用的页面数据访问工具。
适配 page_registry v2.0 通用架构。

v2.2 更新：
- 继承 Dolphin SDK 的 Skillkit 基类
- 通过 _createSkills() 方法注册工具
- 支持 Dolphin Agent 的自动工具调用
"""

import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# 尝试导入 Dolphin SDK
try:
    from dolphin.core.skill.skillkit import Skillkit
    from dolphin.core.skill.skill_function import SkillFunction
    DOLPHIN_SDK_AVAILABLE = True
    logger.info("Dolphin SDK imported successfully")
except ImportError as e:
    logger.warning(f"Dolphin SDK not available: {e}, using fallback")
    DOLPHIN_SDK_AVAILABLE = False
    
    # 兼容层
    class Skillkit:
        """兼容 Skillkit 基类"""
        def __init__(self):
            self._name = "page_data"
            self._global_config = None
        
        def getName(self) -> str:
            return self._name
        
        def setGlobalConfig(self, config):
            self._global_config = config
        
        def _createSkills(self) -> list:
            return []
        
        def getSkills(self) -> list:
            return self._createSkills()
    
    class SkillFunction:
        """兼容 SkillFunction"""
        def __init__(self, func, openai_tool_schema=None):
            self.func = func
            self.openai_tool_schema = openai_tool_schema
        
        def get_function_name(self) -> str:
            return self.openai_tool_schema.get("function", {}).get("name", self.func.__name__)
        
        def get_openai_tool_schema(self) -> dict:
            return self.openai_tool_schema


class PageDataSkillkit(Skillkit):
    """
    页面数据访问工具包（v2.2）

    提供以下工具：
    - get_page_full_snapshot: 获取当前页面全部数据摘要
    - get_page_overview: 获取当前页面轻量概览
    - get_data_detail: 获取指定类别/键的细节数据
    - get_stock_dimension_detail: 获取股票维度数据（向后兼容）
    - fetch_stock_analysis: 按需获取任意股票的分析数据
    """
    
    # Token 控制常量
    MAX_SNAPSHOT_CHARS = 8000  # 约 2000 tokens（中文）
    MAX_TABLE_ROWS = 20
    MAX_DETAIL_CHARS = 4000
    
    def __init__(self):
        super().__init__()
        self._registry = None
    
    def getName(self) -> str:
        """Skillkit 名称"""
        return "page_data"
    
    def _get_registry(self):
        """获取 PageDataRegistry 实例"""
        try:
            import streamlit as st
            return st.session_state.get("page_registry")
        except Exception:
            return None
    
    # ==================== Dolphin SDK 集成 ====================
    
    def _createSkills(self) -> List[SkillFunction]:
        """创建技能列表（Dolphin SDK 会调用此方法）"""
        return [
            SkillFunction(
                func=self._skill_get_page_full_snapshot,
                openai_tool_schema={
                    "type": "function",
                    "function": {
                        "name": "get_page_full_snapshot",
                        "description": "获取当前页面全部股票的摘要数据（资金流向/技术/估值）。用于了解用户正在查看的所有信息。",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                }
            ),
            SkillFunction(
                func=self._skill_get_page_overview,
                openai_tool_schema={
                    "type": "function",
                    "function": {
                        "name": "get_page_overview",
                        "description": "获取当前页面轻量概览（页面名、时间范围、各类别数据统计）。用于快速了解页面上下文。",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                }
            ),
            SkillFunction(
                func=self._skill_get_data_detail,
                openai_tool_schema={
                    "type": "function",
                    "function": {
                        "name": "get_data_detail",
                        "description": "获取指定类别和键的细节数据。当需要深入分析某类数据时使用。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "description": "数据类别：stock（股票）、market（市场）、industry（行业）、ranking（排名）、news（资讯）、custom（自定义）"
                                },
                                "key": {
                                    "type": "string",
                                    "description": "数据键（如股票代码 000001.SZ、summary、flow_ranking 等）"
                                },
                                "level": {
                                    "type": "string",
                                    "enum": ["summary", "raw"],
                                    "description": "详细程度：summary（摘要）或 raw（原始数据）"
                                }
                            },
                            "required": ["category", "key"]
                        }
                    }
                }
            ),
            SkillFunction(
                func=self._skill_get_stock_dimension_detail,
                openai_tool_schema={
                    "type": "function",
                    "function": {
                        "name": "get_stock_dimension_detail",
                        "description": "获取指定股票某维度的细节数据。仅限已在当前页面展示的股票。如需查询其他股票请使用 fetch_stock_analysis。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {
                                    "type": "string",
                                    "description": "股票代码（如 000001.SZ、600519.SH）"
                                },
                                "dimension": {
                                    "type": "string",
                                    "enum": ["money_flow", "technical", "valuation"],
                                    "description": "维度：money_flow（资金流向）、technical（技术形态）、valuation（估值分析）"
                                },
                                "level": {
                                    "type": "string",
                                    "enum": ["summary", "table"],
                                    "description": "详细程度：summary（摘要）或 table（表格数据）"
                                }
                            },
                            "required": ["symbol", "dimension"]
                        }
                    }
                }
            ),
            SkillFunction(
                func=self._skill_fetch_stock_analysis,
                openai_tool_schema={
                    "type": "function",
                    "function": {
                        "name": "fetch_stock_analysis",
                        "description": "按需获取任意股票的完整分析数据（资金流向+技术指标+估值）。支持股票名称（如'比亚迪'）或代码（如'002594.SZ'）。当用户询问不在当前页面的股票时使用此工具。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {
                                    "type": "string",
                                    "description": "股票代码或名称（如 002594.SZ、比亚迪、茅台）"
                                },
                                "days": {
                                    "type": "integer",
                                    "description": "分析数据天数（默认60天）",
                                    "default": 60
                                }
                            },
                            "required": ["symbol"]
                        }
                    }
                }
            ),
        ]
    
    # ==================== 技能实现方法 ====================
    
    def _skill_get_page_full_snapshot(self, **kwargs) -> str:
        """获取当前页面全部数据的摘要"""
        return self.get_page_full_snapshot()
    
    def _skill_get_page_overview(self, **kwargs) -> str:
        """获取当前页面轻量概览"""
        return self.get_page_overview()
    
    def _skill_get_data_detail(self, category: str = "", key: str = "", level: str = "summary", **kwargs) -> str:
        """获取指定类别/键的细节数据"""
        return self.get_data_detail(category, key, level)
    
    def _skill_get_stock_dimension_detail(self, symbol: str = "", dimension: str = "", level: str = "summary", **kwargs) -> str:
        """获取指定股票某维度的细节数据"""
        return self.get_stock_dimension_detail(symbol, dimension, level)
    
    def _skill_fetch_stock_analysis(self, symbol: str = "", days: int = 60, **kwargs) -> str:
        """按需获取任意股票的分析数据"""
        return self.fetch_stock_analysis(symbol, days)
    
    # ==================== 核心业务方法 ====================
    
    def get_page_full_snapshot(self) -> str:
        """
        获取当前页面全部数据的摘要
        
        Returns:
            JSON 字符串：包含页面元信息、各类别数据摘要
        """
        registry = self._get_registry()
        if not registry:
            return json.dumps({"error": "页面数据未加载，请稍后重试"}, ensure_ascii=False)
        
        snapshot = registry.get_full_snapshot()
        json_str = json.dumps(snapshot, ensure_ascii=False, default=str, sort_keys=True)
        
        # Token 控制：超限时降级
        if len(json_str) > self.MAX_SNAPSHOT_CHARS:
            return self._truncated_snapshot(snapshot)
        
        return json_str
    
    def _truncated_snapshot(self, snapshot: dict) -> str:
        """降级快照：只保留关键摘要"""
        truncated = {
            "snapshot_version": snapshot.get("snapshot_version"),
            "snapshot_id": snapshot.get("snapshot_id"),
            "page": snapshot.get("page"),
            "data_summary": {},
            "truncated": True,
            "reason": "快照体积超限，已降级为摘要模式。如需细节请使用 get_data_detail"
        }
        
        for category, entries in snapshot.get("data", {}).items():
            truncated["data_summary"][category] = {}
            count = 0
            for key, entry_data in entries.items():
                if count >= 5:
                    truncated["data_summary"][category]["_more"] = len(entries) - 5
                    break
                truncated["data_summary"][category][key] = entry_data.get("summary", {})
                count += 1
        
        return json.dumps(truncated, ensure_ascii=False, default=str, sort_keys=True)
    
    def get_page_overview(self) -> str:
        """获取当前页面轻量概览"""
        registry = self._get_registry()
        if not registry:
            return json.dumps({"error": "页面数据未加载"}, ensure_ascii=False)
        return json.dumps(registry.get_overview(), ensure_ascii=False, default=str, sort_keys=True)
    
    def get_data_detail(self, category: str, key: str, level: str = "summary") -> str:
        """获取指定类别/键的细节数据"""
        registry = self._get_registry()
        if not registry:
            return json.dumps({"error": "页面数据未加载"}, ensure_ascii=False)
        
        try:
            detail = registry.get_data_detail(category, key, level)
            
            if isinstance(detail.get("data"), list):
                if len(detail["data"]) > self.MAX_TABLE_ROWS:
                    detail["data"] = detail["data"][:self.MAX_TABLE_ROWS]
                    detail["truncated"] = True
            
            json_str = json.dumps(detail, ensure_ascii=False, default=str, sort_keys=True)
            
            if len(json_str) > self.MAX_DETAIL_CHARS:
                return json.dumps({
                    "category": category,
                    "key": key,
                    "summary": detail.get("summary", {}),
                    "truncated": True,
                    "reason": f"数据过大（{len(json_str)} 字符），已只返回摘要"
                }, ensure_ascii=False, sort_keys=True)
            
            return json_str
            
        except Exception as e:
            return json.dumps({"error": f"获取数据失败: {str(e)}"}, ensure_ascii=False)
    
    def get_stock_dimension_detail(self, symbol: str, dimension: str, level: str = "summary") -> str:
        """获取指定股票某维度的细节数据"""
        registry = self._get_registry()
        if not registry:
            return json.dumps({"error": "页面数据未加载"}, ensure_ascii=False)
        
        try:
            detail = registry.get_dimension_detail(symbol, dimension, level)
            
            json_str = json.dumps(detail, ensure_ascii=False, default=str, sort_keys=True)
            
            if len(json_str) > self.MAX_DETAIL_CHARS:
                return json.dumps({
                    "symbol": symbol,
                    "dimension": dimension,
                    "summary": detail.get("summary", {}),
                    "truncated": True,
                    "reason": "数据过大，已只返回摘要"
                }, ensure_ascii=False, sort_keys=True)
            
            return json_str
            
        except Exception as e:
            return json.dumps({"error": f"获取细节失败: {str(e)}"}, ensure_ascii=False)

    def fetch_stock_analysis(self, symbol: str, days: int = 60) -> str:
        """按需获取任意股票的完整分析数据"""
        try:
            from web.data_service import fetch_stock_full_analysis

            logger.info(f"fetch_stock_analysis called: symbol={symbol}, days={days}")

            result = fetch_stock_full_analysis(symbol, days=days)
            result["source"] = "on_demand_fetch"

            json_str = json.dumps(result, ensure_ascii=False, default=str, sort_keys=True)

            if len(json_str) > self.MAX_DETAIL_CHARS:
                summary_result = {
                    "symbol": result.get("symbol"),
                    "query": result.get("query"),
                    "resolved": result.get("resolved"),
                    "source": "on_demand_fetch",
                    "truncated": True,
                }
                for key in ["money_flow", "technical", "valuation"]:
                    if key in result and "error" not in result[key]:
                        summary_result[key] = result[key]
                return json.dumps(summary_result, ensure_ascii=False, default=str, sort_keys=True)

            return json_str

        except ImportError as e:
            return json.dumps({"error": f"数据服务不可用: {str(e)}"}, ensure_ascii=False)
        except Exception as e:
            logger.exception(f"fetch_stock_analysis error: {e}")
            return json.dumps({"error": f"获取数据失败: {str(e)}"}, ensure_ascii=False)

    # ==================== 兼容旧接口 ====================
    
    def get_tools_schema(self) -> list:
        """获取工具的 JSON Schema 定义（兼容旧接口）"""
        return [skill.get_openai_tool_schema() for skill in self.getSkills()]

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """执行工具调用（兼容旧接口）"""
        if not tool_name or not tool_name.strip():
            return json.dumps({"error": "工具名不能为空"}, ensure_ascii=False)

        if tool_name == "get_page_full_snapshot":
            return self.get_page_full_snapshot()
        elif tool_name == "get_page_overview":
            return self.get_page_overview()
        elif tool_name == "get_data_detail":
            return self.get_data_detail(
                category=arguments.get("category", ""),
                key=arguments.get("key", ""),
                level=arguments.get("level", "summary")
            )
        elif tool_name == "get_stock_dimension_detail":
            return self.get_stock_dimension_detail(
                symbol=arguments.get("symbol", ""),
                dimension=arguments.get("dimension", ""),
                level=arguments.get("level", "summary")
            )
        elif tool_name == "fetch_stock_analysis":
            return self.fetch_stock_analysis(
                symbol=arguments.get("symbol", ""),
                days=arguments.get("days", 60)
            )
        else:
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)


# 全局实例
_skillkit_instance = None


def get_page_data_skillkit() -> PageDataSkillkit:
    """获取 PageDataSkillkit 单例"""
    global _skillkit_instance
    if _skillkit_instance is None:
        _skillkit_instance = PageDataSkillkit()
    return _skillkit_instance
