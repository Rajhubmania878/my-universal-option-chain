import os
import json
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

from backend.app.core.config import settings
from backend.app.core.logging import logger

@dataclass
class Instrument:
    token: str
    symbol: str
    name: str
    expiry: Optional[str]
    strike: float
    lotsize: int
    instrumenttype: str
    exch_seg: str
    tick_size: float
    option_type: Optional[str] = None  # "CE", "PE", or None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InstrumentMasterService:
    """
    Downloads, parses, and indexes Angel One OpenAPIScripMaster instruments.
    Dynamically discovers expiries, strikes, CE/PE tokens, lot sizes, and tick sizes.
    Supports NIFTY, BANKNIFTY, FINNIFTY, NSE Equity F&O, and MCX (CRUDEOIL, GOLD, SILVER).
    """

    SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data")
    CACHE_FILE = os.path.join(CACHE_DIR, "instruments_cache.json")

    def __init__(self):
        self._token_map: Dict[str, Instrument] = {}
        self._symbol_map: Dict[Tuple[str, str], Instrument] = {}  # (exchange, symbol) -> Instrument
        self._chain_map: Dict[Tuple[str, str, str, float, str], Instrument] = {}  # (name, exch, expiry, strike, CE/PE) -> Instrument
        self._expiries_map: Dict[Tuple[str, str], List[str]] = {}  # (name, exch) -> sorted expiries
        self._strikes_map: Dict[Tuple[str, str, str], List[float]] = {}  # (name, exch, expiry) -> sorted strikes
        self._underlyings: Dict[str, Dict[str, Any]] = {}
        self._last_loaded_time: Optional[datetime] = None
        self._is_loading = False

        # Pre-seed seed catalogue for offline/testing and instant fallback
        self._seed_default_instruments()

    @property
    def is_loaded(self) -> bool:
        return len(self._token_map) > 0

    @property
    def total_instruments(self) -> int:
        return len(self._token_map)

    @property
    def last_loaded_time(self) -> Optional[str]:
        return self._last_loaded_time.isoformat() if self._last_loaded_time else None

    def _normalize_strike(self, raw_strike: Any, exch_seg: str, symbol: str) -> float:
        """
        In Angel One OpenAPIScripMaster:
        NFO/BFO options strikes are usually multiplied by 100.0 (e.g. 2300000.0 for 23000.0 strike).
        MCX strikes are sometimes plain or / 100.0 depending on instrument.
        """
        try:
            val = float(raw_strike)
        except (ValueError, TypeError):
            return 0.0

        if val <= 0.0:
            return 0.0

        if exch_seg in ("NFO", "BFO", "CDS"):
            if val >= 1000.0 and val % 50 == 0:
                # E.g. strike 2300000.0 is 23000.0
                return val / 100.0
            return val
        elif exch_seg == "MCX":
            if val >= 100000.0:
                return val / 100.0
            return val
        return val

    def _determine_option_type(self, symbol: str, instrumenttype: str) -> Optional[str]:
        sym = symbol.strip().upper()
        if sym.endswith("CE") or instrumenttype in ("OPTIDX", "OPTSTK", "OPTFUT", "OPTCOM") and sym.endswith("CE"):
            return "CE"
        elif sym.endswith("PE") or instrumenttype in ("OPTIDX", "OPTSTK", "OPTFUT", "OPTCOM") and sym.endswith("PE"):
            return "PE"
        return None

    def _parse_and_index_records(self, raw_records: List[Dict[str, Any]]) -> int:
        """Parse raw Angel One JSON records and populate microsecond lookup indexes."""
        token_map: Dict[str, Instrument] = {}
        symbol_map: Dict[Tuple[str, str], Instrument] = {}
        chain_map: Dict[Tuple[str, str, str, float, str], Instrument] = {}
        expiries_set: Dict[Tuple[str, str], set] = {}
        strikes_set: Dict[Tuple[str, str, str], set] = {}
        underlyings: Dict[str, Dict[str, Any]] = {}

        for row in raw_records:
            token = str(row.get("token", "")).strip()
            if not token:
                continue

            symbol = str(row.get("symbol", "")).strip()
            name = str(row.get("name", "")).strip().upper()
            expiry = row.get("expiry")
            if expiry:
                expiry = str(expiry).strip().upper()

            exch_seg = str(row.get("exch_seg", "")).strip().upper()
            instrumenttype = str(row.get("instrumenttype", "")).strip().upper()

            try:
                lotsize = int(row.get("lotsize", 1))
            except (ValueError, TypeError):
                lotsize = 1

            try:
                tick_size = float(row.get("tick_size", 0.05))
            except (ValueError, TypeError):
                tick_size = 0.05

            raw_strike = row.get("strike", 0.0)
            strike = self._normalize_strike(raw_strike, exch_seg, symbol)
            option_type = self._determine_option_type(symbol, instrumenttype)

            inst = Instrument(
                token=token,
                symbol=symbol,
                name=name,
                expiry=expiry,
                strike=strike,
                lotsize=lotsize,
                instrumenttype=instrumenttype,
                exch_seg=exch_seg,
                tick_size=tick_size,
                option_type=option_type,
            )

            token_map[token] = inst
            symbol_map[(exch_seg, symbol)] = inst

            # Category detection
            category = "EQUITY"
            if name in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"):
                category = "INDEX"
            elif exch_seg == "MCX":
                category = "COMMODITY"
            elif exch_seg == "CDS":
                category = "CURRENCY"

            if name not in underlyings:
                underlyings[name] = {
                    "symbol": name,
                    "name": name,
                    "exchange": exch_seg,
                    "category": category,
                    "lot_size": lotsize,
                    "tick_size": tick_size,
                }

            # If derivative with expiry & strike
            if expiry:
                k_exp = (name, exch_seg)
                if k_exp not in expiries_set:
                    expiries_set[k_exp] = set()
                expiries_set[k_exp].add(expiry)

                if option_type and strike > 0:
                    k_str = (name, exch_seg, expiry)
                    if k_str not in strikes_set:
                        strikes_set[k_str] = set()
                    strikes_set[k_str].add(strike)

                    # Chain lookup key: (name, exch_seg, expiry, strike, option_type)
                    chain_map[(name, exch_seg, expiry, strike, option_type)] = inst

        # Sort expiries chronologically
        expiries_map: Dict[Tuple[str, str], List[str]] = {}
        for k, exps in expiries_set.items():
            expiries_map[k] = sorted(list(exps), key=self._expiry_sort_key)

        # Sort strikes numerically
        strikes_map: Dict[Tuple[str, str, str], List[float]] = {}
        for k, strs in strikes_set.items():
            strikes_map[k] = sorted(list(strs))

        # Commit atomical in-memory swap
        self._token_map = token_map
        self._symbol_map = symbol_map
        self._chain_map = chain_map
        self._expiries_map = expiries_map
        self._strikes_map = strikes_map
        self._underlyings = underlyings
        self._last_loaded_time = datetime.utcnow()

        logger.info(f"Loaded and indexed {len(token_map)} instruments across {len(underlyings)} underlyings.")
        return len(token_map)

    def _expiry_sort_key(self, expiry_str: str) -> float:
        """Parse expiry strings like '26MAR2026', '19FEB2024', '2026-03-26' into timestamp."""
        formats = ["%d%b%Y", "%d-%b-%Y", "%Y-%m-%d", "%d%b%y"]
        for fmt in formats:
            try:
                dt = datetime.strptime(expiry_str.strip().upper(), fmt)
                return dt.timestamp()
            except ValueError:
                continue
        return 9999999999.0

    def load_from_url(self, url: Optional[str] = None) -> int:
        """Download instrument master directly from Angel One and cache locally."""
        download_url = url or self.SCRIP_MASTER_URL
        logger.info(f"Downloading Angel One Scrip Master from {download_url}...")
        
        try:
            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    os.makedirs(self.CACHE_DIR, exist_ok=True)
                    with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                    return self._parse_and_index_records(data)
        except Exception as exc:
            logger.warning(f"Failed to download live scrip master ({exc}). Falling back to local cache or seed.")
            return self.load_from_cache()

    def load_from_cache(self) -> int:
        """Load from persisted disk cache if present, otherwise load seed instruments."""
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        return self._parse_and_index_records(data)
            except Exception as e:
                logger.error(f"Error reading instruments cache: {e}")
        
        return self._seed_default_instruments()

    def _seed_default_instruments(self) -> int:
        """
        Default seed data providing dynamic chains for:
        - MCX CRUDEOIL (6500 to 10000 strikes)
        - NIFTY (21000 to 24000 strikes)
        - BANKNIFTY (46000 to 51000 strikes)
        - FINNIFTY (20000 to 23000 strikes)
        - MCX GOLD & SILVER
        - Equity F&O (RELIANCE)
        """
        records = []
        # 1. MCX CRUDEOIL Options Chain (mirroring active MCX strikes)
        crude_strikes = [7500, 7800, 8000, 8200, 8400, 8500, 8600, 8700, 8800, 8900, 9000, 9100, 9200, 9300, 9400, 9500, 9800, 10000]
        for strike in crude_strikes:
            ce_token = f"MCX_CRUDE_{strike}_CE"
            pe_token = f"MCX_CRUDE_{strike}_PE"
            records.append({
                "token": ce_token,
                "symbol": f"CRUDEOIL19FEB26{strike}CE",
                "name": "CRUDEOIL",
                "expiry": "19FEB2026",
                "strike": str(strike),
                "lotsize": "100",
                "instrumenttype": "OPTFUT",
                "exch_seg": "MCX",
                "tick_size": "1.000000"
            })
            records.append({
                "token": pe_token,
                "symbol": f"CRUDEOIL19FEB26{strike}PE",
                "name": "CRUDEOIL",
                "expiry": "19FEB2026",
                "strike": str(strike),
                "lotsize": "100",
                "instrumenttype": "OPTFUT",
                "exch_seg": "MCX",
                "tick_size": "1.000000"
            })
        # Add CRUDEOIL Future
        records.append({
            "token": "MCX_CRUDE_FUT",
            "symbol": "CRUDEOIL19FEB26FUT",
            "name": "CRUDEOIL",
            "expiry": "19FEB2026",
            "strike": "0",
            "lotsize": "100",
            "instrumenttype": "FUTCOM",
            "exch_seg": "MCX",
            "tick_size": "1.000000"
        })

        # 2. NIFTY Options Chain (Weekly & Monthly expiries)
        nifty_expiries = ["26MAR2026", "02APR2026", "30APR2026"]
        nifty_strikes = [22000, 22200, 22400, 22500, 22600, 22800, 23000, 23200, 23400, 23500, 23600, 23800, 24000]
        token_counter = 10000
        for exp in nifty_expiries:
            for s in nifty_strikes:
                token_counter += 1
                records.append({
                    "token": str(token_counter),
                    "symbol": f"NIFTY{exp}{s}CE",
                    "name": "NIFTY",
                    "expiry": exp,
                    "strike": str(s * 100),  # In NFO scrip master, strike is * 100
                    "lotsize": "25",
                    "instrumenttype": "OPTIDX",
                    "exch_seg": "NFO",
                    "tick_size": "5.000000"
                })
                token_counter += 1
                records.append({
                    "token": str(token_counter),
                    "symbol": f"NIFTY{exp}{s}PE",
                    "name": "NIFTY",
                    "expiry": exp,
                    "strike": str(s * 100),
                    "lotsize": "25",
                    "instrumenttype": "OPTIDX",
                    "exch_seg": "NFO",
                    "tick_size": "5.000000"
                })

        # Add NIFTY Future
        records.append({
            "token": "26000",
            "symbol": "NIFTY26MAR26FUT",
            "name": "NIFTY",
            "expiry": "26MAR2026",
            "strike": "0",
            "lotsize": "25",
            "instrumenttype": "FUTIDX",
            "exch_seg": "NFO",
            "tick_size": "5.000000"
        })

        # 3. BANKNIFTY Options Chain
        bn_strikes = [47000, 47500, 48000, 48500, 49000, 49500, 50000]
        for s in bn_strikes:
            token_counter += 1
            records.append({
                "token": str(token_counter),
                "symbol": f"BANKNIFTY26MAR26{s}CE",
                "name": "BANKNIFTY",
                "expiry": "26MAR2026",
                "strike": str(s * 100),
                "lotsize": "15",
                "instrumenttype": "OPTIDX",
                "exch_seg": "NFO",
                "tick_size": "5.000000"
            })
            token_counter += 1
            records.append({
                "token": str(token_counter),
                "symbol": f"BANKNIFTY26MAR26{s}PE",
                "name": "BANKNIFTY",
                "expiry": "26MAR2026",
                "strike": str(s * 100),
                "lotsize": "15",
                "instrumenttype": "OPTIDX",
                "exch_seg": "NFO",
                "tick_size": "5.000000"
            })

        # 4. FINNIFTY Options Chain
        fin_strikes = [21000, 21200, 21400, 21600, 21800, 22000]
        for s in fin_strikes:
            token_counter += 1
            records.append({
                "token": str(token_counter),
                "symbol": f"FINNIFTY26MAR26{s}CE",
                "name": "FINNIFTY",
                "expiry": "26MAR2026",
                "strike": str(s * 100),
                "lotsize": "25",
                "instrumenttype": "OPTIDX",
                "exch_seg": "NFO",
                "tick_size": "5.000000"
            })
            token_counter += 1
            records.append({
                "token": str(token_counter),
                "symbol": f"FINNIFTY26MAR26{s}PE",
                "name": "FINNIFTY",
                "expiry": "26MAR2026",
                "strike": str(s * 100),
                "lotsize": "25",
                "instrumenttype": "OPTIDX",
                "exch_seg": "NFO",
                "tick_size": "5.000000"
            })

        # 5. Equity F&O: RELIANCE
        rel_strikes = [2800, 2900, 3000, 3100]
        for s in rel_strikes:
            token_counter += 1
            records.append({
                "token": str(token_counter),
                "symbol": f"RELIANCE26MAR26{s}CE",
                "name": "RELIANCE",
                "expiry": "26MAR2026",
                "strike": str(s * 100),
                "lotsize": "250",
                "instrumenttype": "OPTSTK",
                "exch_seg": "NFO",
                "tick_size": "5.000000"
            })
            token_counter += 1
            records.append({
                "token": str(token_counter),
                "symbol": f"RELIANCE26MAR26{s}PE",
                "name": "RELIANCE",
                "expiry": "26MAR2026",
                "strike": str(s * 100),
                "lotsize": "250",
                "instrumenttype": "OPTSTK",
                "exch_seg": "NFO",
                "tick_size": "5.000000"
            })

        # 6. MCX GOLD & SILVER
        records.append({
            "token": "MCX_GOLD_FUT",
            "symbol": "GOLD05APR26FUT",
            "name": "GOLD",
            "expiry": "05APR2026",
            "strike": "0",
            "lotsize": "1",
            "instrumenttype": "FUTCOM",
            "exch_seg": "MCX",
            "tick_size": "1.000000"
        })
        records.append({
            "token": "MCX_SILVER_FUT",
            "symbol": "SILVER05MAY26FUT",
            "name": "SILVER",
            "expiry": "05MAY2026",
            "strike": "0",
            "lotsize": "30",
            "instrumenttype": "FUTCOM",
            "exch_seg": "MCX",
            "tick_size": "1.000000"
        })

        return self._parse_and_index_records(records)

    # Lookup Methods
    def get_supported_underlyings(self) -> List[Dict[str, Any]]:
        """Return list of dynamically discovered underlying assets."""
        return list(self._underlyings.values())

    def get_expiries(self, underlying: str, exchange: Optional[str] = None) -> List[str]:
        """Return sorted expiries for an underlying without hardcoding."""
        u = underlying.strip().upper()
        if exchange:
            return self._expiries_map.get((u, exchange.upper()), [])
        
        # Search across exchanges
        for (name, exch), exps in self._expiries_map.items():
            if name == u:
                return exps
        return []

    def get_strikes(self, underlying: str, expiry: str, exchange: Optional[str] = None) -> List[float]:
        """Return sorted numerical strike prices for underlying and expiry."""
        u = underlying.strip().upper()
        exp = expiry.strip().upper()
        if exchange:
            return self._strikes_map.get((u, exchange.upper(), exp), [])
        
        for (name, exch, e), strs in self._strikes_map.items():
            if name == u and e == exp:
                return strs
        return []

    def get_option_contract(
        self,
        underlying: str,
        expiry: str,
        strike: float,
        option_type: str,
        exchange: Optional[str] = None
    ) -> Optional[Instrument]:
        """Microsecond lookup of exact option instrument token."""
        u = underlying.strip().upper()
        exp = expiry.strip().upper()
        ot = option_type.strip().upper()

        if exchange:
            return self._chain_map.get((u, exchange.upper(), exp, float(strike), ot))

        for (name, exch, e, s, t), inst in self._chain_map.items():
            if name == u and e == exp and abs(s - float(strike)) < 0.001 and t == ot:
                return inst
        return None

    def get_option_chain_tokens(
        self,
        underlying: str,
        expiry: str,
        exchange: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Dynamically discover and construct complete option chain matrix:
        Strike, CE Token, PE Token, CE Symbol, PE Symbol, Lot Size, Tick Size.
        Never hard-codes strikes or expiries.
        """
        strikes = self.get_strikes(underlying, expiry, exchange)
        matrix = []

        for strike in strikes:
            ce_inst = self.get_option_contract(underlying, expiry, strike, "CE", exchange)
            pe_inst = self.get_option_contract(underlying, expiry, strike, "PE", exchange)

            lotsize = (ce_inst.lotsize if ce_inst else (pe_inst.lotsize if pe_inst else 1))
            tick_size = (ce_inst.tick_size if ce_inst else (pe_inst.tick_size if pe_inst else 0.05))
            exch = (ce_inst.exch_seg if ce_inst else (pe_inst.exch_seg if pe_inst else "NFO"))

            matrix.append({
                "strike": strike,
                "exchange": exch,
                "lot_size": lotsize,
                "tick_size": tick_size,
                "ce_token": ce_inst.token if ce_inst else None,
                "ce_symbol": ce_inst.symbol if ce_inst else None,
                "pe_token": pe_inst.token if pe_inst else None,
                "pe_symbol": pe_inst.symbol if pe_inst else None,
            })

        return matrix

    def get_instrument_by_token(self, token: str) -> Optional[Instrument]:
        """Look up instrument by token string."""
        return self._token_map.get(str(token).strip())

    def get_lot_size(self, underlying: str, exchange: Optional[str] = None) -> int:
        """Return standard market lot size for underlying."""
        u = underlying.strip().upper()
        meta = self._underlyings.get(u)
        if meta and "lot_size" in meta:
            return meta["lot_size"]
        if u in ("CRUDEOIL", "CRUDEOILM"):
            return 100
        elif u == "NIFTY":
            return 25
        elif u == "BANKNIFTY":
            return 15
        elif u == "FINNIFTY":
            return 25
        elif u == "RELIANCE":
            return 250
        return 1

    def get_instrument_by_symbol(self, symbol: str, exchange: str = "NFO") -> Optional[Instrument]:
        """Look up instrument by symbol and exchange."""
        return self._symbol_map.get((exchange.upper(), symbol.strip().upper()))

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search instruments by partial symbol or underlying name."""
        q = query.strip().upper()
        results = []
        for inst in self._token_map.values():
            if q in inst.symbol or q in inst.name:
                results.append(inst.to_dict())
                if len(results) >= limit:
                    break
        return results

instrument_master = InstrumentMasterService()
