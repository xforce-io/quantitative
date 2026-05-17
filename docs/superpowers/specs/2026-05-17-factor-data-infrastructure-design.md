# Factor Data Infrastructure Design

**Date:** 2026-05-17  
**Scope:** 为 multi_sleeve_rotation 策略新增四类因子数据的基础设施，支持后续 petri pipeline 逐因子验证。

---

## 背景

当前策略使用三因子截面打分（动量0.45 + 低波动0.35 + 相对强度0.20），数据全部来自日频收盘价（`data/tushare/*.csv`）。为了支持以下四类新因子的验证，需要先建好数据基础设施：

1. **ETF份额**：捕捉资金流入/流出作为动量置信度过滤
2. **行业PE/PB历史分位**：过滤估值过高的板块，避免追泡沫
3. **PMI时序**：作为 regime 判断的领先指标辅助
4. **扩展ETF候选池**：从15只扩展到22只，增加轮动选择维度

---

## 设计原则

- **现有代码不动**：`long_rotation_discovery.py` 和 `data/tushare/*.csv` 完全不受影响
- **默认关闭**：所有新因子在 `strategy_spec.json` 中默认 `enabled: false`，建好基础设施后逐 petri run 验证
- **零新依赖**：SQLite 是 Python 标准库，不引入额外包

---

## 数据存储

### `data/factors.db`（SQLite）

多数据源（Tushare + Yahoo Finance），以月频为粒度存储。

```sql
-- ETF月度份额（万份）
CREATE TABLE etf_shares (
    date    TEXT,       -- YYYY-MM-DD，月末最后交易日
    symbol  TEXT,       -- ETF代码，如 512480.SH
    shares  REAL,       -- 份额（万份）
    PRIMARY KEY (date, symbol)
);

-- 行业指数月末估值及历史分位
CREATE TABLE industry_valuation (
    date    TEXT,
    symbol  TEXT,       -- 行业指数代码，如 000933.SH
    pe_ttm  REAL,
    pb_mrq  REAL,
    pe_pct  REAL,       -- PE历史分位，过去5年滚动，0-1
    pb_pct  REAL,       -- PB历史分位
    PRIMARY KEY (date, symbol)
);

-- 月度PMI
CREATE TABLE macro_pmi (
    date        TEXT PRIMARY KEY,   -- 当月公布日期
    mfg_pmi     REAL,               -- 制造业PMI
    non_mfg_pmi REAL                -- 非制造业PMI
);

-- 扩展ETF池代理指数月度价格
CREATE TABLE proxy_prices_ext (
    date    TEXT,
    symbol  TEXT,       -- 代理指数代码
    close   REAL,
    PRIMARY KEY (date, symbol)
);
```

---

## 扩展 ETF 候选池（+7只，15→22）

| ETF名称 | 代码 | 代理指数 | 说明 |
|---------|------|----------|------|
| 华夏物联网ETF | 516220.SH | 中证物联网指数 | 科技/通信 |
| 储能ETF | 561910.SH | 中证储能指数 | 新能源链 |
| 自由现金流ETF | 159201.SZ | 中证自由现金流指数 | 价值/红利替代 |
| 消费电子ETF | 159732.SZ | 中证消费电子指数 | 科技消费 |
| 创新药ETF | 159992.SZ | 中证创新药指数 | 医药细分 |
| 中证A500ETF | 512050.SH | 中证A500指数 | 宽基 |
| 恒生科技ETF | 513180.SH | 恒生科技指数 | 港股科技 |

代理指数历史数据要求：有效覆盖至2010年；缺失数据标注 `proxy_data_from`，不补填。

---

## 文件结构

```
quant/data/
  fetchers/
    __init__.py
    etf_shares.py       ← Tushare fund_share
    valuation.py        ← Tushare index_dailybasic，计算滚动分位
    macro_pmi.py        ← Tushare cn_pmi
    proxy_ext.py        ← Tushare index_daily + Yahoo Finance

  factor_store.py       ← 统一查询接口

scripts/
  refresh_factors.py    ← 全量初始化 & 增量更新入口

data/
  factors.db            ← 新增
  tushare/*.csv         ← 不动
```

---

## FactorStore 接口

```python
class FactorStore:
    def __init__(self, db_path: str = "data/factors.db"): ...

    def get_etf_shares(self, symbols: list[str], date: str) -> dict[str, float]:
        """返回 {symbol: 份额(万份)}"""

    def get_valuation_pct(self, symbols: list[str], date: str) -> dict[str, dict]:
        """返回 {symbol: {"pe_pct": float, "pb_pct": float}}"""

    def get_pmi(self, date: str) -> float | None:
        """返回当月制造业PMI，无数据返回 None"""

    def get_proxy_prices_ext(self, symbols: list[str], start: str, end: str) -> pd.DataFrame:
        """返回月度价格 DataFrame，index=DatetimeIndex，columns=symbols"""
```

所有方法接受 `date` 为 `YYYY-MM-DD` 月末日期，返回该月数据。查不到返回空 dict / None，不抛异常。

---

## 回测脚本集成方式

### 新因子开关（`strategy_spec.json`）

```json
"multi_factor_config": {
  "factors": [
    {"name": "momentum",          "weight": 0.45, "enabled": true},
    {"name": "low_volatility",    "weight": 0.35, "enabled": true},
    {"name": "relative_strength", "weight": 0.20, "enabled": true},
    {"name": "shares_momentum",   "weight": 0.10, "enabled": false},
    {"name": "valuation_pct",     "weight": 0.05, "enabled": false}
  ]
}
```

权重开启新因子时，按比例归一化，现有三因子权重自动缩减。

### PMI 辅助 regime（`strategy_spec.json`）

```json
"risk_on_rule": {
  "method": "simple_threshold",
  "lookback_months": 6,
  "min_return": 0.0,
  "pmi_filter": {"enabled": false, "min_pmi": 50.0}
}
```

`enabled: false` 时行为与当前完全相同。

---

## 数据刷新流程

```bash
python scripts/refresh_factors.py           # 首次全量（2010至今）
python scripts/refresh_factors.py --update  # 每月末增量更新
```

流程：
1. 按顺序运行四个 Fetcher
2. upsert 写入 `factors.db`（重复日期覆盖）
3. 打印每张表最新日期和总行数
4. 单个 Fetcher 失败单独报错，不中断其他 Fetcher

---

## 测试策略

每个 Fetcher 有独立单元测试：
- 数据行数 > 0
- 日期连续性检查（月末对齐）
- 关键字段无全 NULL

`FactorStore` 集成测试：
- 用已知日期查询，断言返回值在合理范围
- 查不到数据时返回空而不抛异常

---

## 后续 Petri 验证顺序（基础设施建好后）

| Run | 验证内容 | 假设 |
|-----|----------|------|
| run-021 | 扩展ETF池（22只） | 更大候选池提升顺风期选股质量 |
| run-022 | ETF份额因子 | 份额动量作为动量置信度过滤 |
| run-023 | 估值分位因子 | PE/PB高分位时压制该板块权重 |
| run-024 | PMI regime辅助 | PMI < 50时顺风期信号打折扣 |

每轮只开一个开关，其余保持 `enabled: false`。
