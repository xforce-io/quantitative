# 2026-05-18 — ETF 份额拆分未复权导致 real_etf 模式数据污染

## 摘要

调查 run-030 (PMI overlay) `real_etf_subset` fold 7 (2021-01~06) candidate -71.83% / MDD -48.72% 异常时，发现这并非策略问题，而是**底层 ETF 价格数据未做复权**。Tushare `fund_daily` API 返回**不复权**价格；当 ETF 发生份额拆分（一拆 N）时历史 NAV 不会反向调整，结果在拆分当日表现为虚假的 -50% 至 -80% 单日"暴跌"。

## 范围

扫描 `config/rotation_universe.yaml` 全部 38 只 ETF 2010-2025 日级收益，发现 **12 只**存在单日 |return| > 20% 的异常事件（全部都是份额拆分/合并的特征跳变，跌完不反弹）：

| ETF | 日期 | 单日跳变 | 推断 |
|---|---|---|---|
| 512170 医疗ETF | 2021-02-25 | -68.10% | 1:3 拆分 |
| 159928 消费ETF | 2021-06-25 | -74.47% | 1:4 拆分 |
| 512010 医药ETF | 2021-06-28 | -73.92% | 1:4 拆分 |
| 512890 红利低波ETF | 2021-10-25 | -51.13% | 1:2 拆分 |
| **513100 纳指ETF** | **2022-01-14** | **-80.45%** | **1:5 拆分（real_etf_full fold 5 -97% 元凶）** |
| 515220 煤炭ETF | 2024-04-12 | -50.34% | 1:2 拆分 |
| 512200 房地产ETF | 2024-08-12 | +170.07% | 反向合并 |
| 510310 沪深300ETF | 2024-09-23 | +100.94% | 反向合并 |
| 159949 创业板50 | 2024-10-08 | +20.02% | 临界，疑似 |
| 159922 中证500 | 2024-12-02 | -61.45% | 拆分 |
| 512800 银行ETF | 2025-07-07 | -49.69% | 1:2 拆分 |
| 512000 券商ETF | 2025-08-04 | -49.74% | 1:2 拆分 |

## 影响

| 数据模式 | 是否受影响 | 备注 |
|---|---|---|
| `index_proxy` | ✗ | 使用代理指数（000016/000300 等），无份额拆分概念，未受污染 |
| `real_etf_subset` | ✓ 严重 | 12 只候选中 159928/512010 在 H1 2021 同时被策略选中，单折 -71.83% |
| `real_etf_full` | ✓ 严重 | 38 只候选中 12 只被污染，2022-H1 因 513100 拆分爆出 -97.09% |

run-016/018/019/021/024/029/030 的 real_etf_full 指标都可能不可信 —— 它们恰好在污染窗口内没被策略选中，掩盖了底层数据问题。

## 根因

`quant/data/providers.py:418-426` 通过 Tushare 的 `fund_daily` API 取 ETF 日级行情：

```python
df = self._fetch_with_backward_paging(
    lambda s, e: self.provider.fund_daily(ts_code=ts_symbol, start_date=s, end_date=e),
    ...
)
```

Tushare `fund_daily` 默认返回**不复权**价格。份额拆分时基金净值会按比例缩减（如 1:4 拆分后单位 NAV 变为原来的 1/4），但历史价格不会反向调整。正确做法是通过 `pro.fund_adj(ts_code=...)` 拿到每个交易日的复权因子，将历史 close 乘以 `adj_factor / adj_factor[最新]` 得到前复权 NAV。

## 短期修复（已落地）

`scripts/long_rotation_discovery.py` 新增 `MAX_SINGLE_DAY_ABS_RET = 0.25` 常量，在 `fetch_etf_monthly_prices` 内对每只 ETF 的日级 return 做扫描，任一日 |return| > 25% 直接 `[SKIP anomaly]` 出局，stderr 打印异常日期。

- 优点：5 分钟改完，立即挡住污染数据进入回测
- 代价：real_etf_subset 候选从 12 只减到 10 只，real_etf_full 从 38 只减到 26 只；统计意义略弱
- 局限：只挡了"已发生"的拆分，将来 ETF 拆分时下一轮回测之前会先污染一次（除非定期跑扫描）

## 长期修复（P0-3，未启动）

正确做法是在 `quant/data/providers.py` 的 ETF 取数路径里应用 Tushare 复权因子：

1. 新增 `_fetch_etf_adjusted_close()`：先调 `fund_adj(ts_code=...)` 拿 `(trade_date, adj_factor)` 序列，再将 `fund_daily` 的 close 乘以 `adj_factor / adj_factor.iloc[-1]`
2. 清空 `cache/` 中所有 ETF 历史，强制重拉
3. 重跑近期 KEEP runs（029、030）作为新基线，刷新 `experiments/history.json`
4. 然后才能启用 `.petri/generated/roles/reviewer/gate.yaml` 中 `real_etf_subset.candidate_mdd >= -0.25` 的 TODO 检查
5. 保留短期修复的 anomaly filter 作为防御层（多一道守门）

## 调查证据

```python
# 单日跳变扫描脚本（可重跑）
from scripts.long_rotation_discovery import load_universe, UNIVERSE_YAML
from quant.services.data_service import DataService, PriceRequest

ds = DataService()
for entry in load_universe(str(UNIVERSE_YAML)):
    df = ds.get_price(PriceRequest(symbol=entry.symbol, start='20100101',
                                   end='20251231', asset_type='etf'))
    close = df['close'].astype(float)
    extreme = close.pct_change()[lambda r: r.abs() > 0.20].dropna()
    for dt, x in extreme.items():
        print(f"{entry.symbol} {dt.date()} {x*100:+.2f}%")
```

## 时间线

- 2026-05-18 ~12:00 — petri pipeline 完成 run-030（PMI overlay），reviewer KEEP（attempt 2）
- 2026-05-18 ~14:00 — review 阶段发现 KEEP 决策可疑，启动 P0-1（gate 加 real_etf_full 不退步检查）
- 2026-05-18 ~17:00 — P0-1 落地，干跑暴露 real_etf_subset MDD 长期挂在 -48.72%，启动 P0-2
- 2026-05-18 ~17:45 — 数据扫描确认 12 只 ETF 数据污染，短期 anomaly filter 落地
