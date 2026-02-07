"""
Tkinter GUI for the MT5 Scalping Bot.
Two tabs: Dashboard (controls, indicators, log, positions)
and Graphique (live candlestick chart with BB, WR, trade levels).
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from gui.chart import ChartPanel


class ScalpBotGUI:
    """Main GUI application window."""

    def __init__(self, config, bot_engine):
        self.config = config
        self.engine = bot_engine

        self.root = tk.Tk()
        self.root.title("MT5 Scalping Bot - WR Reintegration + BB + SMA")
        self.root.geometry("1200x850")
        self.root.resizable(True, True)
        self.root.configure(bg="#1e1e2e")

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self._configure_styles()

        # Wire bot callbacks (thread-safe via root.after)
        self.engine.on_log = lambda msg: self.root.after(0, self._append_log, msg)
        self.engine.on_signal = lambda s: self.root.after(0, self._update_signal, s)
        self.engine.on_status = lambda s: self.root.after(0, self._update_status, s)
        self.engine.on_positions = lambda p: self.root.after(0, self._update_positions, p)
        self.engine.on_indicators = lambda d: self.root.after(0, self._update_indicators, d)
        self.engine.on_state = lambda s: self.root.after(0, self._update_state, s)
        self.engine.on_chart_data = lambda d: self.root.after(0, self._update_chart, d)

        self._build_ui()

    def _configure_styles(self):
        s = self.style
        bg = "#1e1e2e"
        fg = "#cdd6f4"
        accent = "#89b4fa"
        green = "#a6e3a1"
        red = "#f38ba8"
        yellow = "#f9e2af"

        s.configure("TFrame", background=bg)
        s.configure("TLabel", background=bg, foreground=fg, font=("Consolas", 10))
        s.configure("Header.TLabel", background=bg, foreground=accent,
                     font=("Consolas", 12, "bold"))
        s.configure("Buy.TLabel", background=bg, foreground=green,
                     font=("Consolas", 11, "bold"))
        s.configure("Sell.TLabel", background=bg, foreground=red,
                     font=("Consolas", 11, "bold"))
        s.configure("Watch.TLabel", background=bg, foreground=yellow,
                     font=("Consolas", 11, "bold"))
        s.configure("Status.TLabel", background="#313244", foreground=fg,
                     font=("Consolas", 10), padding=5)
        s.configure("TButton", font=("Consolas", 10, "bold"), padding=6)
        s.configure("Start.TButton", foreground="#1e1e2e", background=green)
        s.configure("Stop.TButton", foreground="#1e1e2e", background=red)
        s.configure("TLabelframe", background=bg, foreground=accent,
                     font=("Consolas", 10, "bold"))
        s.configure("TLabelframe.Label", background=bg, foreground=accent)
        s.configure("TEntry", fieldbackground="#313244", foreground=fg)
        s.configure("Treeview", background="#313244", foreground=fg,
                     fieldbackground="#313244", font=("Consolas", 9))
        s.configure("Treeview.Heading", background="#45475a", foreground=fg,
                     font=("Consolas", 9, "bold"))
        s.configure("TNotebook", background=bg)
        s.configure("TNotebook.Tab", background="#313244", foreground=fg,
                     font=("Consolas", 10, "bold"), padding=[10, 4])
        s.map("TNotebook.Tab",
              background=[("selected", accent)],
              foreground=[("selected", "#1e1e2e")])

    def _build_ui(self):
        # Top bar: controls + status
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, padx=10, pady=5)
        self._build_control_bar(top)

        # State bar
        state_frame = ttk.Frame(self.root)
        state_frame.pack(fill=tk.X, padx=10, pady=2)
        self._build_state_bar(state_frame)

        # Notebook (tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Tab 1: Dashboard
        tab_dashboard = ttk.Frame(self.notebook)
        self.notebook.add(tab_dashboard, text="  Dashboard  ")
        self._build_dashboard_tab(tab_dashboard)

        # Tab 2: Chart
        tab_chart = ttk.Frame(self.notebook)
        self.notebook.add(tab_chart, text="  Graphique  ")
        self.chart_panel = ChartPanel(tab_chart, self.config)

        # Bottom: signal bar
        bottom = ttk.Frame(self.root)
        bottom.pack(fill=tk.X, padx=10, pady=5)
        self._build_signal_bar(bottom)

    # ── Dashboard tab ────────────────────────────────────────────

    def _build_dashboard_tab(self, parent):
        main = ttk.Frame(parent)
        main.pack(fill=tk.BOTH, expand=True)

        # Left column: parameters + indicators
        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        self._build_params_panel(left)
        self._build_indicators_panel(left)

        # Right column: log + positions
        right = ttk.Frame(main)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_log_panel(right)
        self._build_positions_panel(right)

    # ── Control bar ──────────────────────────────────────────────

    def _build_control_bar(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X)

        ttk.Label(frame, text="MT5 SCALPING BOT",
                   style="Header.TLabel").pack(side=tk.LEFT, padx=5)

        self.btn_start = ttk.Button(
            frame, text="DEMARRER", style="Start.TButton",
            command=self._on_start
        )
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(
            frame, text="ARRETER", style="Stop.TButton",
            command=self._on_stop, state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.lbl_connection = ttk.Label(frame, text="Deconnecte",
                                         style="Status.TLabel")
        self.lbl_connection.pack(side=tk.RIGHT, padx=5)

        self.lbl_balance = ttk.Label(frame, text="Balance: ---",
                                      style="Status.TLabel")
        self.lbl_balance.pack(side=tk.RIGHT, padx=5)

        self.lbl_equity = ttk.Label(frame, text="Equity: ---",
                                     style="Status.TLabel")
        self.lbl_equity.pack(side=tk.RIGHT, padx=5)

        self.lbl_stats = ttk.Label(frame, text="W:0 L:0",
                                    style="Status.TLabel")
        self.lbl_stats.pack(side=tk.RIGHT, padx=5)

    # ── State bar ────────────────────────────────────────────────

    def _build_state_bar(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X)

        ttk.Label(frame, text="Etat:").pack(side=tk.LEFT, padx=5)
        self.lbl_state = ttk.Label(frame, text="IDLE", style="Status.TLabel")
        self.lbl_state.pack(side=tk.LEFT, padx=5)

    # ── Parameters panel ─────────────────────────────────────────

    def _build_params_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Parametres")
        frame.pack(fill=tk.X, pady=5)

        self.param_vars = {}
        params = [
            ("Symbole", "SYMBOL", self.config.SYMBOL),
            ("Lot total", "LOT_SIZE", str(self.config.LOT_SIZE)),
            ("Williams Per.", "WILLIAMS_PERIOD", str(self.config.WILLIAMS_PERIOD)),
            ("WR Survente", "WILLIAMS_OVERSOLD", str(self.config.WILLIAMS_OVERSOLD)),
            ("WR Surachat", "WILLIAMS_OVERBOUGHT", str(self.config.WILLIAMS_OVERBOUGHT)),
            ("WR Zone M15", "WILLIAMS_CONFIRM_ZONE", str(self.config.WILLIAMS_CONFIRM_ZONE)),
            ("BB Periode", "BOLLINGER_PERIOD", str(self.config.BOLLINGER_PERIOD)),
            ("BB Ecart-type", "BOLLINGER_STD_DEV", str(self.config.BOLLINGER_STD_DEV)),
            ("SMA Periode", "SMA_PERIOD", str(self.config.SMA_PERIOD)),
            ("SL Swing Bars", "SL_SWING_LOOKBACK", str(self.config.SL_SWING_LOOKBACK)),
            ("SL Marge (pts)", "SL_MARGIN_POINTS", str(self.config.SL_MARGIN_POINTS)),
            ("Max Spread", "MAX_SPREAD_POINTS", str(self.config.MAX_SPREAD_POINTS)),
            ("Cooldown (sec)", "COOLDOWN_SECONDS", str(self.config.COOLDOWN_SECONDS)),
            ("Intervalle (sec)", "CHECK_INTERVAL_SECONDS", str(self.config.CHECK_INTERVAL_SECONDS)),
        ]

        for i, (label, key, default) in enumerate(params):
            ttk.Label(frame, text=label).grid(
                row=i, column=0, sticky=tk.W, padx=5, pady=1
            )
            var = tk.StringVar(value=default)
            entry = ttk.Entry(frame, textvariable=var, width=12)
            entry.grid(row=i, column=1, padx=5, pady=1)
            self.param_vars[key] = var

        row = len(params)
        self.be_var = tk.BooleanVar(value=self.config.BREAKEVEN_AFTER_TP1)
        cb = ttk.Checkbutton(frame, text="Breakeven apres TP1",
                              variable=self.be_var)
        cb.grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        self.ignore_spread_var = tk.BooleanVar(value=self.config.IGNORE_SPREAD)
        cb_spread = ttk.Checkbutton(frame, text="Ignorer le spread",
                                     variable=self.ignore_spread_var)
        cb_spread.grid(row=row + 1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        self.ignore_m15_var = tk.BooleanVar(value=self.config.IGNORE_M15)
        cb_m15 = ttk.Checkbutton(frame, text="Ignorer M15 (M3 seul)",
                                  variable=self.ignore_m15_var)
        cb_m15.grid(row=row + 2, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        btn = ttk.Button(frame, text="Appliquer", command=self._apply_params)
        btn.grid(row=row + 3, column=0, columnspan=2, pady=5)

    # ── Indicators panel ─────────────────────────────────────────

    def _build_indicators_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Indicateurs")
        frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.ind_labels = {}
        timeframes = [
            ("Entry", self.config.TIMEFRAME_ENTRY),
            ("Confirm", self.config.TIMEFRAME_CONFIRM),
        ]

        for w in frame.winfo_children():
            w.destroy()

        self.ind_labels = {}
        for col_idx, (key, tf) in enumerate(timeframes):
            c = col_idx * 2
            ttk.Label(frame, text=tf, style="Header.TLabel").grid(
                row=0, column=c, columnspan=2, padx=8, pady=3
            )
            val_labels = {}
            rows = [
                ("wr", "W%R"),
                ("close", "Close"),
                ("bb_up", "BB Up"),
                ("bb_mid", "BB Mid"),
                ("bb_low", "BB Low"),
                ("sma", "SMA"),
                ("sma_dir", "SMA Dir"),
            ]
            for row, (name, display) in enumerate(rows, start=1):
                ttk.Label(frame, text=display).grid(
                    row=row, column=c, sticky=tk.W, padx=4, pady=1
                )
                lbl = ttk.Label(frame, text="---")
                lbl.grid(row=row, column=c + 1, sticky=tk.E, padx=4, pady=1)
                val_labels[name] = lbl

            self.ind_labels[key] = val_labels

    # ── Log panel ────────────────────────────────────────────────

    def _build_log_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Journal")
        frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.log_text = scrolledtext.ScrolledText(
            frame, height=18, bg="#313244", fg="#cdd6f4",
            font=("Consolas", 9), insertbackground="#cdd6f4",
            state=tk.DISABLED, wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

    # ── Positions panel ──────────────────────────────────────────

    def _build_positions_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="Positions Ouvertes")
        frame.pack(fill=tk.X, pady=5)

        columns = ("ticket", "type", "volume", "prix", "sl", "tp", "profit")
        self.pos_tree = ttk.Treeview(
            frame, columns=columns, show="headings", height=5
        )

        headers = {
            "ticket": ("Ticket", 70),
            "type": ("Type", 50),
            "volume": ("Volume", 60),
            "prix": ("Prix", 85),
            "sl": ("SL", 85),
            "tp": ("TP", 85),
            "profit": ("Profit", 70),
        }
        for col, (heading, width) in headers.items():
            self.pos_tree.heading(col, text=heading)
            self.pos_tree.column(col, width=width, anchor=tk.CENTER)

        self.pos_tree.pack(fill=tk.X, padx=3, pady=3)

    # ── Signal bar ───────────────────────────────────────────────

    def _build_signal_bar(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X)

        ttk.Label(frame, text="Signal:").pack(side=tk.LEFT, padx=5)
        self.lbl_signal = ttk.Label(frame, text="Aucun", style="Status.TLabel")
        self.lbl_signal.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    # ── Callbacks & Actions ──────────────────────────────────────

    def _on_start(self):
        self._apply_params()
        success = self.engine.start()
        if success:
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
            self.lbl_connection.config(text="Connecte")
        else:
            messagebox.showerror(
                "Erreur", "Impossible de demarrer le bot.\n"
                "Verifiez que MT5 est ouvert et connecte."
            )

    def _on_stop(self):
        self.engine.stop()
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_connection.config(text="Deconnecte")

    def _apply_params(self):
        """Read GUI fields and update config."""
        cfg = self.config
        try:
            cfg.SYMBOL = self.param_vars["SYMBOL"].get().strip()
            cfg.LOT_SIZE = float(self.param_vars["LOT_SIZE"].get())
            cfg.WILLIAMS_PERIOD = int(self.param_vars["WILLIAMS_PERIOD"].get())
            cfg.WILLIAMS_OVERSOLD = float(self.param_vars["WILLIAMS_OVERSOLD"].get())
            cfg.WILLIAMS_OVERBOUGHT = float(self.param_vars["WILLIAMS_OVERBOUGHT"].get())
            cfg.WILLIAMS_CONFIRM_ZONE = float(self.param_vars["WILLIAMS_CONFIRM_ZONE"].get())
            cfg.BOLLINGER_PERIOD = int(self.param_vars["BOLLINGER_PERIOD"].get())
            cfg.BOLLINGER_STD_DEV = float(self.param_vars["BOLLINGER_STD_DEV"].get())
            cfg.SMA_PERIOD = int(self.param_vars["SMA_PERIOD"].get())
            cfg.SL_SWING_LOOKBACK = int(self.param_vars["SL_SWING_LOOKBACK"].get())
            cfg.SL_MARGIN_POINTS = int(self.param_vars["SL_MARGIN_POINTS"].get())
            cfg.MAX_SPREAD_POINTS = int(self.param_vars["MAX_SPREAD_POINTS"].get())
            cfg.COOLDOWN_SECONDS = int(self.param_vars["COOLDOWN_SECONDS"].get())
            cfg.CHECK_INTERVAL_SECONDS = int(self.param_vars["CHECK_INTERVAL_SECONDS"].get())
            cfg.BREAKEVEN_AFTER_TP1 = self.be_var.get()
            cfg.IGNORE_SPREAD = self.ignore_spread_var.get()
            cfg.IGNORE_M15 = self.ignore_m15_var.get()
            self._append_log("Parametres mis a jour")
        except ValueError as e:
            messagebox.showwarning("Parametre invalide", str(e))

    def _append_log(self, msg: str):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _update_signal(self, signal):
        if signal.direction == "NONE":
            self.lbl_signal.config(
                text=signal.reason or "Pas de signal",
                style="Status.TLabel"
            )
            # Clear trade levels on chart if no active position
            if not self.engine.active_trade:
                self.chart_panel.set_trade_levels(None)
        elif signal.direction == "BUY":
            self.lbl_signal.config(
                text=(
                    f"BUY @ {signal.entry_price:.5f} | "
                    f"SL={signal.sl:.5f} | "
                    f"TP1={signal.tp1:.5f} TP2={signal.tp2:.5f} TP3={signal.tp3:.5f}"
                ),
                style="Buy.TLabel"
            )
            self.chart_panel.set_trade_levels({
                "direction": "BUY",
                "entry": signal.entry_price,
                "sl": signal.sl,
                "tp1": signal.tp1, "tp2": signal.tp2, "tp3": signal.tp3,
            })
        else:
            self.lbl_signal.config(
                text=(
                    f"SELL @ {signal.entry_price:.5f} | "
                    f"SL={signal.sl:.5f} | "
                    f"TP1={signal.tp1:.5f} TP2={signal.tp2:.5f} TP3={signal.tp3:.5f}"
                ),
                style="Sell.TLabel"
            )
            self.chart_panel.set_trade_levels({
                "direction": "SELL",
                "entry": signal.entry_price,
                "sl": signal.sl,
                "tp1": signal.tp1, "tp2": signal.tp2, "tp3": signal.tp3,
            })

    def _update_state(self, state_str: str):
        state_styles = {
            "IDLE": "Status.TLabel",
            "WATCHING_BUY": "Watch.TLabel",
            "WATCHING_SELL": "Watch.TLabel",
            "IN_POSITION": "Buy.TLabel",
        }
        state_labels = {
            "IDLE": "IDLE - En attente de setup",
            "WATCHING_BUY": "WATCHING BUY - Attente reintegration WR",
            "WATCHING_SELL": "WATCHING SELL - Attente reintegration WR",
            "IN_POSITION": "EN POSITION",
        }
        self.lbl_state.config(
            text=state_labels.get(state_str, state_str),
            style=state_styles.get(state_str, "Status.TLabel"),
        )

    def _update_status(self, info: dict):
        self.lbl_balance.config(
            text=f"Balance: {info['balance']:.2f} {info.get('currency', '')}"
        )
        self.lbl_equity.config(
            text=f"Equity: {info['equity']:.2f}"
        )
        self.lbl_stats.config(
            text=f"Trades:{info.get('total_trades', 0)} "
                 f"W:{info.get('winning', 0)} L:{info.get('losing', 0)}"
        )

    def _update_positions(self, positions: list):
        for item in self.pos_tree.get_children():
            self.pos_tree.delete(item)

        for p in positions:
            self.pos_tree.insert("", tk.END, values=(
                p["ticket"],
                p["type"],
                f"{p['volume']:.2f}",
                f"{p['open_price']:.5f}",
                f"{p['sl']:.5f}",
                f"{p['tp']:.5f}",
                f"{p['profit']:.2f}",
            ))

    def _update_indicators(self, data: dict):
        for key, values in data.items():
            labels = self.ind_labels.get(key)
            if not labels:
                continue
            labels["wr"].config(text=f"{values['williams_r']:.1f}")
            labels["close"].config(text=f"{values['close']:.5f}")
            labels["bb_up"].config(text=f"{values['bb_upper']:.5f}")
            labels["bb_mid"].config(text=f"{values['bb_middle']:.5f}")
            labels["bb_low"].config(text=f"{values['bb_lower']:.5f}")
            labels["sma"].config(text=f"{values['sma_value']:.5f}")

            if values["sma_rising"]:
                labels["sma_dir"].config(text="HAUSSE", style="Buy.TLabel")
            else:
                labels["sma_dir"].config(text="BAISSE", style="Sell.TLabel")

    def _update_chart(self, df):
        """Update the chart with new candle data."""
        self.chart_panel.update_chart(df)

    def run(self):
        """Start the Tkinter main loop."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self.engine.is_running:
            self.engine.stop()
        self.root.destroy()
