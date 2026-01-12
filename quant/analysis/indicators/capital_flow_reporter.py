#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资金流向报告生成器 (Capital Flow Reporter)

提供资金流向分析的报告生成功能，包括：
1. HTML格式报告
2. Markdown格式报告
3. 综合分析报告（包含图表）
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import yaml

from quant.core.logging_config import get_logger
logger = get_logger(__name__)



class CapitalFlowReporter:
    """资金流向报告生成器"""

    def __init__(self, output_dir: str = 'reports/capital_flow'):
        """
        初始化报告生成器

        Args:
            output_dir: 输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 加载股票名称映射
        self.symbol_name_map = self._load_symbol_names()

    def _load_symbol_names(self) -> Dict[str, str]:
        """从配置文件加载股票代码到名称的映射"""
        try:
            config_path = Path('config/screens.yaml')
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            name_map = {}
            screens = config.get('screens', {})

            for screen_name, stocks in screens.items():
                for symbol, info in stocks.items():
                    if isinstance(info, dict) and 'name' in info:
                        name_map[symbol] = info['name']

            return name_map
        except Exception as e:
            logger.info("加载股票名称映射失败: {e}")
            return {}

    def _get_stock_display_name(self, symbol: str) -> str:
        """获取股票的显示名称"""
        name = self.symbol_name_map.get(symbol, '')
        if name:
            return f"{name}({symbol})"
        return symbol

    def generate_industry_report(
        self,
        industry_data: Dict[str, Dict[str, Any]],
        chart_paths: Dict[str, str],
        days: int = 30,
        format: str = 'html'
    ) -> str:
        """
        生成行业资金流向报告

        Args:
            industry_data: 行业数据
            chart_paths: 图表路径字典
            days: 分析天数
            format: 报告格式 ('html' 或 'markdown')

        Returns:
            报告文件路径
        """
        if format == 'html':
            return self._generate_html_report(industry_data, chart_paths, days)
        else:
            return self._generate_markdown_report(industry_data, chart_paths, days)

    def _generate_html_report(
        self,
        industry_data: Dict[str, Dict[str, Any]],
        chart_paths: Dict[str, str],
        days: int
    ) -> str:
        """生成HTML格式报告"""

        # 排序行业数据
        sorted_industries = sorted(
            industry_data.items(),
            key=lambda x: x[1].get('avg_inflow_ratio', 0),
            reverse=True
        )

        # HTML模板
        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>行业资金流向分析报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Microsoft YaHei', 'SimHei', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            border-radius: 8px;
        }}

        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 15px;
            margin-bottom: 30px;
            font-size: 32px;
        }}

        h2 {{
            color: #34495e;
            margin-top: 40px;
            margin-bottom: 20px;
            font-size: 24px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }}

        h3 {{
            color: #555;
            margin-top: 25px;
            margin-bottom: 15px;
            font-size: 18px;
        }}

        .meta-info {{
            background: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
        }}

        .meta-item {{
            margin: 5px 15px;
        }}

        .meta-label {{
            font-weight: bold;
            color: #7f8c8d;
        }}

        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}

        .summary-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}

        .summary-card.inflow {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }}

        .summary-card.outflow {{
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }}

        .summary-card h3 {{
            color: white;
            margin-top: 0;
            font-size: 16px;
            opacity: 0.9;
        }}

        .summary-value {{
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
        }}

        .summary-label {{
            font-size: 14px;
            opacity: 0.8;
        }}

        .chart-container {{
            margin: 30px 0;
            text-align: center;
        }}

        .chart-container img {{
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}

        thead {{
            background: #3498db;
            color: white;
        }}

        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}

        tbody tr:hover {{
            background: #f8f9fa;
        }}

        .positive {{
            color: #e74c3c;
            font-weight: bold;
        }}

        .negative {{
            color: #3498db;
            font-weight: bold;
        }}

        .neutral {{
            color: #95a5a6;
        }}

        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }}

        .badge.high {{
            background: #e74c3c;
            color: white;
        }}

        .badge.medium {{
            background: #f39c12;
            color: white;
        }}

        .badge.low {{
            background: #95a5a6;
            color: white;
        }}

        .score-bar {{
            background: #ecf0f1;
            height: 20px;
            border-radius: 10px;
            overflow: hidden;
            margin: 5px 0;
        }}

        .score-fill {{
            height: 100%;
            background: linear-gradient(90deg, #3498db 0%, #e74c3c 100%);
            transition: width 0.3s ease;
        }}

        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 2px solid #ecf0f1;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }}

        .insights {{
            background: #fff9e6;
            border-left: 4px solid #f39c12;
            padding: 15px 20px;
            margin: 20px 0;
            border-radius: 4px;
        }}

        .insights h4 {{
            color: #f39c12;
            margin-bottom: 10px;
        }}

        .insights ul {{
            list-style-position: inside;
            color: #555;
        }}

        .insights li {{
            margin: 5px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 行业资金流向分析报告</h1>

        <div class="meta-info">
            <div class="meta-item">
                <span class="meta-label">分析周期：</span>{days} 天
            </div>
            <div class="meta-item">
                <span class="meta-label">行业数量：</span>{len(industry_data)} 个
            </div>
            <div class="meta-item">
                <span class="meta-label">生成时间：</span>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </div>

        <h2>📈 核心摘要</h2>
        <div class="summary-grid">
            {self._generate_summary_cards(industry_data)}
        </div>

        <h2>🔥 行业资金流向热力图</h2>
        <div class="chart-container">
            {self._generate_chart_html(chart_paths.get('heatmap'))}
        </div>

        <h2>🏆 行业资金流向排名</h2>
        <div class="chart-container">
            {self._generate_chart_html(chart_paths.get('ranking'))}
        </div>

        <h2>📋 行业汇总数据表</h2>
        {self._generate_industry_table(sorted_industries)}

        <h2>📊 个股明细数据</h2>
        {self._generate_stock_detail_table(sorted_industries)}

        <h2>📖 综合评分说明</h2>
        {self._generate_score_explanation()}

        <h2>💡 投资洞察</h2>
        <div class="insights">
            {self._generate_insights(industry_data)}
        </div>

        <div class="footer">
            <p>本报告由量化交易系统自动生成 | 仅供参考，不构成投资建议</p>
        </div>
    </div>
</body>
</html>
"""

        # 保存报告
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f'industry_flow_report_{timestamp}.html'

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return str(report_path)

    def _generate_markdown_report(
        self,
        industry_data: Dict[str, Dict[str, Any]],
        chart_paths: Dict[str, str],
        days: int
    ) -> str:
        """生成Markdown格式报告"""

        sorted_industries = sorted(
            industry_data.items(),
            key=lambda x: x[1].get('avg_inflow_ratio', 0),
            reverse=True
        )

        md_content = f"""# 📊 行业资金流向分析报告

**分析周期**: {days} 天
**行业数量**: {len(industry_data)} 个
**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📈 核心摘要

{self._generate_summary_markdown(industry_data)}

---

## 🔥 行业资金流向热力图

![行业资金流向热力图]({chart_paths.get('heatmap', '')})

---

## 🏆 行业资金流向排名

![行业资金流向排名]({chart_paths.get('ranking', '')})

---

## 📋 详细数据表

{self._generate_industry_table_markdown(sorted_industries)}

---

## 💡 投资洞察

{self._generate_insights_markdown(industry_data)}

---

*本报告由量化交易系统自动生成 | 仅供参考，不构成投资建议*
"""

        # 保存报告
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f'industry_flow_report_{timestamp}.md'

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        return str(report_path)

    def _generate_summary_cards(self, industry_data: Dict[str, Dict[str, Any]]) -> str:
        """生成摘要卡片HTML"""
        total_industries = len(industry_data)

        inflow_count = sum(1 for data in industry_data.values()
                          if data.get('avg_inflow_ratio', 0) > 0)
        outflow_count = total_industries - inflow_count

        avg_inflow = sum(data.get('avg_inflow_ratio', 0)
                        for data in industry_data.values()) / total_industries if total_industries > 0 else 0

        hot_sectors = sum(1 for data in industry_data.values()
                         if data.get('sector_heat_score', 0) > 60)

        cards_html = f"""
        <div class="summary-card inflow">
            <h3>资金流入行业</h3>
            <div class="summary-value">{inflow_count}</div>
            <div class="summary-label">个行业呈资金净流入</div>
        </div>

        <div class="summary-card outflow">
            <h3>资金流出行业</h3>
            <div class="summary-value">{outflow_count}</div>
            <div class="summary-label">个行业呈资金净流出</div>
        </div>

        <div class="summary-card">
            <h3>平均流入比例</h3>
            <div class="summary-value">{avg_inflow:+.2f}%</div>
            <div class="summary-label">行业平均资金流入比例</div>
        </div>

        <div class="summary-card">
            <h3>热门板块</h3>
            <div class="summary-value">{hot_sectors}</div>
            <div class="summary-label">个高热度行业</div>
        </div>
        """

        return cards_html

    def _generate_summary_markdown(self, industry_data: Dict[str, Dict[str, Any]]) -> str:
        """生成摘要Markdown"""
        total_industries = len(industry_data)

        inflow_count = sum(1 for data in industry_data.values()
                          if data.get('avg_inflow_ratio', 0) > 0)
        outflow_count = total_industries - inflow_count

        avg_inflow = sum(data.get('avg_inflow_ratio', 0)
                        for data in industry_data.values()) / total_industries if total_industries > 0 else 0

        hot_sectors = sum(1 for data in industry_data.values()
                         if data.get('sector_heat_score', 0) > 60)

        return f"""
- **资金流入行业**: {inflow_count} 个
- **资金流出行业**: {outflow_count} 个
- **平均流入比例**: {avg_inflow:+.2f}%
- **热门板块数量**: {hot_sectors} 个
"""

    def _generate_chart_html(self, chart_path: Optional[str]) -> str:
        """生成图表HTML"""
        if chart_path and Path(chart_path).exists():
            return f'<img src="{chart_path}" alt="图表">'
        return '<p style="color: #999;">图表未生成</p>'

    def _generate_industry_table(self, sorted_industries: List[Tuple[str, Dict]]) -> str:
        """生成行业数据表HTML"""
        rows = []

        for rank, (industry, data) in enumerate(sorted_industries, 1):
            avg_inflow = data.get('avg_inflow_ratio', 0)
            heat_score = data.get('sector_heat_score', 0)
            consistency = data.get('sector_consistency', 0)
            valid_stocks = data.get('valid_stocks', 0)

            # 计算绝对金额统计
            individual_analysis = data.get('individual_analysis', {})
            total_net_amount = 0
            total_max_inflow = 0
            total_max_outflow = 0

            for stock_data in individual_analysis.values():
                detailed = stock_data.get('detailed_metrics', {})
                total_net_amount += detailed.get('recent_5d_main_inflow', 0) * 100  # 转换为百分比的实际金额估算
                total_max_inflow += detailed.get('max_single_day_inflow', 0)
                total_max_outflow += detailed.get('max_single_day_outflow', 0)

            inflow_class = 'positive' if avg_inflow > 0 else 'negative' if avg_inflow < 0 else 'neutral'
            heat_badge = 'high' if heat_score > 60 else 'medium' if heat_score > 30 else 'low'

            row = f"""
            <tr>
                <td>{rank}</td>
                <td><strong>{industry}</strong></td>
                <td class="{inflow_class}">{avg_inflow:+.2f}%</td>
                <td class="{inflow_class}">{total_max_inflow/10000:.2f}万</td>
                <td class="negative">{total_max_outflow/10000:.2f}万</td>
                <td>
                    <span class="badge {heat_badge}">{heat_score:.0f}</span>
                    <div class="score-bar">
                        <div class="score-fill" style="width: {heat_score}%"></div>
                    </div>
                </td>
                <td>{consistency:.2f}</td>
                <td>{valid_stocks}</td>
            </tr>
            """
            rows.append(row)

        table_html = f"""
        <table>
            <thead>
                <tr>
                    <th>排名</th>
                    <th>行业名称</th>
                    <th>平均流入比例</th>
                    <th>最大单日流入</th>
                    <th>最大单日流出</th>
                    <th>热度评分</th>
                    <th>一致性</th>
                    <th>样本数</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
        """

        return table_html

    def _generate_stock_detail_table(self, sorted_industries: List[Tuple[str, Dict]]) -> str:
        """生成个股明细数据表HTML"""
        html_sections = []

        for industry, data in sorted_industries:
            individual_analysis = data.get('individual_analysis', {})
            if not individual_analysis:
                continue

            # 按综合评分排序个股
            sorted_stocks = sorted(
                individual_analysis.items(),
                key=lambda x: x[1].get('comprehensive_score', 0),
                reverse=True
            )

            rows = []
            for symbol, stock_data in sorted_stocks:
                main_inflow = stock_data.get('main_inflow_ratio', 0) * 100  # 转换为百分比
                detailed = stock_data.get('detailed_metrics', {})
                recent_5d = detailed.get('recent_5d_main_inflow', 0) * 100
                max_inflow = detailed.get('max_single_day_inflow', 0)
                max_outflow = detailed.get('max_single_day_outflow', 0)
                score = stock_data.get('comprehensive_score', 0)
                trend = stock_data.get('main_inflow_trend', 'unknown')

                inflow_class = 'positive' if main_inflow > 0 else 'negative' if main_inflow < 0 else 'neutral'
                recent_class = 'positive' if recent_5d > 0 else 'negative' if recent_5d < 0 else 'neutral'

                # 趋势图标
                trend_icon = '📈' if trend == 'improving' else '📉' if trend == 'deteriorating' else '➡️'

                # 获取股票显示名称
                display_name = self._get_stock_display_name(symbol)

                row = f"""
                <tr>
                    <td>{display_name}</td>
                    <td class="{inflow_class}">{main_inflow:+.2f}%</td>
                    <td class="{recent_class}">{recent_5d:+.2f}%</td>
                    <td class="positive">{max_inflow/10000:.2f}万</td>
                    <td class="negative">{max_outflow/10000:.2f}万</td>
                    <td>{trend_icon} {trend}</td>
                    <td>{score:.1f}</td>
                </tr>
                """
                rows.append(row)

            section_html = f"""
            <h3>{industry} 行业个股明细</h3>
            <table>
                <thead>
                    <tr>
                        <th>股票名称</th>
                        <th>30日主力流入比例</th>
                        <th>近5日流入比例</th>
                        <th>最大单日流入</th>
                        <th>最大单日流出</th>
                        <th>趋势</th>
                        <th>综合评分</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
            """
            html_sections.append(section_html)

        return '\n'.join(html_sections)

    def _generate_score_explanation(self) -> str:
        """生成综合评分说明HTML"""
        return """
        <div class="insights" style="background: #e8f4fd; border-left-color: #3498db;">
            <h4>📊 综合评分计算方法 (满分100分)</h4>
            <p style="margin-bottom: 15px;">综合评分由以下4个维度加权计算:</p>
            <table style="box-shadow: none; font-size: 14px;">
                <thead>
                    <tr>
                        <th>维度</th>
                        <th>权重</th>
                        <th>评分标准</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>主力资金流入</strong></td>
                        <td>40%</td>
                        <td>
                            流入比例 > 5%: 40分<br>
                            流入比例 2%-5%: 30分<br>
                            流入比例 0%-2%: 20分<br>
                            流入比例 -2%-0%: 10分<br>
                            流入比例 < -2%: 0分
                        </td>
                    </tr>
                    <tr>
                        <td><strong>大单趋势</strong></td>
                        <td>25%</td>
                        <td>
                            看涨趋势: +25分 × 趋势强度<br>
                            看跌趋势: -25分 × 趋势强度<br>
                            中性趋势: 0分
                        </td>
                    </tr>
                    <tr>
                        <td><strong>资金流向一致性</strong></td>
                        <td>20%</td>
                        <td>
                            20分 × 一致性评分(0-1)<br>
                            <small>小单、中单、大单、特大单流向的一致程度</small>
                        </td>
                    </tr>
                    <tr>
                        <td><strong>机构关注度</strong></td>
                        <td>15%</td>
                        <td>
                            高关注度: 15分<br>
                            中等关注度: 10分<br>
                            低关注度: 5分<br>
                            <small>基于大单和特大单活跃度</small>
                        </td>
                    </tr>
                </tbody>
            </table>
            <p style="margin-top: 15px; color: #555;">
                <strong>说明:</strong> 评分越高,表示资金流入状况越好,机构关注度越高。
                一般认为 > 60分为强势股,40-60分为中性,< 40分为弱势股。
            </p>
        </div>
        """

    def _generate_industry_table_markdown(self, sorted_industries: List[Tuple[str, Dict]]) -> str:
        """生成行业数据表Markdown"""
        headers = "| 排名 | 行业名称 | 平均流入比例 | 最大单日流入 | 最大单日流出 | 热度评分 | 一致性 | 样本数 |"
        separator = "|------|----------|--------------|--------------|--------------|----------|--------|--------|"

        rows = []
        for rank, (industry, data) in enumerate(sorted_industries, 1):
            avg_inflow = data.get('avg_inflow_ratio', 0)
            heat_score = data.get('sector_heat_score', 0)
            consistency = data.get('sector_consistency', 0)
            valid_stocks = data.get('valid_stocks', 0)

            # 计算绝对金额统计
            individual_analysis = data.get('individual_analysis', {})
            total_max_inflow = sum(
                stock_data.get('detailed_metrics', {}).get('max_single_day_inflow', 0)
                for stock_data in individual_analysis.values()
            )
            total_max_outflow = sum(
                stock_data.get('detailed_metrics', {}).get('max_single_day_outflow', 0)
                for stock_data in individual_analysis.values()
            )

            row = f"| {rank} | {industry} | {avg_inflow:+.2f}% | {total_max_inflow/10000:.2f}万 | {total_max_outflow/10000:.2f}万 | {heat_score:.0f} | {consistency:.2f} | {valid_stocks} |"
            rows.append(row)

        return '\n'.join([headers, separator] + rows)

    def _generate_insights(self, industry_data: Dict[str, Dict[str, Any]]) -> str:
        """生成投资洞察HTML"""
        insights = []

        # 找出最强流入行业
        top_inflow = max(industry_data.items(),
                        key=lambda x: x[1].get('avg_inflow_ratio', 0))
        if top_inflow[1].get('avg_inflow_ratio', 0) > 0:
            insights.append(f"<strong>{top_inflow[0]}</strong> 行业资金流入最强，平均流入比例达 <strong>{top_inflow[1]['avg_inflow_ratio']:+.2f}%</strong>")

        # 找出最热门行业
        top_heat = max(industry_data.items(),
                      key=lambda x: x[1].get('sector_heat_score', 0))
        if top_heat[1].get('sector_heat_score', 0) > 60:
            insights.append(f"<strong>{top_heat[0]}</strong> 行业热度最高，热度评分 <strong>{top_heat[1]['sector_heat_score']:.0f}</strong>")

        # 找出最一致的行业
        top_consistency = max(industry_data.items(),
                             key=lambda x: x[1].get('sector_consistency', 0))
        if top_consistency[1].get('sector_consistency', 0) > 0.7:
            insights.append(f"<strong>{top_consistency[0]}</strong> 行业资金流向最一致，一致性评分 <strong>{top_consistency[1]['sector_consistency']:.2f}</strong>")

        # 整体市场情绪
        avg_inflow = sum(data.get('avg_inflow_ratio', 0)
                        for data in industry_data.values()) / len(industry_data)

        if avg_inflow > 2:
            insights.append("整体市场情绪<strong>偏乐观</strong>，多数行业资金净流入")
        elif avg_inflow < -2:
            insights.append("整体市场情绪<strong>偏谨慎</strong>，多数行业资金净流出")
        else:
            insights.append("整体市场情绪<strong>中性</strong>，资金流向分化")

        if not insights:
            insights.append("暂无明显投资洞察")

        return "<h4>关键发现</h4><ul>" + "".join(f"<li>{insight}</li>" for insight in insights) + "</ul>"

    def _generate_insights_markdown(self, industry_data: Dict[str, Dict[str, Any]]) -> str:
        """生成投资洞察Markdown"""
        insights = []

        # 找出最强流入行业
        top_inflow = max(industry_data.items(),
                        key=lambda x: x[1].get('avg_inflow_ratio', 0))
        if top_inflow[1].get('avg_inflow_ratio', 0) > 0:
            insights.append(f"- **{top_inflow[0]}** 行业资金流入最强，平均流入比例达 **{top_inflow[1]['avg_inflow_ratio']:+.2f}%**")

        # 找出最热门行业
        top_heat = max(industry_data.items(),
                      key=lambda x: x[1].get('sector_heat_score', 0))
        if top_heat[1].get('sector_heat_score', 0) > 60:
            insights.append(f"- **{top_heat[0]}** 行业热度最高，热度评分 **{top_heat[1]['sector_heat_score']:.0f}**")

        # 找出最一致的行业
        top_consistency = max(industry_data.items(),
                             key=lambda x: x[1].get('sector_consistency', 0))
        if top_consistency[1].get('sector_consistency', 0) > 0.7:
            insights.append(f"- **{top_consistency[0]}** 行业资金流向最一致，一致性评分 **{top_consistency[1]['sector_consistency']:.2f}**")

        # 整体市场情绪
        avg_inflow = sum(data.get('avg_inflow_ratio', 0)
                        for data in industry_data.values()) / len(industry_data)

        if avg_inflow > 2:
            insights.append("- 整体市场情绪**偏乐观**，多数行业资金净流入")
        elif avg_inflow < -2:
            insights.append("- 整体市场情绪**偏谨慎**，多数行业资金净流出")
        else:
            insights.append("- 整体市场情绪**中性**，资金流向分化")

        if not insights:
            insights.append("- 暂无明显投资洞察")

        return "\n".join(insights)

    def save_data_json(self, data: Dict, filename: str) -> str:
        """保存原始数据为JSON"""
        json_path = self.output_dir / filename

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return str(json_path)


def test_reporter():
    """测试报告生成器"""
    logger.info("📝 测试资金流向报告生成器...")

    reporter = CapitalFlowReporter()

    # 测试数据
    test_industry_data = {
        "半导体": {
            "avg_inflow_ratio": 3.5,
            "sector_heat_score": 75,
            "sector_consistency": 0.8,
            "valid_stocks": 20
        },
        "新能源": {
            "avg_inflow_ratio": -1.2,
            "sector_heat_score": 45,
            "sector_consistency": 0.6,
            "valid_stocks": 15
        }
    }

    test_chart_paths = {
        "heatmap": "reports/capital_flow/heatmap.png",
        "ranking": "reports/capital_flow/ranking.png"
    }

    # 生成报告
    html_path = reporter.generate_industry_report(
        test_industry_data, test_chart_paths, days=30, format='html'
    )
    logger.info("✅ HTML报告已保存: {html_path}")

    md_path = reporter.generate_industry_report(
        test_industry_data, test_chart_paths, days=30, format='markdown'
    )
    logger.info("✅ Markdown报告已保存: {md_path}")

    logger.info("\n✅ 报告生成器测试完成")


if __name__ == '__main__':
    test_reporter()