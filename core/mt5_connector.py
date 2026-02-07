"""
MT5 connection manager.
Handles initialization, data retrieval, and order execution.
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Mapping of string timeframe names to MT5 constants
TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M2": mt5.TIMEFRAME_M2,
    "M3": mt5.TIMEFRAME_M3,
    "M4": mt5.TIMEFRAME_M4,
    "M5": mt5.TIMEFRAME_M5,
    "M6": mt5.TIMEFRAME_M6,
    "M10": mt5.TIMEFRAME_M10,
    "M12": mt5.TIMEFRAME_M12,
    "M15": mt5.TIMEFRAME_M15,
    "M20": mt5.TIMEFRAME_M20,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H2": mt5.TIMEFRAME_H2,
    "H3": mt5.TIMEFRAME_H3,
    "H4": mt5.TIMEFRAME_H4,
    "H6": mt5.TIMEFRAME_H6,
    "H8": mt5.TIMEFRAME_H8,
    "H12": mt5.TIMEFRAME_H12,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}


class MT5Connector:
    """Manages the connection to MetaTrader 5."""

    def __init__(self, mt5_path=None):
        self.mt5_path = mt5_path
        self.connected = False

    def connect(self) -> bool:
        """Initialize connection to MT5 terminal."""
        if self.mt5_path:
            ok = mt5.initialize(self.mt5_path)
        else:
            ok = mt5.initialize()

        if not ok:
            error = mt5.last_error()
            logger.error("MT5 initialization failed: %s", error)
            self.connected = False
            return False

        info = mt5.terminal_info()
        if info is not None:
            logger.info(
                "Connected to MT5: %s (build %d)", info.name, info.build
            )
        self.connected = True
        return True

    def disconnect(self):
        """Shutdown MT5 connection."""
        mt5.shutdown()
        self.connected = False
        logger.info("Disconnected from MT5")

    def get_account_info(self) -> dict | None:
        """Return account information as a dictionary."""
        info = mt5.account_info()
        if info is None:
            return None
        return {
            "login": info.login,
            "server": info.server,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "leverage": info.leverage,
            "currency": info.currency,
        }

    def get_candles(
        self, symbol: str, timeframe_str: str, count: int = 200
    ) -> pd.DataFrame | None:
        """
        Fetch OHLCV candles for the given symbol and timeframe.
        Returns a DataFrame with columns: time, open, high, low, close, tick_volume
        """
        tf = TIMEFRAME_MAP.get(timeframe_str)
        if tf is None:
            logger.error("Unknown timeframe: %s", timeframe_str)
            return None

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.error(
                "Failed to get candles for %s %s: %s",
                symbol,
                timeframe_str,
                mt5.last_error(),
            )
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df[["time", "open", "high", "low", "close", "tick_volume"]]

    def get_symbol_info(self, symbol: str) -> dict | None:
        """Get symbol trading properties."""
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error("Symbol %s not found", symbol)
            return None
        if not info.visible:
            mt5.symbol_select(symbol, True)
        return {
            "point": info.point,
            "digits": info.digits,
            "spread": info.spread,
            "trade_contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
        }

    def get_tick(self, symbol: str) -> dict | None:
        """Get current bid/ask for a symbol."""
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {"bid": tick.bid, "ask": tick.ask, "time": tick.time}

    def send_order(
        self,
        symbol: str,
        order_type: str,
        lot: float,
        sl: float = 0.0,
        tp: float = 0.0,
        magic: int = 0,
        slippage: int = 10,
        comment: str = "",
    ) -> dict | None:
        """
        Send a market order.
        order_type: "BUY" or "SELL"
        Returns order result dict or None on failure.
        """
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error("Cannot get tick for %s", symbol)
            return None

        if order_type == "BUY":
            trade_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        elif order_type == "SELL":
            trade_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            logger.error("Invalid order type: %s", order_type)
            return None

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot),
            "type": trade_type,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": slippage,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error("Order send returned None: %s", mt5.last_error())
            return None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                "Order failed: retcode=%d, comment=%s",
                result.retcode,
                result.comment,
            )
            return {
                "success": False,
                "retcode": result.retcode,
                "comment": result.comment,
            }

        logger.info(
            "Order placed: %s %s %.2f lots @ %.5f (ticket=%d)",
            order_type,
            symbol,
            lot,
            price,
            result.order,
        )
        return {
            "success": True,
            "ticket": result.order,
            "price": price,
            "volume": lot,
        }

    def close_position(self, ticket: int, symbol: str, lot: float,
                       order_type: str, magic: int = 0,
                       slippage: int = 10) -> dict | None:
        """Close a position by ticket."""
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        if order_type == "BUY":
            # To close a buy, we sell
            trade_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            trade_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot),
            "type": trade_type,
            "position": ticket,
            "price": price,
            "deviation": slippage,
            "magic": magic,
            "comment": "ScalpBot close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {"success": False, "retcode": result.retcode,
                    "comment": result.comment}
        return {"success": True, "ticket": ticket}

    def modify_position_sl(self, ticket: int, symbol: str,
                           new_sl: float, tp: float) -> bool:
        """Modify the stop loss of an open position (for trailing stop)."""
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": ticket,
            "sl": float(new_sl),
            "tp": float(tp),
        }
        result = mt5.order_send(request)
        if result is None:
            return False
        return result.retcode == mt5.TRADE_RETCODE_DONE

    def get_positions(self, symbol: str = None,
                      magic: int = None) -> list[dict]:
        """Get open positions, optionally filtered by symbol and magic."""
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []

        result = []
        for p in positions:
            if magic is not None and p.magic != magic:
                continue
            result.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": p.volume,
                "open_price": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "magic": p.magic,
                "comment": p.comment,
                "time": datetime.fromtimestamp(p.time),
            })
        return result
