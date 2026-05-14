import math

from backtesting import Strategy


class BaseStrategy(Strategy):
    """策略基类，继承 Backtesting.py 的 Strategy。

    子类需实现 init() 和 next()。
    """

    risk_per_trade = 0.01
    max_position_pct = 1.0
    cooldown_losses = 2
    cooldown_bars = 24
    max_holding_bars = 120
    trailing_atr_multiplier = 2.0
    max_drawdown_pct = 0.25

    def init_risk(self):
        """Initialize shared risk state. Call from child init()."""
        self._risk_last_closed_count = 0
        self._risk_consecutive_losses = 0
        self._risk_cooldown_until_bar = -1
        self._risk_peak_equity = self.equity
        self._risk_trading_disabled = False

    @property
    def current_bar(self) -> int:
        return len(self.data.Close) - 1

    def update_risk_state(self):
        """Track closed trades, cooldown state, and account drawdown."""
        if not hasattr(self, "_risk_last_closed_count"):
            self.init_risk()

        closed_count = len(self.closed_trades)
        if closed_count > self._risk_last_closed_count:
            for trade in self.closed_trades[self._risk_last_closed_count:closed_count]:
                if trade.pl < 0:
                    self._risk_consecutive_losses += 1
                else:
                    self._risk_consecutive_losses = 0

            if self._risk_consecutive_losses >= self.cooldown_losses:
                self._risk_cooldown_until_bar = self.current_bar + self.cooldown_bars
                self._risk_consecutive_losses = 0

            self._risk_last_closed_count = closed_count

        self._risk_peak_equity = max(self._risk_peak_equity, self.equity)
        if self.max_drawdown_pct > 0 and self._risk_peak_equity > 0:
            drawdown = 1 - self.equity / self._risk_peak_equity
            if drawdown >= self.max_drawdown_pct:
                self._risk_trading_disabled = True
                if self.position:
                    self.position.close()

    def can_enter(self) -> bool:
        if not hasattr(self, "_risk_trading_disabled"):
            self.init_risk()
        if self._risk_trading_disabled:
            return False
        if self.current_bar < self._risk_cooldown_until_bar:
            return False
        return not self.position

    def position_size_for_stop(self, entry_price: float, stop_loss: float) -> int:
        """Calculate whole-unit position size from risk and stop distance."""
        stop_distance = abs(entry_price - stop_loss)
        if entry_price <= 0 or stop_loss <= 0 or stop_distance <= 0:
            return 0

        risk_cash = self.equity * self.risk_per_trade
        risk_units = risk_cash / stop_distance
        max_units = self.equity * self.max_position_pct / entry_price
        units = math.floor(min(risk_units, max_units))
        return max(units, 0)

    def buy_with_risk(self, entry_price: float, stop_loss: float):
        size = self.position_size_for_stop(entry_price, stop_loss)
        if size <= 0:
            return None
        return self.buy(size=size, sl=stop_loss)

    def apply_time_stop(self):
        if not self.position or self.max_holding_bars <= 0:
            return
        for trade in self.trades:
            if self.current_bar - trade.entry_bar >= self.max_holding_bars and trade.pl <= 0:
                trade.close()

    def update_atr_trailing_stop(self, atr_value: float):
        if not self.position or self.trailing_atr_multiplier <= 0 or atr_value <= 0:
            return

        price = self.data.Close[-1]
        for trade in self.trades:
            if trade.is_long:
                new_sl = price - self.trailing_atr_multiplier * atr_value
                if trade.sl is None or new_sl > trade.sl:
                    trade.sl = new_sl
            else:
                new_sl = price + self.trailing_atr_multiplier * atr_value
                if trade.sl is None or new_sl < trade.sl:
                    trade.sl = new_sl

    def apply_risk_management(self, atr_value: float | None = None):
        self.update_risk_state()
        if atr_value is not None:
            self.update_atr_trailing_stop(atr_value)
        self.apply_time_stop()
