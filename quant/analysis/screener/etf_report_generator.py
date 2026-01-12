#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ETF筛选报告生成器
包含估值分析的增强版报告
"""

import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class ETFReportGenerator:
    """ETF筛选报告生成器"""
    
    def __init__(self, output_dir: str = None):
        """初始化报告生成器
        
        Args:
            output_dir: 输出目录，默认为 reports/etf_screening/YYYYMMDD
        """
        if output_dir is None:
            from datetime import datetime
            today = datetime.now().strftime("%Y%m%d")
            output_dir = f"reports/etf_screening/{today}"
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_markdown_report(self, results_df: pd.DataFrame, 
                                 report_title: str = "ETF动量与估值筛选分析报告",
                                 include_valuation: bool = True) -> str:
        """
        生成Markdown格式的筛选报告（增强版，包含估值分析）
        
        Args:
            results_df: 筛选结果DataFrame
            report_title: 报告标题
            include_valuation: 是否包含估值分析部分
            
        Returns:
            Markdown格式的报告文本
        """
        if results_df.empty:
            return "# 无数据\n\n未获取到有效的ETF分析数据。"
        
        # 报告时间
        now = datetime.now()
        timestamp = now.strftime("%Y年%m月%d日 %H:%M:%S")
        
        lines = [
            f"# {report_title}",
            "",
            f"**生成时间**: {timestamp}",
            "",
            "## 📊 执行摘要",
            "",
            f"- **总分析ETF数量**: {len(results_df)}",
            f"- **通过筛选ETF数量**: {len(results_df[results_df['passes_screening'] == True])}",
            f"- **通过率**: {len(results_df[results_df['passes_screening'] == True]) / len(results_df) * 100:.1f}%",
            ""
        ]
        
        # 通过筛选的ETF
        passed_etfs = results_df[results_df['passes_screening'] == True]
        
        if not passed_etfs.empty:
            # 等级分布
            grade_counts = passed_etfs['grade'].value_counts()
            lines.extend([
                "### 推荐等级分布",
                *[f"- **{grade}级**: {count}只" for grade, count in grade_counts.items()],
                ""
            ])
            
            # 估值分布（如果有估值数据）
            if include_valuation and 'valuation_level' in passed_etfs.columns:
                valuation_counts = passed_etfs['valuation_level'].value_counts()
                lines.extend([
                    "### 估值水平分布",
                    *[f"- **{level}**: {count}只" for level, count in valuation_counts.items()],
                    ""
                ])
            
            # 详细列表
            lines.extend([
                "### 详细列表",
                ""
            ])
            
            # 根据是否有估值数据选择表头
            if include_valuation and 'valuation_level' in passed_etfs.columns:
                # 🆕 增加风险警告列
                has_risk_warnings = 'risk_warnings' in passed_etfs.columns
                
                if has_risk_warnings:
                    lines.append(
                        "| 排名 | ETF代码 | ETF名称 | 类别 | 综合得分 | 等级 | "
                        "1月收益率 | 3月收益率 | 6月收益率 | 12月收益率 | RSI | 估值水平 | 估值区间 | 风险警告 |"
                    )
                    lines.append(
                        "|------|---------|---------|------|----------|------|"
                        "-----------|-----------|-----------|------------|-----|----------|----------|----------|"
                    )
                else:
                    lines.append(
                        "| 排名 | ETF代码 | ETF名称 | 类别 | 综合得分 | 等级 | "
                        "1月收益率 | 3月收益率 | 6月收益率 | 12月收益率 | RSI | 估值水平 | 估值区间 |"
                    )
                    lines.append(
                        "|------|---------|---------|------|----------|------|"
                        "-----------|-----------|-----------|------------|-----|----------|----------|"
                    )
                
                for idx, (_, row) in enumerate(passed_etfs.iterrows(), 1):
                    base_row = (
                        f"| {idx} | {row['ts_code']} | {row['name']} | {row['category']} | "
                        f"{row['overall_score']:.3f} | {row['grade']} | "
                        f"{row['1m_return']:.1f}% | {row['3m_return']:.1f}% | "
                        f"{row['6m_return']:.1f}% | {row['12m_return']:.1f}% | "
                        f"{row['rsi']:.1f} | {row.get('valuation_level', '合理')} | "
                        f"{row.get('valuation_zone', '合理区')} |"
                    )
                    
                    if has_risk_warnings:
                        warnings = row.get('risk_warnings', '').replace('|', ', ') if row.get('risk_warnings') else '-'
                        base_row += f" {warnings} |"
                    
                    lines.append(base_row)
            else:
                lines.append(
                    "| 排名 | ETF代码 | ETF名称 | 类别 | 综合得分 | 等级 | "
                    "1月收益率 | 3月收益率 | 6月收益率 | 12月收益率 | RSI |"
                )
                lines.append(
                    "|------|---------|---------|------|----------|------|"
                    "-----------|-----------|-----------|------------|-----|"
                )
                
                for idx, (_, row) in enumerate(passed_etfs.iterrows(), 1):
                    lines.append(
                        f"| {idx} | {row['ts_code']} | {row['name']} | {row['category']} | "
                        f"{row['overall_score']:.3f} | {row['grade']} | "
                        f"{row['1m_return']:.1f}% | {row['3m_return']:.1f}% | "
                        f"{row['6m_return']:.1f}% | {row['12m_return']:.1f}% | "
                        f"{row['rsi']:.1f} |"
                    )
            
            lines.append("")
        
        # 估值分析详情（新增）
        if include_valuation and 'valuation_level' in results_df.columns and not passed_etfs.empty:
            lines.extend([
                "## 💎 估值分析详情",
                "",
                "### 估值水平说明",
                "",
                "- **极度低估** (分位数 < 10%): 价格处于历史极低水平，可能存在投资机会",
                "- **低估** (分位数 10-25%): 价格偏低，值得关注",
                "- **偏低** (分位数 25-40%): 价格略低于历史平均",
                "- **合理** (分位数 40-60%): 价格处于合理区间",
                "- **偏高** (分位数 60-75%): 价格略高于历史平均",
                "- **高估** (分位数 75-90%): 价格偏高，需谨慎",
                "- **极度高估** (分位数 > 90%): 价格处于历史极高水平，风险较大",
                "",
                "### 各估值水平ETF列表",
                ""
            ])
            
            # 按估值水平分组
            valuation_groups = {
                '极度低估': passed_etfs[passed_etfs['valuation_level'] == '极度低估'],
                '低估': passed_etfs[passed_etfs['valuation_level'] == '低估'],
                '偏低': passed_etfs[passed_etfs['valuation_level'] == '偏低'],
                '合理': passed_etfs[passed_etfs['valuation_level'] == '合理'],
                '偏高': passed_etfs[passed_etfs['valuation_level'] == '偏高'],
                '高估': passed_etfs[passed_etfs['valuation_level'] == '高估'],
                '极度高估': passed_etfs[passed_etfs['valuation_level'] == '极度高估']
            }
            
            for val_level, etfs in valuation_groups.items():
                if not etfs.empty:
                    emoji = {
                        '极度低估': '🟢',
                        '低估': '🟢',
                        '偏低': '🟡',
                        '合理': '⚪',
                        '偏高': '🟡',
                        '高估': '🔴',
                        '极度高估': '🔴'
                    }.get(val_level, '⚪')
                    
                    lines.append(f"#### {emoji} {val_level} ({len(etfs)}只)")
                    lines.append("")
                    for _, row in etfs.iterrows():
                        percentile = row.get('valuation_percentile', 50)
                        mr_signal = row.get('mean_reversion_signal', '持有')
                        lines.append(
                            f"- **{row['name']}** ({row['ts_code']}): "
                            f"分位数 {percentile:.1f}% | 均值回归信号: {mr_signal}"
                        )
                    lines.append("")

        # 🆕 未通过筛选的ETF列表
        failed_etfs = results_df[results_df['passes_screening'] == False]
        if not failed_etfs.empty:
            lines.extend([
                "## ❌ 未通过筛选的ETF",
                "",
                f"**未通过数量**: {len(failed_etfs)} 只",
                "",
                "| 代码 | 名称 | 类别 | 综合得分 | 等级 | 未通过原因 |",
                "|------|------|------|----------|------|------------|"
            ])

            # 按综合得分倒序排列，显示接近通过的ETF
            failed_sorted = failed_etfs.sort_values('overall_score', ascending=False)

            for idx, (_, row) in enumerate(failed_sorted.iterrows(), 1):
                # 获取未通过原因
                failed_reasons = row.get('failed_reasons', [])
                if isinstance(failed_reasons, list):
                    reasons_str = ' | '.join(failed_reasons) if failed_reasons else '综合得分不足'
                else:
                    reasons_str = str(failed_reasons) if failed_reasons else '综合得分不足'

                lines.append(
                    f"| {row['ts_code']} | {row['name']} | {row['category']} | "
                    f"{row['overall_score']:.3f} | {row['grade']} | {reasons_str} |"
                )

            lines.append("")
            lines.append("### 💡 未通过ETF分析说明")
            lines.append("")
            lines.append("- **接近通过**：综合得分 0.50-0.59 的ETF值得关注，可能在后续表现改善")
            lines.append("- **收益率不足**：短期动量较弱，等待趋势确认")
            lines.append("- **RSI超买/超卖**：技术指标显示短期风险，等待调整")
            lines.append("")

        # 市场概况分析
        lines.extend([
            "## 📈 市场概况分析",
            "",
            "### 各类别表现统计",
            ""
        ])
        
        # 按类别统计
        category_stats = []
        for category in results_df['category'].unique():
            cat_data = results_df[results_df['category'] == category]
            cat_passed = cat_data[cat_data['passes_screening'] == True]
            
            category_stats.append({
                '类别': category,
                '总数': len(cat_data),
                '通过数': len(cat_passed),
                '通过率': f"{len(cat_passed) / len(cat_data) * 100:.1f}%",
                '平均综合得分': f"{cat_data['overall_score'].mean():.3f}",
                '平均1月收益率': f"{cat_data['1m_return'].mean():.1f}%",
                '平均3月收益率': f"{cat_data['3m_return'].mean():.1f}%",
                '平均6月收益率': f"{cat_data['6m_return'].mean():.1f}%"
            })
        
        if category_stats:
            cat_df = pd.DataFrame(category_stats)
            lines.append(cat_df.to_markdown(index=False))
            lines.append("")
        
        # 收益率分布分析
        lines.extend([
            "## 📊 收益率分布分析",
            ""
        ])
        
        for period_name, column in [
            ('1个月', '1m_return'),
            ('3个月', '3m_return'),
            ('6个月', '6m_return'),
            ('12个月', '12m_return')
        ]:
            returns = results_df[column]
            positive_count = (returns > 0).sum()
            negative_count = (returns < 0).sum()
            
            lines.extend([
                f"### {period_name}收益率统计",
                "",
                f"- **平均收益率**: {returns.mean():.2f}%",
                f"- **中位数收益率**: {returns.median():.2f}%",
                f"- **最高收益率**: {returns.max():.2f}%",
                f"- **最低收益率**: {returns.min():.2f}%",
                f"- **正收益ETF数量**: {positive_count} ({positive_count / len(returns) * 100:.1f}%)",
                f"- **负收益ETF数量**: {negative_count} ({negative_count / len(returns) * 100:.1f}%)",
                ""
            ])
        
        # 筛选标准说明
        lines.extend([
            "## 📋 筛选标准说明",
            "",
            "本次筛选采用以下标准：",
            "",
            "### 动量指标要求",
            "- 1个月收益率 ≥ 3.0%",
            "- 3个月收益率 ≥ 8.0%",
            "- 6个月收益率 ≥ 15.0%",
            "- 12个月收益率 ≥ 20.0%",
            "- RSI指标在40-80区间",
            "- MACD信号为正向",
            ""
        ])
        
        if include_valuation:
            lines.extend([
                "### 估值调整机制（趋势优先策略）",
                "- **趋势强劲时**：估值仅作风险提示，不影响评分（让利润奔跑）",
                "- **趋势反转时**：",
                "  - MACD死叉 + 极度高估：-0.30",
                "  - 动能转负 + 极度高估：-0.25",
                "  - 动能衰竭 + 高估：-0.15",
                "  - 减速滞涨：-0.10",
                "- **低估机会**：极度低估 +0.15，低估 +0.10",
                ""
            ])
        
        lines.extend([
            "### 综合评分说明",
            "- **A级** (≥0.80): 良好，推荐",
            "- **B级** (0.60-0.79): 可考虑",
            "- **C级** (<0.60): 表现较弱，不推荐",
            "",
            "## ⚠️ 风险提示",
            "",
            "1. **历史表现不代表未来收益**：本分析基于历史数据，不保证未来表现。",
            "2. **市场风险**：ETF投资存在市场波动风险，可能面临本金损失。",
            "3. **流动性风险**：部分ETF可能存在流动性不足的问题。",
            "4. **跟踪误差**：ETF可能无法完全复制标的指数表现。",
            "5. **估值仅供参考**：估值分析基于历史价格分位数，不代表绝对价值。",
            "6. **投资建议**：请结合个人风险承受能力和投资目标做出决策。",
            "",
            "---",
            f"*本报告由ETF动量与估值筛选系统自动生成*"
        ])
        
        return "\n".join(lines)
    
    def save_report(self, report_content: str, prefix: str = "etf_screening") -> Path:
        """
        保存报告到文件
        
        Args:
            report_content: 报告内容
            prefix: 文件名前缀
            
        Returns:
            保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}_report.md"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        return filepath
    
    def generate_and_save_report(self, results_df: pd.DataFrame, 
                                 report_title: str = "ETF动量与估值筛选分析报告",
                                 prefix: str = "etf_screening",
                                 include_valuation: bool = True) -> Path:
        """
        生成并保存报告
        
        Args:
            results_df: 筛选结果DataFrame
            report_title: 报告标题
            prefix: 文件名前缀
            include_valuation: 是否包含估值分析
            
        Returns:
            保存的文件路径
        """
        report_content = self.generate_markdown_report(
            results_df, 
            report_title=report_title,
            include_valuation=include_valuation
        )
        return self.save_report(report_content, prefix=prefix)

