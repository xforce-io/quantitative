#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ETF 板块轮动策略
ETF Sector Rotation Strategy

核心逻辑：
  动量得分 = 20日涨幅 × 1.0 + 60日涨幅 × 1.5

排名规则：
  - 前 1/3：强势主线，持有
  - 中 1/3：震荡观望
  - 后 1/3：弱势回避

信号规则（来自原文第五部分）：
  1. 长短期共振向上 → 主线加速，持有
  2. 短期转负、中期为正 → 只守不攻，不加仓
  3. 排名持续下滑 → 减仓信号
  4. 得分回升但 20 日仍负 → 不抄底
  5. 资源/贵金属大涨 + 金融得分转负 → 滞胀预警，收缩仓位
"""

import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from quant.core.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 默认 ETF 池：A 股主流行业/主题 ETF（可按需修改）
# ---------------------------------------------------------------------------
DEFAULT_ETF_POOL = {
    # 宽基指数
    "510300.SH": "沪深300",
    "510500.SH": "中证500",
    "159915.SZ": "创业板",
    "588000.SH": "科创50",
    # 科技 / AI
    "512760.SH": "芯片",
    "589090.SH": "科创AI",
    "515000.SH": "科技",
    "512980.SH": "传媒",
    # 新能源
    "515030.SH": "新能源车",
    "515790.SH": "光伏",
    "159326.SZ": "电网设备",      # 修正：原 516200 是证券ETF
    # 资源 / 大宗
    "518880.SH": "黄金ETF",
    "561570.SH": "油气",           # 修正：原 159632 是纳斯达克ETF
    "512400.SH": "有色金属",
    "515220.SH": "煤炭",
    # 制造 / 军工 / 航天
    "512660.SH": "军工",
    "159667.SZ": "工业母机",       # 修正：原 516980 是证券ETF
    "563380.SH": "航空航天",       # 新增
    # 消费 / 医疗
    "561100.SH": "消费电子",       # 修正：原 159869 是游戏ETF
    "512010.SH": "医药",
    "512170.SH": "医疗",
    "159985.SZ": "豆粕",
    # 金融 / 地产
    "512880.SH": "证券",
    "512200.SH": "房地产",
    "513050.SH": "中概互联网",
}

# 信号类型
SIGNAL_LONG_SHORT_MOMENTUM = "长短期共振向上"      # 强势持有
SIGNAL_SHORT_WEAK_MID_OK   = "短期转负中期为正"    # 只守不攻
SIGNAL_RANK_DECLINING      = "排名持续下滑"        # 减仓信号
SIGNAL_SCORE_UP_SHORT_NEG  = "得分回升但短期仍负"  # 不抄底
SIGNAL_STAGFLATION_WARN    = "滞胀预警"            # 收缩仓位
SIGNAL_NORMAL              = "无明显信号"


class ETFRotationStrategy:
    """
    ETF 板块轮动排名策略

    使用方式：
        strategy = ETFRotationStrategy(provider)
        result = strategy.run()
        print(result.ranking)
    """

    def __init__(
        self,
        provider,
        etf_pool: Optional[Dict[str, str]] = None,
        short_window: int = 20,
        long_window: int = 60,
        short_weight: float = 1.0,
        long_weight: float = 1.5,
        min_history_days: int = 70,   # 至少需要的历史天数（交易日 × 1.4 缓冲）
        request_sleep: float = 0.3,   # 每次 API 请求间隔（秒），避免触发频率限制
    ):
        """
        Args:
            provider: TushareProvider 实例
            etf_pool: {ts_code: 名称} 字典，None 则使用内置默认池
            short_window: 短期动量窗口（交易日），默认 20
            long_window:  中期动量窗口（交易日），默认 60
            short_weight: 短期权重，默认 1.0
            long_weight:  中期权重，默认 1.5
            min_history_days: 拉取的历史数据日历天数，默认 70
            request_sleep: 请求间隔（秒）
        """
        self.provider = provider
        self.etf_pool = etf_pool or DEFAULT_ETF_POOL
        self.short_window = short_window
        self.long_window = long_window
        self.short_weight = short_weight
        self.long_weight = long_weight
        self.min_history_days = min_history_days
        self.request_sleep = request_sleep

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def run(self, as_of_date: Optional[str] = None) -> "RotationResult":
        """
        执行轮动排名，返回 RotationResult。

        Args:
            as_of_date: 计算基准日期 YYYYMMDD，None 表示今天
        """
        end_date = as_of_date or datetime.now().strftime("%Y%m%d")
        start_date = self._lookback_start(end_date)

        logger.info(f"ETF 轮动排名：{start_date} → {end_date}，ETF 池大小 {len(self.etf_pool)}")

        records = self._fetch_all(start_date, end_date)

        if not records:
            logger.error("未能获取任何 ETF 数据，请检查 token 和网络")
            return RotationResult(ranking=pd.DataFrame(), signals={}, as_of_date=end_date)

        ranking = self._build_ranking(records)
        signals = self._generate_signals(ranking)

        return RotationResult(ranking=ranking, signals=signals, as_of_date=end_date)

    # ------------------------------------------------------------------
    # 数据获取
    # ------------------------------------------------------------------

    def _lookback_start(self, end_date: str) -> str:
        """往前推足够的日历天数（交易日约为日历天 × 0.7，多留 buffer）"""
        calendar_days = int(self.long_window / 0.7) + 30
        dt = datetime.strptime(end_date, "%Y%m%d") - timedelta(days=calendar_days)
        return dt.strftime("%Y%m%d")

    def _fetch_all(self, start_date: str, end_date: str) -> Dict[str, pd.Series]:
        """
        批量拉取所有 ETF 的收盘价序列。

        Returns:
            {ts_code: close_series（DatetimeIndex，按日期升序）}
        """
        results = {}
        total = len(self.etf_pool)
        for i, (ts_code, name) in enumerate(self.etf_pool.items(), 1):
            try:
                df = self.provider.get_fund_data(ts_code, start_date, end_date)
                if df is None or df.empty:
                    logger.warning(f"[{i}/{total}] {name}({ts_code}) 数据为空，跳过")
                    continue

                # 统一取 close 列，按日期升序排列
                close = self._extract_close(df)
                if len(close) < self.long_window + 1:
                    logger.warning(
                        f"[{i}/{total}] {name}({ts_code}) 数据不足 {self.long_window+1} 条（实际 {len(close)}），跳过"
                    )
                    continue

                results[ts_code] = close
                logger.info(f"[{i}/{total}] {name}({ts_code}) OK，{len(close)} 条")

            except Exception as e:
                logger.warning(f"[{i}/{total}] {name}({ts_code}) 拉取失败：{e}")

            if self.request_sleep > 0 and i < total:
                time.sleep(self.request_sleep)

        return results

    def _extract_close(self, df: pd.DataFrame) -> pd.Series:
        """从 provider 返回的 DataFrame 中提取 close 序列（DatetimeIndex，升序）"""
        col = "close"
        if col not in df.columns:
            raise ValueError(f"DataFrame 中缺少 close 列，实际列：{list(df.columns)}")

        # index 可能是 DatetimeIndex 或 trade_date 列
        if isinstance(df.index, pd.DatetimeIndex):
            series = df[col].copy()
        elif "trade_date" in df.columns:
            df = df.copy()
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            series = df.set_index("trade_date")[col]
        else:
            series = df[col].copy()

        series = series.sort_index()
        series = pd.to_numeric(series, errors="coerce").dropna()
        return series

    # ------------------------------------------------------------------
    # 得分计算
    # ------------------------------------------------------------------

    def _calc_return(self, close: pd.Series, window: int) -> float:
        """计算 N 日涨幅（最近 N+1 条数据）"""
        if len(close) < window + 1:
            return np.nan
        price_now = close.iloc[-1]
        price_n = close.iloc[-(window + 1)]
        if price_n == 0:
            return np.nan
        return (price_now - price_n) / price_n

    def _calc_score(self, ret20: float, ret60: float) -> float:
        """动量得分 = 20日涨幅 × 1.0 + 60日涨幅 × 1.5"""
        if np.isnan(ret20) or np.isnan(ret60):
            return np.nan
        return ret20 * self.short_weight + ret60 * self.long_weight

    def _build_ranking(self, records: Dict[str, pd.Series]) -> pd.DataFrame:
        """构建排名表"""
        rows = []
        for ts_code, close in records.items():
            ret20 = self._calc_return(close, self.short_window)
            ret60 = self._calc_return(close, self.long_window)
            score = self._calc_score(ret20, ret60)
            rows.append(
                {
                    "ts_code": ts_code,
                    "name": self.etf_pool.get(ts_code, ts_code),
                    "ret_20d": ret20,
                    "ret_60d": ret60,
                    "score": score,
                    "latest_close": close.iloc[-1],
                    "latest_date": close.index[-1].strftime("%Y-%m-%d")
                    if hasattr(close.index[-1], "strftime")
                    else str(close.index[-1]),
                }
            )

        df = pd.DataFrame(rows).dropna(subset=["score"])
        df = df.sort_values("score", ascending=False).reset_index(drop=True)
        df.index += 1  # 排名从 1 开始

        n = len(df)
        df["tier"] = pd.cut(
            df.index,
            bins=[0, n // 3, 2 * n // 3, n],
            labels=["强势主线", "震荡观望", "弱势回避"],
            include_lowest=True,
        )

        # 百分比格式化（保留原始数值用于逻辑判断，display 列用于展示）
        df["ret_20d_pct"] = df["ret_20d"].map(lambda x: f"{x*100:.2f}%")
        df["ret_60d_pct"] = df["ret_60d"].map(lambda x: f"{x*100:.2f}%")

        return df

    # ------------------------------------------------------------------
    # 信号生成
    # ------------------------------------------------------------------

    def _generate_signals(self, ranking: pd.DataFrame) -> Dict[str, str]:
        """
        对每只 ETF 生成交易信号，基于原文第五部分的 5 条判断规则。

        Returns:
            {ts_code: signal_str}
        """
        if ranking.empty:
            return {}

        n = len(ranking)
        signals = {}

        # 计算排名分位，用于判断"排名持续下滑"（本次只能看单截面，历史对比需外部维护）
        for _, row in ranking.iterrows():
            ts_code = row["ts_code"]
            ret20 = row["ret_20d"]
            ret60 = row["ret_60d"]
            rank_pos = row.name  # 1-based rank
            rank_pct = rank_pos / n

            if ret20 > 0 and ret60 > 0:
                signal = SIGNAL_LONG_SHORT_MOMENTUM   # 规则1：双正 → 主线
            elif ret20 <= 0 and ret60 > 0:
                signal = SIGNAL_SHORT_WEAK_MID_OK     # 规则2：短弱中强 → 观望
            elif row["score"] > 0 and ret20 < 0:
                signal = SIGNAL_SCORE_UP_SHORT_NEG    # 规则4：得分回升但短期仍负
            elif rank_pct > 0.67:
                signal = SIGNAL_RANK_DECLINING        # 规则3：后 1/3 → 弱势
            else:
                signal = SIGNAL_NORMAL

            signals[ts_code] = signal

        # 规则5：滞胀预警——检测黄金/能源板块强势 + 金融转负
        self._check_stagflation_signal(ranking, signals)

        return signals

    def _check_stagflation_signal(
        self, ranking: pd.DataFrame, signals: Dict[str, str]
    ) -> None:
        """
        规则5：若黄金/能源类 ETF 得分大幅为正，同时金融类得分为负，
        触发全局滞胀预警，对金融类 ETF 标注预警信号。
        """
        GOLD_CODES   = {"518880.SH", "159801.SZ"}
        ENERGY_CODES = {"159632.SZ", "515220.SH"}
        FIN_CODES    = {"512880.SH", "510310.SH"}

        score_map = ranking.set_index("ts_code")["score"].to_dict()
        ret60_map = ranking.set_index("ts_code")["ret_60d"].to_dict()

        gold_strong   = any(score_map.get(c, 0) > 0.05 for c in GOLD_CODES)
        energy_strong = any(score_map.get(c, 0) > 0.05 for c in ENERGY_CODES)
        fin_weak      = any(ret60_map.get(c, 0) < 0 for c in FIN_CODES)

        if (gold_strong or energy_strong) and fin_weak:
            logger.warning("⚠️  滞胀预警：贵金属/能源强势 + 金融转负，建议收缩整体仓位")
            for code in FIN_CODES:
                if code in signals:
                    signals[code] = SIGNAL_STAGFLATION_WARN


class RotationResult:
    """轮动策略输出结果"""

    def __init__(
        self,
        ranking: pd.DataFrame,
        signals: Dict[str, str],
        as_of_date: str,
    ):
        self.ranking = ranking
        self.signals = signals
        self.as_of_date = as_of_date

    def print_report(self, top_n: int = 20) -> None:
        """打印排名报告"""
        print(f"\n{'='*70}")
        print(f"  ETF 板块轮动排名  ({self.as_of_date})")
        print(f"  得分 = 20日涨幅×1.0 + 60日涨幅×1.5")
        print(f"{'='*70}")

        if self.ranking.empty:
            print("  无数据")
            return

        display_cols = ["name", "ret_20d_pct", "ret_60d_pct", "score", "tier"]
        df = self.ranking[display_cols].head(top_n).copy()
        df["score"] = df["score"].map(lambda x: f"{x:.4f}")

        # 加上信号列
        df["signal"] = self.ranking["ts_code"].head(top_n).map(
            lambda c: self.signals.get(c, "")
        ).values

        print(df.to_string())
        print(f"\n共计 {len(self.ranking)} 只 ETF 参与排名")

        # 打印各 tier 汇总
        for tier in ["强势主线", "震荡观望", "弱势回避"]:
            sub = self.ranking[self.ranking["tier"] == tier]
            names = "、".join(sub["name"].tolist())
            print(f"\n【{tier}】{names}")

    def to_csv(self, path: str) -> None:
        """导出排名到 CSV"""
        self.ranking.to_csv(path, encoding="utf-8-sig")
        logger.info(f"排名已导出：{path}")


# ---------------------------------------------------------------------------
# 便捷入口：直接运行
# ---------------------------------------------------------------------------

def run_etf_rotation(token: str = None, top_n: int = 20) -> RotationResult:
    """
    一键运行 ETF 轮动排名。

    Args:
        token: Tushare token，None 则从环境变量 TUSHARE_TOKEN 读取
        top_n: 打印前 N 名

    Returns:
        RotationResult
    """
    from quant.data.implementations.tushare_provider import TushareProvider

    config = {}
    if token:
        config["token"] = token

    provider = TushareProvider(config)
    strategy = ETFRotationStrategy(provider)
    result = strategy.run()
    result.print_report(top_n=top_n)
    return result


if __name__ == "__main__":
    run_etf_rotation()
