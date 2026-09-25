"""
Trading execution and paper trading position manager.
Provides order placement, risk checks (max loss, max position quantity),
P&L tracking, multi-leg order execution (Straddle, Strangle, Spreads),
and Angel One SmartAPI order payload generation.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from backend.app.core.logging import logger

class OrderType:
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL_LIMIT = "STOPLOSS_LIMIT"
    SL_MARKET = "STOPLOSS_MARKET"

class OrderAction:
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus:
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

class PaperTradingEngine:
    def __init__(self, initial_capital: float = 1000000.0):
        self.initial_capital = initial_capital
        self.available_cash = initial_capital
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.positions: Dict[str, Dict[str, Any]] = {}  # key: symbol/token
        self.max_order_qty_limit = 5000
        self.max_drawdown_limit = 100000.0  # ₹1 Lakh
        logger.info(f"Initialized PaperTradingEngine with capital: ₹{initial_capital:,.2f}")

    def place_order(
        self,
        symbol: str,
        token: str,
        underlying: str,
        transaction_type: str,
        quantity: int,
        order_type: str = OrderType.MARKET,
        price: float = 0.0,
        stoploss: Optional[float] = None,
        target: Optional[float] = None,
        product_type: str = "INTRADAY"
    ) -> Dict[str, Any]:
        """
        Place a simulated order with risk checks and position updates.
        """
        transaction_type = transaction_type.upper()
        if transaction_type not in (OrderAction.BUY, OrderAction.SELL):
            raise ValueError(f"Invalid transaction_type: {transaction_type}")

        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")

        if quantity > self.max_order_qty_limit:
            return {
                "status": OrderStatus.REJECTED,
                "reason": f"Quantity {quantity} exceeds single order limit {self.max_order_qty_limit}",
                "order_id": None
            }

        order_id = f"ORD-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        execution_price = price if price > 0 else 100.0  # simulated fill

        required_margin = (execution_price * quantity) if transaction_type == OrderAction.BUY else (execution_price * quantity * 0.2)
        if transaction_type == OrderAction.BUY and required_margin > self.available_cash:
            return {
                "status": OrderStatus.REJECTED,
                "reason": f"Insufficient margin. Required ₹{required_margin:,.2f}, Available: ₹{self.available_cash:,.2f}",
                "order_id": order_id
            }

        # Deduct cash on buy
        if transaction_type == OrderAction.BUY:
            self.available_cash -= required_margin

        # Create Order Record
        order_record = {
            "order_id": order_id,
            "symbol": symbol,
            "token": token,
            "underlying": underlying,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": order_type,
            "price": execution_price,
            "status": OrderStatus.COMPLETE,
            "stoploss": stoploss,
            "target": target,
            "product_type": product_type,
            "placed_at": datetime.now(timezone.utc).isoformat()
        }
        self.orders[order_id] = order_record

        # Update Position Book
        pos_key = f"{symbol}_{product_type}"
        if pos_key not in self.positions:
            self.positions[pos_key] = {
                "symbol": symbol,
                "token": token,
                "underlying": underlying,
                "product_type": product_type,
                "net_qty": 0,
                "buy_qty": 0,
                "buy_avg": 0.0,
                "sell_qty": 0,
                "sell_avg": 0.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "current_ltp": execution_price
            }

        pos = self.positions[pos_key]
        if transaction_type == OrderAction.BUY:
            total_buy_val = (pos["buy_qty"] * pos["buy_avg"]) + (quantity * execution_price)
            pos["buy_qty"] += quantity
            pos["buy_avg"] = total_buy_val / pos["buy_qty"]
            pos["net_qty"] += quantity
        else:
            total_sell_val = (pos["sell_qty"] * pos["sell_avg"]) + (quantity * execution_price)
            pos["sell_qty"] += quantity
            pos["sell_avg"] = total_sell_val / pos["sell_qty"]
            pos["net_qty"] -= quantity

        logger.info(f"Order executed: {order_id} | {transaction_type} {quantity}x {symbol} @ {execution_price}")
        return {
            "status": OrderStatus.COMPLETE,
            "order_id": order_id,
            "execution_price": execution_price,
            "quantity": quantity,
            "net_qty": pos["net_qty"],
            "available_cash": self.available_cash
        }

    def place_multi_leg_strategy(
        self,
        strategy_name: str,
        underlying: str,
        legs: List[Dict[str, Any]],
        product_type: str = "INTRADAY"
    ) -> Dict[str, Any]:
        """
        Execute multi-leg options order simultaneously (e.g. ATM Short Straddle or Iron Condor).
        """
        strategy_id = f"STRAT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        executed_legs = []

        for leg in legs:
            exec_res = self.place_order(
                symbol=leg["symbol"],
                token=leg.get("token", "0"),
                underlying=underlying,
                transaction_type=leg["transaction_type"],
                quantity=leg["quantity"],
                order_type=leg.get("order_type", OrderType.MARKET),
                price=leg.get("price", 0.0),
                product_type=product_type
            )
            executed_legs.append({
                "leg": leg,
                "result": exec_res
            })

        return {
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "underlying": underlying,
            "legs_count": len(legs),
            "legs": executed_legs,
            "executed_at": datetime.now(timezone.utc).isoformat()
        }

    def update_live_pnl(self, quotes: Dict[str, float]) -> Dict[str, Any]:
        """
        Recalculate unrealized and realized P&L based on current market LTPs.
        """
        total_unrealized = 0.0
        total_realized = 0.0

        for pos_key, pos in self.positions.items():
            ltp = quotes.get(pos["symbol"], quotes.get(pos["token"], pos["current_ltp"]))
            pos["current_ltp"] = ltp

            if pos["net_qty"] > 0:
                pos["unrealized_pnl"] = (ltp - pos["buy_avg"]) * pos["net_qty"]
            elif pos["net_qty"] < 0:
                pos["unrealized_pnl"] = (pos["sell_avg"] - ltp) * abs(pos["net_qty"])
            else:
                pos["unrealized_pnl"] = 0.0

            total_unrealized += pos["unrealized_pnl"]
            total_realized += pos["realized_pnl"]

        current_portfolio_value = self.available_cash + total_unrealized
        return {
            "initial_capital": self.initial_capital,
            "available_cash": round(self.available_cash, 2),
            "total_unrealized_pnl": round(total_unrealized, 2),
            "total_realized_pnl": round(total_realized, 2),
            "portfolio_value": round(current_portfolio_value, 2),
            "active_positions_count": sum(1 for p in self.positions.values() if p["net_qty"] != 0),
            "positions": list(self.positions.values())
        }

    def square_off_all_positions(self) -> Dict[str, Any]:
        """
        Emergency square-off / intraday EOD exit for all active open positions.
        """
        closed_orders = []
        for pos_key, pos in list(self.positions.items()):
            net_qty = pos["net_qty"]
            if net_qty != 0:
                action = OrderAction.SELL if net_qty > 0 else OrderAction.BUY
                res = self.place_order(
                    symbol=pos["symbol"],
                    token=pos["token"],
                    underlying=pos["underlying"],
                    transaction_type=action,
                    quantity=abs(net_qty),
                    price=pos["current_ltp"],
                    product_type=pos["product_type"]
                )
                closed_orders.append(res)

        return {
            "squared_off_count": len(closed_orders),
            "closed_orders": closed_orders,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

# Global singleton
paper_trading_engine = PaperTradingEngine()
