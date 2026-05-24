"""
drawdown_chart.py
回撤曲線圖元件
"""
from typing import List

import plotly.graph_objects as go


def build_drawdown_chart(
    drawdown_series: List[dict],
    title: str = "回撤曲線（Drawdown）",
) -> go.Figure:
    """
    建立回撤曲線（面積圖），紅色填充低於 0 的區域。

    參數：
        drawdown_series : [{"date": "...", "drawdown": -0.02}, ...]
                          所有值 <= 0
    """
    fig = go.Figure()

    if drawdown_series:
        dates = [e["date"] for e in drawdown_series]
        dd_pct = [round(e["drawdown"] * 100, 4) for e in drawdown_series]

        fig.add_trace(go.Scatter(
            x=dates,
            y=dd_pct,
            name="回撤 %",
            mode="lines",
            fill="tozeroy",
            line=dict(color="#dc2626", width=1.5),
            fillcolor="rgba(220, 38, 38, 0.15)",
        ))

    fig.update_layout(
        title=title,
        xaxis_title="日期",
        yaxis_title="回撤 %",
        height=220,
        margin=dict(l=0, r=10, t=40, b=0),
        hovermode="x unified",
        yaxis=dict(ticksuffix="%"),
    )
    return fig
