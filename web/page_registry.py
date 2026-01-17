"""
Page Data Registry - 页面数据注册器与快照结构（v2.0 通用架构）

本模块负责收集并维护"本次页面渲染所展示的业务数据"。
实现设计文档中的数据层架构。

v2.0 改进：
- 通用 register_data() 接口支持任意数据类型
- 内置摘要提取器 + 自定义提取器机制
- 向后兼容的便捷方法
"""

import uuid
import json
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class DataEntry:
    """通用数据条目"""
    raw_data: Any
    summary: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now().isoformat())


class PageDataRegistry:
    """
    页面数据注册器（v2.0 通用架构）
    
    用于收集页面渲染时的业务数据，并生成可供 Agent 工具读取的快照。
    存放位置：st.session_state["page_registry"]
    
    数据存储结构：
    - _data: {category: {key: DataEntry}}
    - category: stock / market / industry / ranking / news / custom
    - key: 具体标识（如股票代码、"summary" 等）
    """
    
    # 版本号
    SNAPSHOT_VERSION = "2.0"
    
    # 数据类别常量
    CATEGORY_STOCK = "stock"
    CATEGORY_MARKET = "market"
    CATEGORY_INDUSTRY = "industry"
    CATEGORY_RANKING = "ranking"
    CATEGORY_NEWS = "news"
    CATEGORY_CUSTOM = "custom"
    
    # 允许出现在快照中的字段白名单（安全过滤）
    ALLOWED_SNAPSHOT_KEYS = {
        "snapshot_version", "snapshot_id", "page", "data", "generated_at"
    }
    
    def __init__(self, page_name: str = "", page_path: str = ""):
        """初始化注册器"""
        self._snapshot_id = str(uuid.uuid4())[:8]
        self._page_name = page_name
        self._page_path = page_path
        self._params: Dict[str, Any] = {}
        self._data: Dict[str, Dict[str, DataEntry]] = defaultdict(dict)
        self._created_at = datetime.now()
    
    # ========== 核心通用接口 ==========
    
    def register_data(
        self,
        category: str,
        key: str,
        data: Any,
        summary_extractor: Optional[Callable[[Any], Dict]] = None,
        metadata: Optional[Dict] = None
    ):
        """
        通用数据注册接口
        
        Args:
            category: 数据类别（stock/market/industry/ranking/news/custom）
            key: 数据键（如股票代码、"summary"、行业名称等）
            data: 原始数据
            summary_extractor: 可选，自定义摘要提取函数
            metadata: 可选，附加元信息
            
        Examples:
            # 注册个股数据
            registry.register_data("stock", "000001.SZ", {
                "name": "平安银行",
                "money_flow": flow_data,
                "technical": tech_data
            })
            
            # 注册市场汇总
            registry.register_data("market", "summary", summary_data)
            
            # 自定义数据（带自定义摘要提取）
            registry.register_data(
                "custom", "my_analysis",
                raw_data,
                summary_extractor=lambda d: {"key_metric": d["value"]}
            )
        """
        if summary_extractor:
            try:
                summary = summary_extractor(data)
            except Exception as e:
                summary = {"error": f"摘要提取失败: {str(e)}"}
        else:
            summary = self._auto_summarize(category, data)
        
        entry = DataEntry(
            raw_data=data,
            summary=summary,
            metadata=metadata or {}
        )
        self._data[category][key] = entry
    
    def _auto_summarize(self, category: str, data: Any) -> Dict:
        """根据类别自动提取摘要"""
        extractor = self._get_builtin_extractor(category)
        if extractor:
            try:
                return extractor(data)
            except Exception:
                pass
        
        # 兜底：返回数据的键列表或长度
        if isinstance(data, dict):
            return {"keys": list(data.keys())[:10], "type": "dict", "count": len(data)}
        elif isinstance(data, (list, tuple)):
            return {"length": len(data), "type": "list"}
        elif hasattr(data, "shape"):  # DataFrame
            return {"shape": list(data.shape), "type": "dataframe", "columns": list(getattr(data, 'columns', []))[:10]}
        else:
            return {"type": str(type(data).__name__)}
    
    def _get_builtin_extractor(self, category: str) -> Optional[Callable]:
        """获取内置摘要提取器"""
        extractors = {
            self.CATEGORY_STOCK: self._extract_stock_summary,
            self.CATEGORY_MARKET: self._extract_market_summary,
            self.CATEGORY_INDUSTRY: self._extract_industry_summary,
        }
        return extractors.get(category)
    
    # ========== 内置摘要提取器 ==========
    
    def _extract_stock_summary(self, data: Dict) -> Dict:
        """提取个股摘要"""
        summary = {"name": data.get("name", "")}
        
        # 资金流向
        if "money_flow" in data and data["money_flow"]:
            mf = data["money_flow"]
            if "error" not in mf:
                inst = mf.get("institutional", {})
                retail = mf.get("retail", {})
                summary["inst_net_flow_yi"] = round(inst.get("total_net_flow", 0) / 1e8, 2)
                summary["retail_net_flow_yi"] = round(retail.get("total_net_flow", 0) / 1e8, 2)
                summary["money_flow_trend"] = mf.get("trend", "")
                summary["inst_inflow_days"] = inst.get("net_inflow_days", 0)
                summary["total_days"] = mf.get("total_days", 0)
        
        # 技术分析
        if "technical" in data and data["technical"]:
            tech = data["technical"]
            summary["ma_trend"] = tech.get("ma_trend", "")
            summary["macd_signal"] = tech.get("macd_signal", "")
            summary["rsi_value"] = tech.get("rsi_value")
            summary["latest_close"] = tech.get("latest_close")
        
        # 估值
        if "valuation" in data and data["valuation"]:
            val = data["valuation"]
            if "error" not in val:
                latest = val.get("latest", {})
                percentile = val.get("percentile", {})
                summary["pe_ttm"] = latest.get("pe_ttm")
                summary["pb"] = latest.get("pb")
                summary["pe_percentile"] = percentile.get("pe_ttm")
                summary["pb_percentile"] = percentile.get("pb")
        
        return summary
    
    def _extract_market_summary(self, data: Dict) -> Dict:
        """提取市场汇总摘要"""
        if "error" in data:
            return {"error": data["error"]}
        
        inst = data.get("institutional_analysis", {})
        retail = data.get("retail_analysis", {})
        north = data.get("north_money", {})
        sentiment = data.get("market_sentiment", {})
        ranking = data.get("industry_ranking", {})
        
        summary = {
            "inst_net_flow_yi": round(inst.get("total_net_flow", 0) / 1e8, 2),
            "retail_net_flow_yi": round(retail.get("total_net_flow", 0) / 1e8, 2),
            "north_net_flow_yi": round(north.get("north_money_in", 0) / 1e8, 2),
            "sentiment": sentiment.get("sentiment", "N/A"),
            "sentiment_reason": sentiment.get("reason", ""),
        }
        
        # Top 5 流入/流出行业
        top_inflow = ranking.get("top_10_inflow", [])[:5]
        top_outflow = ranking.get("top_10_outflow", [])[:5]
        
        if top_inflow:
            summary["top_5_inflow"] = [
                {"name": item["name"], "net_yi": round(item["net_amount"] / 1e8, 2)}
                for item in top_inflow
            ]
        if top_outflow:
            summary["top_5_outflow"] = [
                {"name": item["name"], "net_yi": round(item["net_amount"] / 1e8, 2)}
                for item in top_outflow
            ]
        
        return summary
    
    def _extract_industry_summary(self, data: Any) -> Dict:
        """提取行业数据摘要"""
        if hasattr(data, "iterrows"):  # DataFrame
            records = []
            for _, row in data.head(10).iterrows():
                records.append({
                    "name": row.get("name", ""),
                    "net_yi": round(row.get("net_amount", 0) / 1e8, 2),
                    "pct_change": round(row.get("pct_change", 0), 2) if row.get("pct_change") else None,
                })
            return {
                "total_industries": len(data),
                "top_10": records
            }
        elif isinstance(data, list):
            return {"count": len(data), "sample": data[:5] if data else []}
        elif isinstance(data, dict):
            return data  # 已经是摘要格式
        else:
            return {"type": str(type(data).__name__)}
    
    # ========== 便捷方法（向后兼容）==========
    
    def set_page_info(self, name: str, path: str = "", params: Dict[str, Any] = None):
        """设置页面信息"""
        self._page_name = name
        self._page_path = path
        self._params = params or {}
    
    def set_date_range(self, start_date: str, end_date: str):
        """设置时间范围"""
        self._params["date_range"] = {"start": start_date, "end": end_date}
    
    def register_stock(
        self,
        symbol: str,
        name: str,
        money_flow: Optional[Dict] = None,
        technical: Optional[Dict] = None,
        valuation: Optional[Dict] = None
    ):
        """便捷方法：注册个股数据（向后兼容）"""
        data = {"name": name}
        if money_flow:
            data["money_flow"] = money_flow
        if technical:
            data["technical"] = technical
        if valuation:
            data["valuation"] = valuation
        
        self.register_data(self.CATEGORY_STOCK, symbol, data)
    
    def register_market_summary(self, summary: Dict[str, Any], display_date: str = ""):
        """便捷方法：注册市场汇总数据（向后兼容）"""
        if not summary or "error" in summary:
            return
        self.register_data(
            self.CATEGORY_MARKET,
            "summary",
            summary,
            metadata={"display_date": display_date}
        )
    
    def register_industry_data(self, df, is_aggregated: bool = False):
        """便捷方法：注册行业数据（向后兼容）"""
        if df is None or (hasattr(df, 'empty') and df.empty):
            return
        self.register_data(
            self.CATEGORY_INDUSTRY,
            "flow_ranking",
            df,
            metadata={"is_aggregated": is_aggregated}
        )
    
    def register_chart(self, chart_id: str, chart_type: str, title: str, symbols: List[str]):
        """注册图表"""
        self.register_data(
            self.CATEGORY_CUSTOM,
            f"chart_{chart_id}",
            {
                "id": chart_id,
                "type": chart_type,
                "title": title,
                "related_symbols": symbols
            }
        )
    
    def mark_stock_expanded(self, symbol: str):
        """标记股票详情已展开"""
        if "ui_state" not in self._params:
            self._params["ui_state"] = {"expanded": []}
        if symbol not in self._params["ui_state"]["expanded"]:
            self._params["ui_state"]["expanded"].append(symbol)
    
    # ========== 快照与查询 ==========
    
    def get_overview(self) -> Dict[str, Any]:
        """获取轻量概览"""
        # 统计各类别数据
        category_stats = {}
        for category, entries in self._data.items():
            category_stats[category] = {
                "count": len(entries),
                "keys": list(entries.keys())[:10]
            }
        
        return {
            "snapshot_version": self.SNAPSHOT_VERSION,
            "snapshot_id": self._snapshot_id,
            "page": {
                "name": self._page_name,
                "path": self._page_path,
            },
            "date_range": self._params.get("date_range", {}),
            "categories": category_stats,
            "total_entries": sum(len(e) for e in self._data.values()),
            "generated_at": datetime.now().isoformat()
        }
    
    def get_full_snapshot(self) -> Dict[str, Any]:
        """获取完整快照（含摘要）"""
        snapshot = {
            "snapshot_version": self.SNAPSHOT_VERSION,
            "snapshot_id": self._snapshot_id,
            "page": {
                "name": self._page_name,
                "path": self._page_path,
                "params": self._params
            },
            "data": {},
            "generated_at": datetime.now().isoformat()
        }
        
        for category, entries in self._data.items():
            snapshot["data"][category] = {}
            for key, entry in entries.items():
                snapshot["data"][category][key] = {
                    "summary": entry.summary,
                    "metadata": entry.metadata,
                    "has_raw_data": entry.raw_data is not None
                }
        
        return snapshot
    
    def get_data_detail(self, category: str, key: str, level: str = "summary") -> Dict[str, Any]:
        """
        获取指定数据的细节
        
        Args:
            category: 数据类别
            key: 数据键
            level: 详细程度（summary / raw）
        """
        if category not in self._data or key not in self._data[category]:
            return {"error": f"未找到 {category}/{key} 数据"}
        
        entry = self._data[category][key]
        
        if level == "summary":
            return {
                "category": category,
                "key": key,
                "summary": entry.summary,
                "metadata": entry.metadata
            }
        elif level == "raw":
            raw = entry.raw_data
            # 处理 DataFrame
            if hasattr(raw, "to_dict"):
                return {
                    "category": category,
                    "key": key,
                    "summary": entry.summary,
                    "data": raw.head(30).to_dict(orient="records")
                }
            elif isinstance(raw, dict):
                return {
                    "category": category,
                    "key": key,
                    "summary": entry.summary,
                    "data": raw
                }
            else:
                return {
                    "category": category,
                    "key": key,
                    "summary": entry.summary,
                    "data": str(raw)[:2000]
                }
        else:
            return {"error": f"不支持的 level: {level}"}
    
    # 向后兼容：保留旧的接口名
    def get_dimension_detail(self, symbol: str, dimension: str, level: str = "summary") -> Dict[str, Any]:
        """向后兼容：获取股票维度数据"""
        result = self.get_data_detail(self.CATEGORY_STOCK, symbol, level)
        if "error" in result:
            return result
        
        # 从 summary 中提取维度信息
        summary = result.get("summary", {})
        
        # 构造旧格式的返回
        if dimension == "money_flow":
            dim_summary = {
                "inst_net_flow_yi": summary.get("inst_net_flow_yi"),
                "retail_net_flow_yi": summary.get("retail_net_flow_yi"),
                "inst_inflow_days": summary.get("inst_inflow_days"),
                "total_days": summary.get("total_days"),
            }
        elif dimension == "technical":
            dim_summary = {
                "ma_trend": summary.get("ma_trend"),
                "macd_signal": summary.get("macd_signal"),
                "rsi_value": summary.get("rsi_value"),
                "latest_close": summary.get("latest_close"),
            }
        elif dimension == "valuation":
            dim_summary = {
                "pe_ttm": summary.get("pe_ttm"),
                "pb": summary.get("pb"),
                "pe_percentile": summary.get("pe_percentile"),
                "pb_percentile": summary.get("pb_percentile"),
            }
        else:
            dim_summary = summary
        
        return {
            "symbol": symbol,
            "name": summary.get("name", ""),
            "dimension": dimension,
            "summary": dim_summary
        }
    
    def get_registered_symbols(self) -> List[str]:
        """获取已注册的股票代码列表"""
        return list(self._data.get(self.CATEGORY_STOCK, {}).keys())
    
    def get_snapshot_id(self) -> str:
        """获取快照 ID"""
        return self._snapshot_id


def get_page_registry():
    """从 session_state 获取 PageDataRegistry 实例"""
    import streamlit as st
    
    if "page_registry" not in st.session_state:
        st.session_state.page_registry = PageDataRegistry()
    
    return st.session_state.page_registry


def init_page_registry(page_name: str, page_path: str = "") -> PageDataRegistry:
    """初始化或重置 PageDataRegistry"""
    import streamlit as st
    
    registry = PageDataRegistry(page_name=page_name, page_path=page_path)
    st.session_state.page_registry = registry
    return registry
