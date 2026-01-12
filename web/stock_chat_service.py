"""
Stock Chat Service - 个股分析对话服务
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

import yaml


def _load_llm_config() -> Dict[str, Any]:
    """从 config/dolphin.yaml 加载 AI Agent 配置"""
    config_path = Path(__file__).parent.parent / "config" / "dolphin.yaml"
    if not config_path.exists():
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def _expand_env_vars(value: str) -> str:
    """展开环境变量 ${VAR_NAME}"""
    if not isinstance(value, str):
        return value
    pattern = r'\$\{(\w+)\}'
    def replacer(match):
        var_name = match.group(1)
        return os.getenv(var_name, "")
    return re.sub(pattern, replacer, value)


def get_llm_settings() -> Dict[str, str]:
    """
    获取 LLM 配置（API 地址、API Key、模型名称）

    Returns:
        {"api_base": "...", "api_key": "...", "model": "..."}
    """
    llm_config = _load_llm_config()

    if not llm_config:
        # 回退到环境变量
        return {
            "api_base": os.getenv("LLM_API_BASE", "http://localhost:8000"),
            "api_key": os.getenv("LLM_API_KEY", ""),
            "model": os.getenv("LLM_MODEL", "qwen-plus")
        }

    # 获取默认模型
    default_model_key = llm_config.get("default", "qwen-plus")
    llms = llm_config.get("llms", {})
    clouds = llm_config.get("clouds", {})

    model_config = llms.get(default_model_key, {})
    cloud_name = model_config.get("cloud", "aliyun")
    cloud_config = clouds.get(cloud_name, {})

    api_base = _expand_env_vars(cloud_config.get("api", ""))
    api_key = _expand_env_vars(cloud_config.get("api_key", ""))
    model_name = model_config.get("model_name", default_model_key)

    return {
        "api_base": api_base,
        "api_key": api_key,
        "model": model_name
    }


@dataclass
class StockContext:
    """股票分析上下文"""
    symbol: str
    name: str
    inst_net_flow: float = 0.0
    retail_net_flow: float = 0.0
    inst_inflow_days: int = 0
    total_days: int = 0
    latest_close: float = 0.0
    ma_trend: str = ""
    macd_signal: str = ""
    rsi_value: float = 0.0
    rsi_status: str = ""
    tech_interpretation: str = ""
    pe_ttm: float = 0.0
    pe_percentile: float = 0.0
    pb: float = 0.0
    pb_percentile: float = 0.0
    valuation_status: str = ""
    total_mv: float = 0.0

    def to_context_string(self) -> str:
        lines = [
            f"## {self.name} ({self.symbol}) 分析数据",
            "", "### 资金流向",
            f"- 机构净流入: {self.inst_net_flow:+.2f} 亿元",
            f"- 散户净流入: {self.retail_net_flow:+.2f} 亿元",
            f"- 机构流入天数: {self.inst_inflow_days} / {self.total_days} 天",
            "", "### 技术形态",
            f"- 最新收盘价: {self.latest_close:.2f} 元",
            f"- 均线趋势: {self.ma_trend or '暂无'}",
            f"- MACD 信号: {self.macd_signal or '暂无'}",
        ]
        if self.rsi_value:
            lines.append(f"- RSI: {self.rsi_value:.1f} ({self.rsi_status})")
        if self.tech_interpretation:
            lines.append(f"- 技术解读: {self.tech_interpretation}")
        lines.extend(["", "### 估值分析"])
        if self.pe_ttm:
            lines.append(f"- PE(TTM): {self.pe_ttm:.1f} (历史分位: {self.pe_percentile:.0f}%)")
        if self.pb:
            lines.append(f"- PB: {self.pb:.2f} (历史分位: {self.pb_percentile:.0f}%)")
        if self.valuation_status:
            lines.append(f"- 估值状态: {self.valuation_status}")
        if self.total_mv:
            lines.append(f"- 总市值: {self.total_mv:.0f} 亿元")
        return "\n".join(lines)


def build_stock_context(symbol, name, flow_data=None, tech_analysis=None, valuation_data=None):
    """从各维度分析数据构建股票上下文"""
    ctx = StockContext(symbol=symbol, name=name)
    if flow_data and "error" not in flow_data:
        inst = flow_data.get("institutional", {})
        retail = flow_data.get("retail", {})
        ctx.inst_net_flow = inst.get("total_net_flow", 0) / 1e8
        ctx.retail_net_flow = retail.get("total_net_flow", 0) / 1e8
        ctx.inst_inflow_days = inst.get("net_inflow_days", 0)
        ctx.total_days = flow_data.get("total_days", 0)
    if tech_analysis:
        ctx.latest_close = tech_analysis.get("latest_close", 0)
        ctx.ma_trend = tech_analysis.get("ma_trend", "")
        ctx.macd_signal = tech_analysis.get("macd_signal", "")
        ctx.rsi_value = tech_analysis.get("rsi_value", 0)
        ctx.rsi_status = tech_analysis.get("rsi_status", "")
        ctx.tech_interpretation = tech_analysis.get("interpretation", "")
    if valuation_data and "error" not in valuation_data:
        latest = valuation_data.get("latest", {})
        percentile = valuation_data.get("percentile", {})
        status = valuation_data.get("status", {})
        ctx.pe_ttm = latest.get("pe_ttm", 0) or 0
        ctx.pe_percentile = percentile.get("pe_ttm", 0) or 0
        ctx.pb = latest.get("pb", 0) or 0
        ctx.pb_percentile = percentile.get("pb", 0) or 0
        statuses = list(status.values())
        if statuses:
            low = sum(1 for s in statuses if s in ["低估", "偏低"])
            high = sum(1 for s in statuses if s in ["高估", "偏高"])
            ctx.valuation_status = "偏低估" if low > high else ("偏高估" if high > low else "中性")
        ctx.total_mv = (latest.get("total_mv", 0) or 0) / 10000
    return ctx


def build_system_prompt(context):
    """构建系统提示词"""
    return f"""你是一位专业的 A 股投资分析师，擅长技术分析、资金流向分析和估值分析。
你正在为用户分析 {context.name} ({context.symbol}) 这只股票。

以下是该股票的最新分析数据：

{context.to_context_string()}

## 对话要求
1. 基于数据: 严格基于上述分析数据回答用户问题
2. 专业客观: 提供专业的分析视角，但避免给出明确的买卖建议
3. 风险提示: 适时提醒投资风险
4. 通俗易懂: 对专业术语提供简明解释
5. 结构清晰: 使用 Markdown 格式

请用中文回答用户的问题。"""


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


class StockChatService:
    """股票分析对话服务"""

    def __init__(self, api_base: str = None, api_key: str = None, model: str = None):
        # 从配置文件读取默认值
        settings = get_llm_settings()
        self.api_base = api_base or settings["api_base"]
        self.api_key = api_key or settings["api_key"]
        self.model = model or settings["model"]

    def get_config_display(self) -> Dict[str, str]:
        """获取配置信息（用于 UI 展示）"""
        # 隐藏 API Key 中间部分
        if self.api_key and len(self.api_key) > 10:
            masked_key = self.api_key[:6] + "****" + self.api_key[-4:]
        else:
            masked_key = "未配置"

        return {
            "api_base": self.api_base,
            "api_key": masked_key,
            "model": self.model
        }

    def chat(self, message, context, history=None):
        """同步对话"""
        full_response = ""
        for chunk in self.chat_stream(message, context, history):
            full_response += chunk
        return full_response

    def chat_stream(self, message, context, history=None):
        """流式对话"""
        try:
            import httpx
        except ImportError:
            yield "请安装 httpx: pip install httpx"
            return

        if not self.api_base:
            yield "LLM API 未配置，请在 config/dolphin.yaml 中配置"
            return

        system_prompt = build_system_prompt(context)
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for msg in history[-10:]:
                messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": message})

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            with httpx.Client(timeout=60.0) as client:
                with client.stream(
                    "POST",
                    f"{self.api_base}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                        "temperature": 0.7,
                        "max_tokens": 2000
                    },
                    headers=headers
                ) as response:
                    if response.status_code != 200:
                        yield f"API 调用失败: {response.status_code}"
                        return

                    for line in response.iter_lines():
                        if line:
                            line = line.strip()
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_str)
                                    if "choices" in data and len(data["choices"]) > 0:
                                        delta = data["choices"][0].get("delta", {})
                                        if "content" in delta:
                                            yield delta["content"]
                                except json.JSONDecodeError:
                                    pass
        except Exception as e:
            yield f"对话出错: {str(e)}"


# 兼容旧代码的常量
LLM_API_BASE = get_llm_settings().get("api_base", "")
LLM_MODEL = get_llm_settings().get("model", "qwen-plus")
