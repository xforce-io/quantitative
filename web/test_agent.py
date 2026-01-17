#!/usr/bin/env python
"""测试 Agent Manager 的工具调用和回复生成"""

import os
import sys

# 添加项目路径
sys.path.insert(0, '/Users/xupeng/lab/quantitative_trading')

# 模拟 Streamlit session_state
class MockSessionState:
    def __init__(self):
        self._data = {}
        
    def __contains__(self, key):
        return key in self._data
    
    def __getitem__(self, key):
        return self._data.get(key)
    
    def __setitem__(self, key, value):
        self._data[key] = value
        
    def get(self, key, default=None):
        return self._data.get(key, default)

# Mock streamlit
import types
st_mock = types.ModuleType('streamlit')
st_mock.session_state = MockSessionState()
sys.modules['streamlit'] = st_mock

# 导入并初始化 page_registry
from web.page_registry import PageDataRegistry

# 创建一个带有市场数据的 registry
registry = PageDataRegistry(page_name="Money Flow", page_path="pages/1_Money_Flow.py")
registry.set_date_range("20260112", "20260113")

# 注册一些测试数据
test_market_data = {
    "institutional_analysis": {
        "total_net_flow": -180572000000,  # -1805.72 亿
    },
    "retail_analysis": {
        "total_net_flow": 179365000000,  # 1793.65 亿
    },
    "north_money": {
        "north_money_in": 0,
    },
    "market_sentiment": {
        "sentiment": "divergent_retail_buy",
        "reason": "机构卖出，散户买入，需要警惕"
    },
    "industry_ranking": {
        "top_10_inflow": [
            {"name": "黄金概念", "net_amount": 2700000000},
            {"name": "电网设备", "net_amount": 2100000000},
        ],
        "top_10_outflow": []
    }
}

registry.register_market_summary(test_market_data, "20260113")
st_mock.session_state["page_registry"] = registry

print("=" * 50)
print("Registry 内容检查：")
print("=" * 50)
overview = registry.get_overview()
print(f"Page: {overview['page']}")
print(f"Categories: {overview['categories']}")
print(f"Total entries: {overview['total_entries']}")

snapshot = registry.get_full_snapshot()
print(f"\nSnapshot data keys: {list(snapshot.get('data', {}).keys())}")
if 'market' in snapshot.get('data', {}):
    print(f"Market data: {snapshot['data']['market']}")

print("\n" + "=" * 50)
print("测试 Agent Manager：")
print("=" * 50)

from web.agent_manager import run_agent_stream

print("\n发送查询: '总结内容'")
print("-" * 50)

events = []
for event in run_agent_stream("test_session", "总结内容"):
    events.append(event)
    event_type = event.get("type", "")
    
    if event_type == "delta":
        print(event.get("content", ""), end="", flush=True)
    elif event_type == "tool_call":
        print(f"\n[Tool Call] {event.get('name')}: {event.get('args')}")
    elif event_type == "tool_result":
        result = event.get("result", "")
        print(f"[Tool Result] {event.get('name')}: {result[:200]}...")
    elif event_type == "done":
        print(f"\n[Done] Full response length: {len(event.get('content', ''))}")
    elif event_type == "error":
        print(f"\n[Error] {event.get('message')}")

print("\n" + "-" * 50)
print(f"Total events: {len(events)}")
print(f"Event types: {[e.get('type') for e in events]}")
