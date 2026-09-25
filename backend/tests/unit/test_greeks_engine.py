import unittest
import math
from backend.app.services.analytics.greeks_engine import GreeksEngine, greeks_engine
from backend.app.services.analytics.option_chain_builder import option_chain_builder

class TestGreeksEngine(unittest.TestCase):
    def setUp(self):
        self.engine = GreeksEngine(default_risk_free_rate=0.065)

    def test_bs_pricing_and_put_call_parity(self):
        spot = 23000.0
        strike = 23000.0
        tte = 30.0 / 365.0
        vol = 0.20  # 20%
        rate = 0.065

        call_price = self.engine.bs_price(spot, strike, tte, vol, rate, "CE")
        put_price = self.engine.bs_price(spot, strike, tte, vol, rate, "PE")

        self.assertGreater(call_price, 0)
        self.assertGreater(put_price, 0)

        # Put-Call Parity: C - P = S - K * exp(-r * T)
        parity_lhs = call_price - put_price
        parity_rhs = spot - strike * math.exp(-rate * tte)
        self.assertAlmostEqual(parity_lhs, parity_rhs, places=2)

    def test_delta_bounds_and_direction(self):
        spot = 23000.0
        tte = 15.0 / 365.0
        vol = 0.18
        rate = 0.065

        # ATM Call & Put
        atm_greeks_ce = self.engine.calculate_greeks(350.0, spot, 23000.0, "26MAR2026", "CE")
        atm_greeks_pe = self.engine.calculate_greeks(320.0, spot, 23000.0, "26MAR2026", "PE")

        self.assertGreaterEqual(atm_greeks_ce.delta, 0.0)
        self.assertLessEqual(atm_greeks_ce.delta, 1.0)
        self.assertAlmostEqual(atm_greeks_ce.delta, 0.5, delta=0.15)

        self.assertGreaterEqual(atm_greeks_pe.delta, -1.0)
        self.assertLessEqual(atm_greeks_pe.delta, 0.0)
        self.assertAlmostEqual(atm_greeks_pe.delta, -0.5, delta=0.15)

        # Deep ITM Call (strike = 21000)
        deep_itm_ce = self.engine.calculate_greeks(2050.0, spot, 21000.0, "26MAR2026", "CE")
        self.assertGreater(deep_itm_ce.delta, 0.85)

        # Deep OTM Call (strike = 25000)
        deep_otm_ce = self.engine.calculate_greeks(25.0, spot, 25000.0, "26MAR2026", "CE")
        self.assertLess(deep_otm_ce.delta, 0.20)

    def test_gamma_properties(self):
        spot = 8900.0
        tte = 20.0 / 365.0
        vol = 0.25
        rate = 0.065

        atm_ce = self.engine.calculate_greeks(250.0, spot, 8900.0, "19FEB2026", "CE", exchange="MCX")
        atm_pe = self.engine.calculate_greeks(240.0, spot, 8900.0, "19FEB2026", "PE", exchange="MCX")

        # Gamma must be positive
        self.assertGreater(atm_ce.gamma, 0.0)
        self.assertGreater(atm_pe.gamma, 0.0)

        # Call Gamma equals Put Gamma for same strike & spot
        self.assertAlmostEqual(atm_ce.gamma, atm_pe.gamma, places=4)

    def test_theta_and_vega(self):
        spot = 23000.0
        greeks = self.engine.calculate_greeks(400.0, spot, 23000.0, "26MAR2026", "CE")

        # Theta must be negative (time decay hurts long option)
        self.assertLess(greeks.theta, 0.0)

        # Vega must be positive (volatility expansion benefits long option)
        self.assertGreater(greeks.vega, 0.0)

    def test_iv_solver_recovery(self):
        spot = 23000.0
        strike = 23000.0
        tte = 25.0 / 365.0
        target_vol = 0.225  # 22.5%
        rate = 0.065

        # 1. Compute price from target_vol
        theo_price = self.engine.bs_price(spot, strike, tte, target_vol, rate, "CE")

        # 2. Invert using solve_iv
        solved_iv = self.engine.solve_iv(theo_price, spot, strike, tte, rate, "CE")

        # 3. Check recovery
        self.assertAlmostEqual(solved_iv, target_vol * 100.0, delta=0.2)

    def test_tte_calculation(self):
        tte_nfo_y, tte_nfo_d = self.engine.calculate_tte("26MAR2026", exchange="NFO")
        self.assertGreater(tte_nfo_y, 0.0)
        self.assertGreater(tte_nfo_d, 0.0)

        tte_mcx_y, tte_mcx_d = self.engine.calculate_tte("19FEB2026", exchange="MCX")
        self.assertGreater(tte_mcx_y, 0.0)
        self.assertGreater(tte_mcx_d, 0.0)

    def test_option_chain_greeks_attachment(self):
        matrix = option_chain_builder.build("CRUDEOIL", expiry="19FEB2026", strike_window=2, exchange="MCX")
        self.assertIsNotNone(matrix)
        self.assertGreater(len(matrix.rows), 0)

        for row in matrix.rows:
            # Check Call side Greeks
            if row.call:
                self.assertIsNotNone(row.call.iv)
                self.assertGreater(row.call.iv, 0.0)
                self.assertIsNotNone(row.call.delta)
                self.assertGreaterEqual(row.call.delta, 0.0)
                self.assertLessEqual(row.call.delta, 1.0)
                self.assertIsNotNone(row.call.gamma)
                self.assertGreater(row.call.gamma, 0.0)
                self.assertIsNotNone(row.call.theta)
                self.assertLessEqual(row.call.theta, 0.0)
                self.assertIsNotNone(row.call.vega)
                self.assertGreater(row.call.vega, 0.0)

            # Check Put side Greeks
            if row.put:
                self.assertIsNotNone(row.put.iv)
                self.assertGreater(row.put.iv, 0.0)
                self.assertIsNotNone(row.put.delta)
                self.assertGreaterEqual(row.put.delta, -1.0)
                self.assertLessEqual(row.put.delta, 0.0)
                self.assertIsNotNone(row.put.gamma)
                self.assertGreater(row.put.gamma, 0.0)
                self.assertIsNotNone(row.put.theta)
                self.assertLessEqual(row.put.theta, 0.0)
                self.assertIsNotNone(row.put.vega)
                self.assertGreater(row.put.vega, 0.0)

if __name__ == "__main__":
    unittest.main()
