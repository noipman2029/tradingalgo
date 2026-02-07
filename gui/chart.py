"""
Matplotlib chart embedded in Tkinter.
Displays candlesticks + Bollinger Bands on top, Williams %R on bottom.
Shows entry, SL, TP1/TP2/TP3 levels when in position.
"""

import tkinter as tk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from core.indicators import compute_all_indicators


# Dark theme colors matching the GUI
BG_COLOR = "#1e1e2e"
GRID_COLOR = "#45475a"
TEXT_COLOR = "#cdd6f4"
CANDLE_UP = "#a6e3a1"
CANDLE_DOWN = "#f38ba8"
BB_COLOR = "#89b4fa"
BB_FILL = "#89b4fa"
SMA_COLOR = "#f9e2af"
WR_COLOR = "#cba6f7"
WR_OVERSOLD = "#a6e3a1"
WR_OVERBOUGHT = "#f38ba8"
ENTRY_COLOR = "#ffffff"
SL_COLOR = "#f38ba8"
TP1_COLOR = "#a6e3a1"
TP2_COLOR = "#94e2d5"
TP3_COLOR = "#89dceb"


class ChartPanel:
    """Matplotlib chart panel for the Graphique tab."""

    def __init__(self, parent_frame, config):
        self.config = config
        self.parent = parent_frame

        # Trade levels to display
        self._trade_levels = None  # {direction, entry, sl, tp1, tp2, tp3}

        # Create figure with dark background
        self.fig, (self.ax_price, self.ax_wr) = plt.subplots(
            2, 1, figsize=(10, 6),
            gridspec_kw={"height_ratios": [3, 1]},
            facecolor=BG_COLOR,
        )
        self.fig.subplots_adjust(hspace=0.05, left=0.08, right=0.95,
                                  top=0.95, bottom=0.08)

        self._style_axes()

        # Embed in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Number of candles to show
        self.display_candles = 80

    def _style_axes(self):
        for ax in (self.ax_price, self.ax_wr):
            ax.set_facecolor(BG_COLOR)
            ax.tick_params(colors=TEXT_COLOR, labelsize=8)
            ax.spines["top"].set_color(GRID_COLOR)
            ax.spines["bottom"].set_color(GRID_COLOR)
            ax.spines["left"].set_color(GRID_COLOR)
            ax.spines["right"].set_color(GRID_COLOR)
            ax.yaxis.label.set_color(TEXT_COLOR)
            ax.grid(True, color=GRID_COLOR, alpha=0.3, linewidth=0.5)

        # Hide x-axis labels on price chart (shared with WR below)
        self.ax_price.tick_params(labelbottom=False)

    def set_trade_levels(self, levels: dict | None):
        """Set trade levels to display. None to clear."""
        self._trade_levels = levels

    def update_chart(self, df: pd.DataFrame):
        """Redraw the chart with new data."""
        if df is None or len(df) < 25:
            return

        cfg = self.config
        data = compute_all_indicators(
            df, cfg.WILLIAMS_PERIOD, cfg.BOLLINGER_PERIOD,
            cfg.BOLLINGER_STD_DEV, cfg.SMA_PERIOD,
        )

        # Take last N candles for display
        data = data.tail(self.display_candles).reset_index(drop=True)

        self.ax_price.clear()
        self.ax_wr.clear()
        self._style_axes()

        x = np.arange(len(data))

        # ── Candlesticks ─────────────────────────────────────────
        self._draw_candles(x, data)

        # ── Bollinger Bands ──────────────────────────────────────
        bb_upper = data["bb_upper"].values
        bb_middle = data["bb_middle"].values
        bb_lower = data["bb_lower"].values

        self.ax_price.plot(x, bb_upper, color=BB_COLOR, linewidth=0.8,
                           alpha=0.7, label="BB Upper")
        self.ax_price.plot(x, bb_middle, color=BB_COLOR, linewidth=0.5,
                           alpha=0.5, linestyle="--")
        self.ax_price.plot(x, bb_lower, color=BB_COLOR, linewidth=0.8,
                           alpha=0.7, label="BB Lower")
        self.ax_price.fill_between(x, bb_upper, bb_lower,
                                    color=BB_FILL, alpha=0.06)

        # ── SMA ──────────────────────────────────────────────────
        sma_vals = data["sma"].values
        self.ax_price.plot(x, sma_vals, color=SMA_COLOR, linewidth=0.8,
                           alpha=0.7, label="SMA")

        # ── Trade levels (entry, SL, TPs) ────────────────────────
        if self._trade_levels:
            self._draw_trade_levels(x)

        # ── Williams %R ──────────────────────────────────────────
        wr = data["williams_r"].values
        self.ax_wr.plot(x, wr, color=WR_COLOR, linewidth=1.2)
        self.ax_wr.axhline(y=cfg.WILLIAMS_OVERSOLD, color=WR_OVERSOLD,
                            linewidth=0.8, linestyle="--", alpha=0.7)
        self.ax_wr.axhline(y=cfg.WILLIAMS_OVERBOUGHT, color=WR_OVERBOUGHT,
                            linewidth=0.8, linestyle="--", alpha=0.7)
        self.ax_wr.fill_between(x, cfg.WILLIAMS_OVERSOLD, -100,
                                 alpha=0.08, color=WR_OVERSOLD)
        self.ax_wr.fill_between(x, cfg.WILLIAMS_OVERBOUGHT, 0,
                                 alpha=0.08, color=WR_OVERBOUGHT)
        self.ax_wr.set_ylim(-105, 5)
        self.ax_wr.set_ylabel("W%R", fontsize=9)

        # ── X-axis time labels ───────────────────────────────────
        if "time" in data.columns:
            n_labels = min(8, len(data))
            step = max(1, len(data) // n_labels)
            tick_positions = list(range(0, len(data), step))
            tick_labels = [
                data["time"].iloc[i].strftime("%H:%M")
                for i in tick_positions
            ]
            self.ax_wr.set_xticks(tick_positions)
            self.ax_wr.set_xticklabels(tick_labels, fontsize=7,
                                        color=TEXT_COLOR)

        # ── Legend ───────────────────────────────────────────────
        self.ax_price.legend(loc="upper left", fontsize=7,
                              facecolor=BG_COLOR, edgecolor=GRID_COLOR,
                              labelcolor=TEXT_COLOR)

        self.ax_price.set_xlim(-1, len(data))
        self.ax_wr.set_xlim(-1, len(data))

        self.canvas.draw_idle()

    def _draw_candles(self, x, data):
        """Draw candlestick bodies and wicks."""
        opens = data["open"].values
        highs = data["high"].values
        lows = data["low"].values
        closes = data["close"].values

        body_width = 0.6
        wick_width = 0.15

        for i in range(len(x)):
            color = CANDLE_UP if closes[i] >= opens[i] else CANDLE_DOWN

            # Wick (high-low line)
            self.ax_price.plot(
                [x[i], x[i]], [lows[i], highs[i]],
                color=color, linewidth=wick_width * 5, solid_capstyle="round"
            )

            # Body
            body_bottom = min(opens[i], closes[i])
            body_height = abs(closes[i] - opens[i])
            if body_height < (highs[i] - lows[i]) * 0.01:
                body_height = (highs[i] - lows[i]) * 0.01

            self.ax_price.bar(
                x[i], body_height, bottom=body_bottom,
                width=body_width, color=color, edgecolor=color,
                linewidth=0.5
            )

    def _draw_trade_levels(self, x):
        """Draw horizontal lines for entry, SL, and TPs."""
        levels = self._trade_levels
        xmin, xmax = x[0], x[-1]

        # Entry line
        self.ax_price.axhline(
            y=levels["entry"], color=ENTRY_COLOR,
            linewidth=1.0, linestyle="-", alpha=0.9
        )
        self.ax_price.text(
            xmax + 0.5, levels["entry"], f" E {levels['entry']:.5f}",
            color=ENTRY_COLOR, fontsize=7, va="center"
        )

        # SL line
        self.ax_price.axhline(
            y=levels["sl"], color=SL_COLOR,
            linewidth=1.0, linestyle="--", alpha=0.9
        )
        self.ax_price.text(
            xmax + 0.5, levels["sl"], f" SL {levels['sl']:.5f}",
            color=SL_COLOR, fontsize=7, va="center"
        )

        # TP lines
        for tp_key, tp_color, tp_label in [
            ("tp1", TP1_COLOR, "TP1"),
            ("tp2", TP2_COLOR, "TP2"),
            ("tp3", TP3_COLOR, "TP3"),
        ]:
            val = levels[tp_key]
            self.ax_price.axhline(
                y=val, color=tp_color,
                linewidth=1.0, linestyle=":", alpha=0.9
            )
            self.ax_price.text(
                xmax + 0.5, val, f" {tp_label} {val:.5f}",
                color=tp_color, fontsize=7, va="center"
            )

        # Shade the SL-TP3 zone
        direction = levels.get("direction", "BUY")
        if direction == "BUY":
            self.ax_price.axhspan(
                levels["sl"], levels["entry"],
                alpha=0.05, color=SL_COLOR
            )
            self.ax_price.axhspan(
                levels["entry"], levels["tp3"],
                alpha=0.05, color=TP1_COLOR
            )
        else:
            self.ax_price.axhspan(
                levels["entry"], levels["sl"],
                alpha=0.05, color=SL_COLOR
            )
            self.ax_price.axhspan(
                levels["tp3"], levels["entry"],
                alpha=0.05, color=TP1_COLOR
            )
