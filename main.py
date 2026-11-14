#!/usr/bin/env python3
"""
========================================================================================
BINANCE USDT-M FUTURES ENGINE (POOL 5 BLUEPRINT: TRUE 2-WAY LONG/SHORT + 30% TAX VAULT)
========================================================================================
Architecture:
  - Exchange: Binance Spot Testnet (https://testnet.binance.vision)
  - Portfolio Architecture: 5-Trader Hardened 3-2 Equalizer
      * Group A (50%): @booobsas, @limpan96 (Scalpers)
      * Group B (50%): @akira, @prateek, @henderson_14 (Macro/Swing)
  - Core Tax Vault Rules:
      1. Real-Time 30% Tax Vault Skim: 30% of every winning trade is ring-fenced into
         the safe tax vault immediately; 70% is returned to active capital to compound.
      2. Zero Loss Offset: Losses are deducted strictly from the trader's active capital;
         the Tax Vault is 100% protected and NEVER touched.
  - Core Execution Safeguards:
      1. Real Live Order Execution: Places live MARKET BUY/SELL orders via Binance Testnet.
      2. Strict 4-Hour Time Exit: Auto-sells position at the 4-hour mark to recycle capital.
      3. Hard -85% Stop-Loss Floor: Protects against tail drawdown.
      4. Position Sizing Cap (₹10 Lakh / ~11,900 USDT equivalent per trade).
      5. Subgroup Rescue & Weekly 50/50 Equalizer.
      6. Telegram Real-Time Notifications for all fills, exits, and tax vault skims.
========================================================================================
"""

import os
import sys
import time
import json
import base64
import signal
import atexit
import math
import hmac
import hashlib
import socket
import gc
import threading
import csv
import http.client
import ssl
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

# Limit socket wait times to avoid hanging
socket.setdefaulttimeout(8.0)

# Windows UTF-8 stdout wrapper
# Immediate unbuffered stdout for cloud consoles (Wispbyte / Docker / Linux)
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
    except Exception:
        pass

# Pure Python standard library .env loader (supports Wispbyte /.env)
for _env_candidate in [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    os.path.join(os.getcwd(), ".env"),
    "/home/container/.env",
    "/.env"
]:
    if os.path.exists(_env_candidate):
        try:
            with open(_env_candidate, "r", encoding="utf-8", errors="ignore") as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _v = _line.split("=", 1)
                        _k = _k.strip()
                        _v = _v.strip().strip("'").strip('"')
                        if _k and _k not in os.environ:
                            os.environ[_k] = _v
        except Exception:
            pass

# --------------------------------------------------------------------------------------
# 1. CREDENTIALS & CONSTANTS
# --------------------------------------------------------------------------------------
BINANCE_TESTNET_BASE_URL = "https://demo-fapi.binance.com"
BINANCE_FUTURES_API_KEY = os.getenv("BINANCE_FUTURES_API_KEY", "29QiqScIhWceyenV7wJtIniETkbO8D2It3939mpule9G6HoBsDF7fixoQUWrK7yO")
BINANCE_FUTURES_SECRET_KEY = os.getenv("BINANCE_FUTURES_SECRET_KEY", "KYJYAs7lijVBWzqHWepaVe8EI1AsWo3OlVBcfhx0Lhlcpv7pEMGP8lKKPIycYzjw")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", BINANCE_FUTURES_API_KEY)
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", BINANCE_FUTURES_SECRET_KEY)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "9140409751:AAGdy1Y-45jlQkr04xRwcmwc1hyiAAfc_XA")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8909652482")

# Optional GitHub Pages Sync (set GITHUB_TOKEN and GITHUB_REPO if syncing to GitHub repo)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "Rhythmofgrace/invo-live")   # Default to user's repo
DASHBOARD_PORT = int(os.getenv("PORT", "8080"))

INVO_BASE_URL = "https://api.invoapp.com"
INVO_REFRESH_TOKEN = os.getenv(
    "INVO_REFRESH_TOKEN",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiY2ExYWEzYjUtYjJhMC00ZjQxLTllODgtYjc4YjE4ZjMyZmQ3IiwiZXhwaXJlcyI6MTgyMDIwMTI0NS4zODA3OTA1LCJkZXZpY2VfaWQiOiJkM2M1ZGYzNi0zNmZjLTRkZDQtODc2OS1lMzVhM2Y5NWYwZGIiLCJ0cmFkaW5nX2FjY291bnQiOnsiaWQiOiI0ZWRmNWJhMi1mNDk3LTQxNDctOWU3NC1lYzk5ZjU4M2U5NDUiLCJwcm92aWRlciI6InR1cm5rZXkiLCJvcmdhbml6YXRpb25faWQiOiJlNzJkODdmMC00ODkxLTQxMzItOGY3ZS1iZTg5NjE1MjU1M2QiLCJ3YWxsZXRfYWRkcmVzcyI6IjB4NzRiNmE0OGJENkZjYTQxN0NmNWIwMjIxRDRDQzA3RDhkOWJCYmMxOCIsInByaW1hcnkiOnRydWUsIndhbGxldCI6eyJldm1fYWRkcmVzcyI6IjB4NzRiNmE0OGJENkZjYTQxN0NmNWIwMjIxRDRDQzA3RDhkOWJCYmMxOCIsInN2bV9hZGRyZXNzIjoiSG03R0xodVVQcngyN29CNDFMZ01HaFVVZk1Lb21jNHRYd0RFVWNmTENkOWoifX0sInJlZnJlc2hhYmxlIjp0cnVlfQ.XcGGJhEYbscNZI58PMd8mxekqIhYlYhXoVL8m2N65a4"
)

# Pool 5 Traders
POOL5_CONFIG = {
    "name": "Pool5 (Binance Live 3-2 Equalizer with 30% Tax Vault)",
    "subgroups": {
        "group_a": ["inquisitor", "lazylegendx"],           # 50% Capital (Scalpers)
        "group_b": ["akira", "nicush", "ka5h"]              # 50% Capital (Macro/Swing)
    },
    "traders": [
        {"username": "akira", "subgroup": "group_b", "portfolio_id": "72813ea9-35db-4ffe-b0b1-2d71cbbac837", "expected_title": "Crypto"},
        {"username": "nicush", "subgroup": "group_b", "portfolio_id": "f392d602-4882-40bc-8198-6d681943284d", "expected_title": "Kitchen"},
        {"username": "ka5h", "legacy_username": "henderson_14", "subgroup": "group_b", "portfolio_id": "5a0fd0c7-3031-485a-b379-41c16abb395c", "expected_title": "Main Port"},
        {"username": "inquisitor", "legacy_username": "booobsas", "subgroup": "group_a", "portfolio_id": "1c4f8dfd-3e4c-4378-b6fd-a0f694c10fd3", "expected_title": "$100 to $1M"},
        {"username": "lazylegendx", "legacy_username": "lazylegend0_", "subgroup": "group_a", "portfolio_id": "f97c4675-66b1-49fc-86a4-24fb3aa16a03", "expected_title": "𝘛𝘶𝘧𝘢𝘯"},
    ]
}

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "binance_live_state.json")
TRADES_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.csv")
TRADES_JSONL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.jsonl")
COMMISSION_RATE = 0.0005          # Binance spot standard fee 0.1% (or BNB fee 0.075%)
TAX_RATE = 0.30                  # 30% flat tax on gains (Section 115BBH)
SL_CAP_PCT = 85.0                # Hard -85% protective stop-loss floor
MAX_HOLD_HOURS = 4.0             # Strict 4-Hour Time Exit for fast capital recycling
POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL", "12.0")) # 12s sleep cadence (< 1% CPU on Wispbyte)
REBALANCE_INTERVAL_DAYS = 7.0    # 7-day 50/50 subgroup rebalancing
SIZING_RATIO = 0.90              # 10% fee & slippage reserve buffer
USDT_INR = 93.85                  # Live USD to INR rate fallback, dynamically updated

def fetch_live_usdt_inr():
    """Fetches real-time USD to INR live exchange rate from official Forex APIs."""
    global USDT_INR
    try:
        req = urllib.request.Request("https://open.er-api.com/v6/latest/USD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.load(resp)
            rate = data.get("rates", {}).get("INR")
            if rate and rate > 50:
                USDT_INR = round(float(rate), 2)
                return USDT_INR
    except Exception:
        pass
    try:
        req = urllib.request.Request("https://api.exchangerate-api.com/v4/latest/USD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.load(resp)
            rate = data.get("rates", {}).get("INR")
            if rate and rate > 50:
                USDT_INR = round(float(rate), 2)
                return USDT_INR
    except Exception:
        pass
    return USDT_INR

try:
    fetch_live_usdt_inr()
except Exception:
    pass

INITIAL_SEED_INR = float(os.getenv("INITIAL_SEED_INR", "10000.0"))
INITIAL_SEED_USDT = float(os.getenv("INITIAL_SEED_USDT", "106.55")) # ₹10,000 INR @ live 93.85 rate ($106.55 USDT)
FORCE_RESET_EPOCH = 1794538500        # Reset checkpoint Nov 13 08:30 AM IST
MAX_MARGIN_CAP_USDT = 11900.0    # ₹10 Lakh equivalent in USDT (~$11,900)
IST = timezone(timedelta(hours=5, minutes=30))

_LAST_TG_SENT = 0.0


# --------------------------------------------------------------------------------------
# 2. TIME & FORMATTING HELPERS
# --------------------------------------------------------------------------------------
def now_ist_str() -> str:
    return datetime.now(timezone.utc).astimezone(IST).strftime("%Y-%m-%d %I:%M:%S %p IST")

def now_ist_short() -> str:
    return datetime.now(timezone.utc).astimezone(IST).strftime("%b %d, %I:%M %p IST")

def fmt_usdt(val: float) -> str:
    if val is None: return "$0.00"
    return f"${val:,.2f}"

def fmt_inr(val: float) -> str:
    if val is None: return "₹0"
    inr = val * USDT_INR
    if abs(inr) >= 10000000:
        return f"₹{inr / 10000000:.2f} Cr"
    elif abs(inr) >= 100000:
        return f"₹{inr / 100000:.2f} Lakh"
    return f"₹{inr:,.2f}"

def send_telegram(text: str) -> bool:
    global _LAST_TG_SENT
    now = time.time()
    if (now - _LAST_TG_SENT) < 1.0:
        time.sleep(1.0 - (now - _LAST_TG_SENT))
    _LAST_TG_SENT = time.time()

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return bool(res.get("ok"))
    except Exception as e:
        print(f"[Telegram] Failed to send message: {e}", flush=True)
        return False


# --------------------------------------------------------------------------------------
# 2B. GITHUB PAGES & MICRO HTTP SERVER SYNC
# --------------------------------------------------------------------------------------
def sync_file_to_github(path_in_repo: str, content_bytes: bytes, commit_msg: str):
    """Pushes any file directly to GitHub repo via REST API (uses <2KB)."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    try:
        b64_content = base64.b64encode(content_bytes).decode("utf-8")
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path_in_repo}"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Invo-Wispbyte-Sync/1.0"
        }
        sha = None
        try:
            req_get = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req_get, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                sha = data.get("sha")
        except Exception:
            pass

        payload = {
            "message": commit_msg,
            "content": b64_content
        }
        if sha:
            payload["sha"] = sha

        put_data = json.dumps(payload).encode("utf-8")
        req_put = urllib.request.Request(api_url, data=put_data, headers=headers, method="PUT")
        with urllib.request.urlopen(req_put, timeout=6.0) as resp:
            if resp.status in (200, 201):
                pass
    except Exception as e:
        print(f"[GitHub Sync Note: {path_in_repo}] {e}", flush=True)

def sync_state_to_github(state_dict: dict):
    """Pushes binance_live_state.json directly to GitHub repo via REST API."""
    content_bytes = json.dumps(state_dict, indent=2).encode("utf-8")
    sync_file_to_github("binance_live_state.json", content_bytes, f"Auto-Sync: Live Stats [{now_ist_short()}]")

def start_micro_http_server(port: int = DASHBOARD_PORT):
    """Starts a non-blocking, zero-overhead HTTP server to view index.html and state."""
    live_dir = os.path.dirname(os.path.abspath(__file__))
    def serve():
        class SilentHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=live_dir, **kwargs)
            def log_message(self, format, *args):
                pass  # Zero terminal clutter

        try:
            httpd = HTTPServer(("0.0.0.0", port), SilentHandler)
            print(f"[Web Dashboard] Live dashboard active at http://0.0.0.0:{port} (serving {live_dir})", flush=True)
            httpd.serve_forever()
        except Exception as e:
            print(f"[Web Dashboard Note] Server could not bind to port {port}: {e}", flush=True)

    t = threading.Thread(target=serve, daemon=True)
    t.start()


# --------------------------------------------------------------------------------------
# 3. BINANCE SPOT TESTNET CLIENT
# --------------------------------------------------------------------------------------
class BinanceFuturesClient:
    """High-efficiency Binance USDT-M Futures Client supporting true bidirectional LONG & SHORT trading."""
    def __init__(self, api_key: str = "", secret_key: str = ""):
        self.api_key = api_key or os.getenv("BINANCE_FUTURES_API_KEY", BINANCE_FUTURES_API_KEY)
        self.secret_key = secret_key or os.getenv("BINANCE_FUTURES_SECRET_KEY", BINANCE_FUTURES_SECRET_KEY)
        self.testnet_url = "https://demo-fapi.binance.com"
        self.live_price_url = "https://fapi.binance.com"
        self.has_credentials = bool(self.api_key and self.secret_key)
        self.symbol_info_cache = {}
        self.refresh_exchange_info()

    def _sign(self, params: dict) -> str:
        params["timestamp"] = int(time.time() * 1000)
        query = urllib.parse.urlencode(params)
        sig = hmac.new(self.secret_key.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{query}&signature={sig}"

    def refresh_exchange_info(self):
        try:
            req = urllib.request.Request(f"{self.live_price_url}/fapi/v1/exchangeInfo", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for s in data.get("symbols", []):
                    if s.get("contractType") == "PERPETUAL":
                        sym = s["symbol"]
                        step_size = 0.001
                        min_qty = 0.001
                        for f in s.get("filters", []):
                            if f["filterType"] == "LOT_SIZE":
                                step_size = float(f.get("stepSize") or 0.001)
                                min_qty = float(f.get("minQty") or 0.001)
                        self.symbol_info_cache[sym] = {
                            "stepSize": step_size,
                            "minQty": min_qty,
                            "pricePrecision": int(s.get("pricePrecision") or 2)
                        }
            print(f"[Binance Futures] Loaded {len(self.symbol_info_cache)} perpetual contract symbols.", flush=True)
        except Exception as e:
            print(f"[Binance Futures] Note loading exchangeInfo: {e}", flush=True)

    def format_qty(self, pair: str, qty: float) -> float:
        info = self.symbol_info_cache.get(pair, {})
        step = float(info.get("stepSize") or 0.001)
        min_qty = float(info.get("minQty") or 0.001)
        if step > 0:
            precision = max(0, int(round(-math.log10(step)))) if step < 1.0 else 0
            fmt_qty = math.floor(qty * (10 ** precision)) / (10 ** precision)
            return max(fmt_qty, min_qty)
        return round(qty, 3)

    def get_symbol_pair(self, ticker: str) -> str:
        sym = (ticker or "").upper().strip()
        pair = sym if sym.endswith("USDT") else f"{sym}USDT"
        if pair in self.symbol_info_cache:
            return pair
        return "BTCUSDT"

    def get_ticker_price(self, pair: str) -> float:
        for base in [self.live_price_url, self.testnet_url]:
            try:
                req = urllib.request.Request(f"{base}/fapi/v1/ticker/price?symbol={pair}", headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    p = float(data.get("price") or 0.0)
                    if p > 0: return p
            except Exception:
                continue
        return 0.0

    def get_account_balances(self) -> dict:
        """Fetches account balances from Binance Futures Demo/Testnet."""
        if not self.has_credentials:
            return {"USDT": {"free": 5000.0, "locked": 0.0}}
        try:
            params = {}
            query_str = self._sign(params)
            url = f"{self.testnet_url}/fapi/v2/account?{query_str}"
            req = urllib.request.Request(url, headers={"X-MBX-APIKEY": self.api_key})
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                avail = float(data.get("availableBalance") or 0.0)
                total = float(data.get("totalWalletBalance") or avail)
                return {"USDT": {"free": avail, "locked": max(0.0, total - avail)}}
        except Exception as e:
            print(f"[Binance Futures] Note reading balances: {e}", flush=True)
            return {"USDT": {"free": 5000.0, "locked": 0.0}}

    def place_futures_order(self, pair: str, side: str, qty: float, position_side: str = None) -> dict:
        """Executes order on Binance Futures Demo/Testnet if keys present, else matches against live mark price."""
        curr_price = self.get_ticker_price(pair)
        order_id = f"FUT_{int(time.time()*1000)}"
        exec_qty = self.format_qty(pair, qty)

        if self.has_credentials:
            try:
                params = {
                    "symbol": pair,
                    "side": side,
                    "type": "MARKET",
                    "quantity": exec_qty
                }
                query_str = self._sign(params)
                url = f"{self.testnet_url}/fapi/v1/order"
                req = urllib.request.Request(url, data=query_str.encode("utf-8"), headers={"X-MBX-APIKEY": self.api_key}, method="POST")
                with urllib.request.urlopen(req, timeout=6.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    avg_p = float(data.get("avgPrice") or 0.0)
                    if avg_p <= 0.0:
                        avg_p = curr_price
                    return {
                        "success": True,
                        "order_id": str(data.get("orderId", order_id)),
                        "executed_qty": float(data.get("executedQty") or exec_qty),
                        "avg_price": avg_p,
                    }
            except Exception as e:
                print(f"[Binance Futures API Note: {e} -> fallback to live mark fill]", flush=True)

        return {
            "success": True,
            "order_id": order_id,
            "executed_qty": qty,
            "avg_price": curr_price
        }

# --------------------------------------------------------------------------------------
# 4. INVO API CLIENT (HIGH-EFFICIENCY KEEP-ALIVE CONNECTION POOL)
# --------------------------------------------------------------------------------------
class InvoClient:
    def __init__(self, refresh_token: str):
        self.refresh_token = refresh_token
        self.access_token = None
        self.token_expiry = 0
        self._conn = None
        self._ssl_ctx = ssl.create_default_context()

    def _get_conn(self):
        if self._conn is None:
            self._conn = http.client.HTTPSConnection("api.invoapp.com", timeout=8.0, context=self._ssl_ctx)
        return self._conn

    def _reset_conn(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _headers(self, auth_token: str = None) -> dict:
        h = {
            "x-app-version": "0.0.75",
            "x-platform": "web",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Connection": "keep-alive"
        }
        if auth_token:
            h["Authorization"] = auth_token if auth_token.startswith("Bearer ") else f"Bearer {auth_token}"
        return h

    def refresh_access_token(self) -> bool:
        headers = self._headers(self.refresh_token)
        for attempt in range(2):
            try:
                conn = self._get_conn()
                conn.request("GET", "/v1_0/auth/refresh_token", headers=headers)
                resp = conn.getresponse()
                raw = resp.read()
                if resp.status == 200:
                    data = json.loads(raw.decode("utf-8"))
                    new_token = data.get("accessToken")
                    if new_token and "." in new_token:
                        self.access_token = new_token
                        payload = new_token.split(".")[1]
                        padded = payload + "=" * (-len(payload) % 4)
                        claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
                        self.token_expiry = float(claims.get("exp", time.time() + 3600))
                        return True
            except Exception:
                self._reset_conn()
                time.sleep(0.5)
        return False

    def ensure_token(self):
        if not self.access_token or time.time() >= (self.token_expiry - 60):
            if not self.refresh_access_token():
                raise RuntimeError("Failed to refresh Invo access token")

    def request(self, endpoint: str, method: str = "GET", body: dict = None):
        try:
            self.ensure_token()
        except Exception:
            return None

        headers = self._headers(self.access_token)
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body)

        for attempt in range(2):
            try:
                conn = self._get_conn()
                conn.request(method, endpoint, body=data, headers=headers)
                resp = conn.getresponse()
                raw = resp.read()
                if resp.status == 401 and attempt < 1:
                    if self.refresh_access_token():
                        headers["Authorization"] = f"Bearer {self.access_token}"
                        self._reset_conn()
                        continue
                if resp.status in (200, 201):
                    return json.loads(raw.decode("utf-8"))
                return None
            except Exception:
                self._reset_conn()
                time.sleep(0.3)
        return None

    def get_open_investments(self, portfolio_id: str):
        res = self.request(
            "/v1_0/investments/get_investments",
            method="POST",
            body={"portfolioId": portfolio_id, "isOpen": True, "params": {"page": 1, "size": 50}},
        )
        if not isinstance(res, dict) or "investmentsTicker" not in res:
            return None
        return res["investmentsTicker"]

    def get_closed_investments(self, portfolio_id: str, limit: int = 15):
        res = self.request(
            "/v1_0/investments/get_investments",
            method="POST",
            body={"portfolioId": portfolio_id, "isOpen": False, "params": {"page": 1, "size": limit}},
        )
        if not isinstance(res, dict) or "investmentsTicker" not in res:
            return []
        return res.get("investmentsTicker", [])


# --------------------------------------------------------------------------------------
# 5. POOL 5 LIVE TESTNET TRADING ENGINE WITH 30% TAX VAULT
# --------------------------------------------------------------------------------------
class Pool5LiveBinanceEngine:
    def __init__(self, binance_client: BinanceFuturesClient, pool_config: dict = POOL5_CONFIG):
        self.bn = binance_client
        self.config = pool_config
        self.subgroups = pool_config["subgroups"]
        self.all_users = [t["username"] for t in pool_config["traders"]]

        # State Variables
        self.active_balances = {}           # Active trading capital per trader in USDT
        self.tax_vault_usdt = 0.0           # Cumulative 30% safe tax vault in USDT
        self.active_positions = {}          # Open positions: {username: pos_dict}
        self.stats = {}                     # Realized performance per trader
        self.trade_history = []
        self.notifications = []
        self.last_rebalance_epoch = time.time()
        self.last_update_epoch = time.time()

        if os.path.exists(STATE_FILE):
            self.load_state()
        else:
            self.bootstrap_state()

    def bootstrap_state(self):
        print(f"[{now_ist_str()}] Bootstrapping Binance Testnet Pool 5 state with ₹10,000 INR ({INITIAL_SEED_USDT:.2f} USDT)...", flush=True)
        total_usdt = INITIAL_SEED_USDT
        
        # 50/50 Subgroup Split (Group A: 50%, Group B: 50%)
        grp_a = self.subgroups["group_a"]
        grp_b = self.subgroups["group_b"]
        half_capital = total_usdt / 2.0

        for u in grp_a:
            self.active_balances[u] = half_capital / len(grp_a)
        for u in grp_b:
            self.active_balances[u] = half_capital / len(grp_b)

        self.reset_epoch = FORCE_RESET_EPOCH
        self.tax_vault_usdt = 0.0
        self.active_positions = {u: [] for u in self.all_users}
        self.stats = {u: {"trades": 0, "wins": 0, "losses": 0, "pnl_usdt": 0.0, "tax_usdt": 0.0} for u in self.all_users}
        self.trade_history = []
        self.notifications = []
        self.last_rebalance_epoch = time.time()
        self.last_update_epoch = time.time()

        self.save_state()
        print(f"[Bootstrap] Completed! Total USDT Capital: {fmt_usdt(total_usdt)} ({fmt_inr(total_usdt)})", flush=True)

    def load_state(self):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("reset_epoch", 0) < FORCE_RESET_EPOCH or "--reset" in sys.argv:
                print(f"[State Reset] Force-resetting portfolio to fresh ₹10,000 INR ({INITIAL_SEED_USDT:.2f} USDT) as requested...", flush=True)
                self.bootstrap_state()
                return
            self.active_balances = state.get("active_balances", {})
            # Seamless migration for renamed traders
            if "booobsas" in self.active_balances and "inquisitor" not in self.active_balances:
                self.active_balances["inquisitor"] = self.active_balances.pop("booobsas")
            if "henderson_14" in self.active_balances and "ka5h" not in self.active_balances:
                self.active_balances["ka5h"] = self.active_balances.pop("henderson_14")

            self.tax_vault_usdt = float(state.get("tax_vault_usdt", 0.0))
            raw_pos = state.get("active_positions", {})
            if "booobsas" in raw_pos and "inquisitor" not in raw_pos:
                raw_pos["inquisitor"] = raw_pos.pop("booobsas")
            if "henderson_14" in raw_pos and "ka5h" not in raw_pos:
                raw_pos["ka5h"] = raw_pos.pop("henderson_14")

            self.active_positions = {}
            for u in self.all_users:
                v = raw_pos.get(u, [])
                if v is None:
                    self.active_positions[u] = []
                elif isinstance(v, list):
                    self.active_positions[u] = [p for p in v if isinstance(p, dict)]
                elif isinstance(v, dict):
                    self.active_positions[u] = [v]
                else:
                    self.active_positions[u] = []
            self.stats = state.get("stats", {})
            if "booobsas" in self.stats and "inquisitor" not in self.stats:
                self.stats["inquisitor"] = self.stats.pop("booobsas")
            if "henderson_14" in self.stats and "ka5h" not in self.stats:
                self.stats["ka5h"] = self.stats.pop("henderson_14")
            for u in self.all_users:
                if u not in self.stats:
                    self.stats[u] = {"trades": 0, "wins": 0, "losses": 0, "pnl_usdt": 0.0, "tax_usdt": 0.0}
            self.trade_history = state.get("trade_history", [])
            self.notifications = state.get("notifications", [])
            self.wispbyte_close_epoch = float(state.get("wispbyte_close_epoch", 0.0))
            if not self.wispbyte_close_epoch:
                env_epoch = os.getenv("WISPBAYTE_CLOSE_EPOCH")
                env_hrs = os.getenv("WISPBAYTE_REMAINING_HOURS")
                if env_epoch:
                    try:
                        self.wispbyte_close_epoch = float(env_epoch)
                    except Exception:
                        pass
                elif env_hrs:
                    try:
                        self.wispbyte_close_epoch = time.time() + float(env_hrs) * 3600.0
                    except Exception:
                        pass
            self.sent_close_warnings = set()
            self.last_rebalance_epoch = float(state.get("last_rebalance_epoch", time.time()))
            self.last_update_epoch = float(state.get("last_update_epoch", time.time()))
            print(f"[State] Loaded existing state. Total Equity: {fmt_usdt(self.total_portfolio_equity())} | Vault: {fmt_usdt(self.tax_vault_usdt)}")
        except Exception as e:
            print(f"[State Error] {e}. Re-bootstrapping...", flush=True)
            self.bootstrap_state()

    def export_trades_csv(self):
        """Persists all trade logs to trades.csv for easy verification & audit."""
        fieldnames = [
            "time_ist",
            "username",
            "pair",
            "direction",
            "margin_spent",
            "entry_price",
            "exit_price",
            "quote_received",
            "gross_pnl_usdt",
            "tax_skim_usdt",
            "net_pnl_usdt",
            "roi_pct",
            "exit_reason",
            "entry_order_id",
            "sell_order_id",
            "tax_vault_after_usdt",
            "trader_balance_after_usdt",
            "portfolio_equity_after_usdt"
        ]
        try:
            with open(TRADES_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for t in self.trade_history:
                    row = dict(t)
                    if "roi_pct" not in row:
                        m = float(row.get("margin_spent") or 0.0)
                        p = float(row.get("net_pnl_usdt") or 0.0)
                        row["roi_pct"] = round((p / m * 100.0) if m > 0 else 0.0, 2)
                    writer.writerow(row)
            
            # Sync to GitHub so it is always accessible & downloadable
            with open(TRADES_CSV, "rb") as f:
                sync_file_to_github("trades.csv", f.read(), f"Auto-Sync: Trades CSV [{now_ist_short()}]")
        except Exception as e:
            print(f"[Trades CSV Note] {e}", flush=True)

    def save_state(self):
        tmp_file = STATE_FILE + ".tmp"
        state = {
            "version": "pool5_binance_testnet_tax_vault_v1",
            "reset_epoch": getattr(self, "reset_epoch", FORCE_RESET_EPOCH),
            "initial_seed_usdt": INITIAL_SEED_USDT,
            "initial_seed_inr": INITIAL_SEED_INR,
            "last_update_ist": now_ist_str(),
            "last_update_epoch": time.time(),
            "last_rebalance_epoch": self.last_rebalance_epoch,
            "total_portfolio_equity": self.total_portfolio_equity(),
            "total_active_trading_capital": sum(self.active_balances.values()),
            "tax_vault_usdt": self.tax_vault_usdt,
            "tax_vault_inr": self.tax_vault_usdt * USDT_INR,
            "usdt_inr_rate": USDT_INR,
            "active_balances": self.active_balances,
            "active_positions": self.active_positions,
            "stats": self.stats,
            "trade_history": self.trade_history,  # keep all trades for complete export
            "notifications": self.notifications[-20:],  # last 20 notifications for website banner/toasts
            "wispbyte_close_epoch": getattr(self, "wispbyte_close_epoch", 0.0)
        }
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_file, STATE_FILE)
        sync_state_to_github(state)
        self.export_trades_csv()

    def add_notification(self, title: str, message: str, level: str = "info"):
        """Adds a notification that broadcasts to the GitHub Pages live dashboard."""
        notif = {
            "id": f"notif_{int(time.time()*1000)}",
            "time_ist": now_ist_str(),
            "time_short": now_ist_short(),
            "epoch": time.time(),
            "title": title,
            "message": message,
            "level": level  # "success", "info", "warning", "danger"
        }
        self.notifications.append(notif)
        self.notifications = self.notifications[-20:]
        self.save_state()
        return notif

    def total_portfolio_equity(self) -> float:
        tot = sum(self.active_balances.values())
        for u, pos_list in self.active_positions.items():
            if isinstance(pos_list, list):
                for pos in pos_list:
                    if isinstance(pos, dict):
                        tot += pos.get("allocated_margin_usdt", 0.0)
            elif isinstance(pos_list, dict):
                tot += pos_list.get("allocated_margin_usdt", 0.0)
        return tot + self.tax_vault_usdt

    def check_subgroup_rescue(self, username: str):
        pos_list = self.active_positions.get(username, [])
        if not isinstance(pos_list, list):
            pos_list = [pos_list] if isinstance(pos_list, dict) else []
        user_equity = self.active_balances.get(username, 0.0) + sum(p.get("allocated_margin_usdt", 0.0) for p in pos_list)
        if user_equity > 10.0: return
        grp_a = self.config["subgroups"]["group_a"]
        peer_group = grp_a if username in grp_a else self.config["subgroups"]["group_b"]
        donor = max(peer_group, key=lambda x: self.active_balances.get(x, 0.0))
        if self.active_balances.get(donor, 0.0) > 50.0:
            transfer = 25.0
            self.active_balances[donor] -= transfer
            self.active_balances[username] = self.active_balances.get(username, 0.0) + transfer
            self.save_state()
            send_telegram(
                f"🛡️ <b>RESCUE: @{username} Recapitalized</b>\n"
                f"Transferred {fmt_usdt(transfer)} from @{donor}."
            )

    # --------------------------------------------------------------------------
    # LIVE ORDER EXECUTION: FUTURES BIDIRECTIONAL (LONG & SHORT)
    # --------------------------------------------------------------------------
    def open_live_trade(self, username: str, ticker: str, direction: str = "LONG", leverage: float = 1.0, trader_sl: float = None, trader_tp: float = None, invo_entry_size: float = None, invo_entry_price: float = None) -> dict:
        pos_list = self.active_positions.get(username, [])
        if not isinstance(pos_list, list):
            pos_list = [pos_list] if isinstance(pos_list, dict) else []
            self.active_positions[username] = pos_list

        if any(p.get("ticker", "").upper() == ticker.upper() for p in pos_list):
            return {"error": f"@{username} already has an active position in {ticker}"}

        # ----------------------------------------------------------------------
        # FLEET ALTCOIN DEDUP GUARD:
        # High-liquidity majors (BTC, ETH) allow concurrent fleet positions.
        # Thin altcoins are strictly limited to 1 trader max across the entire fleet to prevent slippage & double exposure.
        # ----------------------------------------------------------------------
        is_major = ticker.upper() in {"BTC", "ETH", "BTCUSDT", "ETHUSDT"}
        if not is_major:
            for other_user, other_positions in self.active_positions.items():
                if isinstance(other_positions, list):
                    for other_pos in other_positions:
                        if other_pos.get("ticker", "").upper() == ticker.upper():
                            print(f"[Fleet Altcoin Dedup Guard] Skipped @{username} entry on {ticker}: Already actively held by @{other_user}", flush=True)
                            return {"error": f"Fleet Altcoin Dedup Guard: {ticker} is already actively held by @{other_user}"}

        self.check_subgroup_rescue(username)
        cur_cash = self.active_balances.get(username, 0.0)
        total_equity = cur_cash + sum(p.get("allocated_margin_usdt", 0.0) for p in pos_list)

        max_slots = 2 if total_equity >= 20.0 else 1
        if len(pos_list) >= max_slots:
            return {"error": f"@{username} reached maximum active slots ({len(pos_list)}/{max_slots})"}

        remaining_slots = max(1, max_slots - len(pos_list))
        trade_margin_usdt = min((cur_cash / remaining_slots) * SIZING_RATIO, MAX_MARGIN_CAP_USDT)

        if trade_margin_usdt < 5.0:
            return {"error": f"Insufficient trade margin for @{username}: {fmt_usdt(trade_margin_usdt)} (min $5)"}

        # CoinDCX whitelist filter
        try:
            with urllib.request.urlopen("https://api.coindcx.com/exchange/v1/derivatives/futures/data/active_instruments", timeout=4.0) as r:
                cdcx_coins = {s.replace("B-", "").replace("I-", "").split("_")[0].upper() for s in json.load(r)}
            if ticker.upper() not in cdcx_coins:
                print(f"[CoinDCX Filter] Skipped {ticker}: not listed on CoinDCX derivatives", flush=True)
                return {"error": f"{ticker} not on CoinDCX"}
        except Exception:
            pass

        pair = self.bn.get_symbol_pair(ticker)
        curr_price = self.bn.get_ticker_price(pair)
        if curr_price <= 0:
            return {"error": f"Could not fetch live Futures price for {pair}"}

        # Compute contract quantity: (Margin * Leverage) / Entry Price
        notional_val = trade_margin_usdt * leverage
        exec_qty = notional_val / curr_price

        # Execute Live Futures Order: BUY for LONG, SELL for SHORT
        entry_side = "BUY" if direction == "LONG" else "SELL"
        order_res = self.bn.place_futures_order(pair, side=entry_side, qty=exec_qty)
        if not order_res.get("success"):
            return {"error": f"Futures order failed: {order_res.get('error')}"}

        avg_entry = order_res.get("avg_price") or curr_price
        order_id = order_res.get("order_id")

        # Stop-Loss Floor (-85%)
        sl_floor_price = avg_entry * (1.0 - (SL_CAP_PCT / 100.0) / leverage) if direction == "LONG" else avg_entry * (1.0 + (SL_CAP_PCT / 100.0) / leverage)

        self.active_balances[username] = max(0.0, cur_cash - trade_margin_usdt)
        new_pos = {
            "ticker": ticker,
            "pair": pair,
            "direction": direction,
            "leverage": leverage,
            "allocated_margin_usdt": trade_margin_usdt,
            "untraded_cash_usdt": self.active_balances[username],
            "executed_qty": exec_qty,
            "entry_price": avg_entry,
            "entry_order_id": order_id,
            "entry_epoch": time.time(),
            "entry_ist": now_ist_str(),
            "sl_floor_price": sl_floor_price,
            "trader_sl_price": float(trader_sl) if trader_sl and float(trader_sl) > 0 else None,
            "trader_tp_price": float(trader_tp) if trader_tp and float(trader_tp) > 0 else None,
            "invo_entry_size": float(invo_entry_size) if invo_entry_size and float(invo_entry_size) > 0 else 1.0,
            "invo_entry_price": float(invo_entry_price) if invo_entry_price and float(invo_entry_price) > 0 else avg_entry,
            "loans": []
        }
        self.active_positions[username].append(new_pos)
        self.save_state()

        slot_idx = len(self.active_positions[username])
        msg = (
            f"🚀 <b>BINANCE FUTURES ENTRY: @{username} (Slot {slot_idx}/{max_slots})</b>\n"
            f"Contract: <b>{pair}</b> (<b>{direction}</b> {int(leverage)}x)\n"
            f"Entry Price: <b>${avg_entry:,.4f}</b> | Size: {fmt_usdt(notional_val)}\n"
            f"Margin Invested: <b>{fmt_usdt(trade_margin_usdt)}</b> ({fmt_inr(trade_margin_usdt)})\n"
            f"Stop-Loss Floor: <b>${sl_floor_price:,.4f}</b> (-85%)\n"
            f"Order ID: <code>{order_id}</code>"
        )
        send_telegram(msg)
        print(f"\n[Futures Entry] {msg}\n", flush=True)
        self.add_notification(
            title=f"🚀 Entry: @{username} {pair} ({direction} {int(leverage)}x)",
            message=f"Filled @ ${avg_entry:,.4f} | Margin: {fmt_usdt(trade_margin_usdt)} | Order: {order_id}",
            level="info"
        )
        return {"success": True, "position": new_pos}

    # --------------------------------------------------------------------------
    # LIVE ORDER EXECUTION: SCALE-IN / DCA WITH FLEET PEER LENDING
    # --------------------------------------------------------------------------
    def scale_in_live_trade(self, username: str, target_pos: dict, invo_inv: dict) -> dict:
        """
        Executes a proportionate scale-in / DCA add-on order on Binance when an Invo trader increases position size.
        If the active trader lacks sufficient cash, it automatically borrows from an idle peer trader
        under the Fleet Peer Lending protocol.
        """
        pair = target_pos["pair"]
        ticker = target_pos["ticker"]
        direction = target_pos.get("direction", "LONG")
        leverage = target_pos.get("leverage", 1.0)
        curr_margin = target_pos.get("allocated_margin_usdt", 0.0)
        curr_qty = target_pos.get("executed_qty", 0.0)
        old_entry = target_pos.get("entry_price", 0.0)

        new_invo_size = float(invo_inv.get("entrySize") or 0.0)
        old_invo_size = float(target_pos.get("invo_entry_size") or 1.0)
        if new_invo_size <= (old_invo_size * 1.10):
            return {"error": "No meaningful size increase detected"}

        size_multiplier = (new_invo_size - old_invo_size) / max(0.01, old_invo_size)
        raw_needed_margin = curr_margin * size_multiplier
        needed_margin = min(raw_needed_margin, MAX_MARGIN_CAP_USDT)
        needed_margin = max(5.0, needed_margin)

        # ----------------------------------------------------------------------
        # FLEET PEER LENDING PROTOCOL
        # ----------------------------------------------------------------------
        cur_cash = self.active_balances.get(username, 0.0)
        user_contrib = 0.0
        borrowed_amt = 0.0
        lender_user = None

        # Check if user has sufficient cash (keeping a small $2.00 buffer)
        available_user_cash = max(0.0, cur_cash - 2.0)
        if available_user_cash >= needed_margin:
            user_contrib = needed_margin
        else:
            user_contrib = available_user_cash
            shortfall = needed_margin - user_contrib

            # Search for richest idle peer trader
            grp_a = self.config["subgroups"]["group_a"]
            peer_group = grp_a if username in grp_a else self.config["subgroups"]["group_b"]
            candidates = [p for p in peer_group if p != username and self.active_balances.get(p, 0.0) > 10.0]
            if not candidates:
                other_grp = self.config["subgroups"]["group_b"] if username in grp_a else grp_a
                candidates = [p for p in other_grp if self.active_balances.get(p, 0.0) > 10.0]

            if candidates:
                lender_user = max(candidates, key=lambda x: self.active_balances.get(x, 0.0))
                lender_avail = max(0.0, self.active_balances.get(lender_user, 0.0) - 10.0) # Keep $10 buffer for lender
                borrowed_amt = min(shortfall, lender_avail)

        total_add_margin = user_contrib + borrowed_amt
        if total_add_margin < 5.0:
            print(f"[Scale-In Note] Insufficient fleet liquidity for @{username} on {ticker}: needed ${needed_margin:.2f}, only ${total_add_margin:.2f} available", flush=True)
            return {"error": "Insufficient fleet liquidity"}

        curr_price = self.bn.get_ticker_price(pair)
        if curr_price <= 0:
            return {"error": f"Failed to fetch market price for {pair}"}

        add_notional = total_add_margin * leverage
        add_qty = add_notional / curr_price

        order_side = "BUY" if direction == "LONG" else "SELL"
        order_res = self.bn.place_futures_order(pair, side=order_side, qty=add_qty)
        if not order_res.get("success"):
            print(f"[Scale-In Order Error] {order_res.get('error')}", flush=True)
            return {"error": order_res.get("error")}

        fill_price = order_res.get("avg_price") or curr_price
        order_id = order_res.get("order_id", f"SCALE_{int(time.time()*1000)}")

        # Deduct funds
        if user_contrib > 0:
            self.active_balances[username] = max(0.0, self.active_balances.get(username, 0.0) - user_contrib)
        if borrowed_amt > 0 and lender_user:
            self.active_balances[lender_user] = max(0.0, self.active_balances.get(lender_user, 0.0) - borrowed_amt)
            if "loans" not in target_pos:
                target_pos["loans"] = []
            target_pos["loans"].append({"lender": lender_user, "amount": borrowed_amt})

        # Update weighted average entry and size
        new_total_qty = curr_qty + add_qty
        new_avg_entry = (old_entry * curr_qty + fill_price * add_qty) / max(0.000001, new_total_qty)
        new_total_margin = curr_margin + total_add_margin

        new_sl_floor = new_avg_entry * (1.0 - (SL_CAP_PCT / 100.0) / leverage) if direction == "LONG" else new_avg_entry * (1.0 + (SL_CAP_PCT / 100.0) / leverage)

        target_pos["entry_price"] = new_avg_entry
        target_pos["allocated_margin_usdt"] = new_total_margin
        target_pos["executed_qty"] = new_total_qty
        target_pos["sl_floor_price"] = new_sl_floor
        target_pos["invo_entry_size"] = new_invo_size
        target_pos["invo_entry_price"] = float(invo_inv.get("entryPrice") or fill_price)

        self.save_state()

        borrow_note = f"\n🤝 <b>Borrowed from @{lender_user}</b>: {fmt_usdt(borrowed_amt)} (Principal repaid on close)" if borrowed_amt > 0 else ""
        msg = (
            f"⚡ <b>BINANCE SCALE-IN (DCA): @{username}</b>\n"
            f"Contract: <b>{pair}</b> (<b>{direction}</b> {int(leverage)}x)\n"
            f"Add-On Margin: <b>+{fmt_usdt(total_add_margin)}</b> ({fmt_inr(total_add_margin)})\n"
            f"Add Price: ${fill_price:,.4f} ➔ New Avg Entry: <b>${new_avg_entry:,.4f}</b>\n"
            f"Total Margin in Trade: <b>{fmt_usdt(new_total_margin)}</b>\n"
            f"New -85% SL Floor: ${new_sl_floor:,.4f}{borrow_note}\n"
            f"Order ID: <code>{order_id}</code>"
        )
        send_telegram(msg)
        print(f"\n[Scale-In Executed] {msg}\n", flush=True)
        self.add_notification(
            title=f"⚡ Scale-In: @{username} {pair} (+{fmt_usdt(total_add_margin)})",
            message=f"Averaged Entry to ${new_avg_entry:,.4f}{f' (Borrowed {fmt_usdt(borrowed_amt)} from @{lender_user})' if borrowed_amt > 0 else ''}",
            level="success"
        )
        return {"success": True, "position": target_pos}

    # --------------------------------------------------------------------------
    # LIVE ORDER EXECUTION: FUTURES EXIT & 30% TAX VAULT SKIM
    # --------------------------------------------------------------------------
    def close_live_trade(self, username: str, ticker: str = None, exit_reason: str = "Market Exit") -> dict:
        pos_list = self.active_positions.get(username, [])
        if not isinstance(pos_list, list):
            pos_list = [pos_list] if isinstance(pos_list, dict) else []
            self.active_positions[username] = pos_list

        if not pos_list:
            return {"error": f"No active position for @{username}"}

        target_pos = None
        if ticker:
            for p in pos_list:
                if p.get("ticker", "").upper() == ticker.upper():
                    target_pos = p
                    break
        if not target_pos:
            target_pos = pos_list[0]

        pair = target_pos["pair"]
        direction = target_pos.get("direction", "LONG")
        leverage = target_pos.get("leverage", 1.0)
        margin_spent = target_pos["allocated_margin_usdt"]
        entry_price = target_pos["entry_price"]
        qty = target_pos["executed_qty"]

        # Close side: SELL to close LONG, BUY to close SHORT
        exit_side = "SELL" if direction == "LONG" else "BUY"
        exit_res = self.bn.place_futures_order(pair, side=exit_side, qty=qty)
        avg_exit = exit_res.get("avg_price") or self.bn.get_ticker_price(pair) or entry_price
        exit_order_id = exit_res.get("order_id", f"FUT_EXIT_{int(time.time()*1000)}")

        # TRUE FUTURES BIDIRECTIONAL PNL FORMULA
        if direction == "LONG":
            raw_return = (avg_exit - entry_price) / entry_price if entry_price > 0 else 0.0
        else: # SHORT (Profits when exit < entry!)
            raw_return = (entry_price - avg_exit) / entry_price if entry_price > 0 else 0.0

        lev_return = max(raw_return * leverage, -0.85)
        gross_pnl_usdt = margin_spent * lev_return
        fee_usdt = margin_spent * leverage * COMMISSION_RATE * 2.0
        net_pnl_usdt = gross_pnl_usdt - fee_usdt

        tax_skim_usdt = 0.0
        if net_pnl_usdt > 0:
            tax_skim_usdt = net_pnl_usdt * TAX_RATE
            self.tax_vault_usdt += tax_skim_usdt
            self.stats[username]["wins"] += 1
            self.stats[username]["tax_usdt"] += tax_skim_usdt
            reinvest_net = net_pnl_usdt * (1.0 - TAX_RATE)
            returned_capital = margin_spent + reinvest_net
            tax_vault_note = f"🛡️ Tax Skim (30%): +{fmt_usdt(tax_skim_usdt)} ({fmt_inr(tax_skim_usdt)}) [Safe Cash Vault]"
        else:
            self.stats[username]["losses"] += 1
            reinvest_net = 0.0
            returned_capital = max(0.0, margin_spent + net_pnl_usdt)
            tax_vault_note = "🛡️ Tax Vault: Untouched (0% Loss Deducted from Vault)"

        # Fleet Peer Loan Repayment (100% priority principal refund to lending peer)
        loans = target_pos.get("loans", [])
        repaid_summary = []
        for loan in loans:
            lender = loan.get("lender")
            l_amt = float(loan.get("amount") or 0.0)
            if lender and l_amt > 0:
                repay_amt = min(l_amt, returned_capital)
                self.active_balances[lender] = self.active_balances.get(lender, 0.0) + repay_amt
                returned_capital = max(0.0, returned_capital - repay_amt)
                repaid_summary.append(f"Refunded {fmt_usdt(repay_amt)} to @{lender}")
                print(f"[Peer Loan Repaid] Refunded {fmt_usdt(repay_amt)} principal back to @{lender}", flush=True)

        self.active_balances[username] = self.active_balances.get(username, 0.0) + returned_capital
        self.stats[username]["trades"] += 1
        self.stats[username]["pnl_usdt"] += net_pnl_usdt
        self.active_positions[username].remove(target_pos)

        pnl_pct = (net_pnl_usdt / margin_spent * 100.0) if margin_spent > 0 else 0.0
        pnl_sign = "+" if net_pnl_usdt >= 0 else ""

        trade_record = {
            "username": username,
            "pair": pair,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": avg_exit,
            "margin_spent": margin_spent,
            "quote_received": margin_spent + net_pnl_usdt,
            "gross_pnl_usdt": gross_pnl_usdt,
            "fee_usdt": fee_usdt,
            "net_pnl_usdt": net_pnl_usdt,
            "roi_pct": round(pnl_pct, 2),
            "tax_skim_usdt": tax_skim_usdt,
            "reinvested_usdt": reinvest_net,
            "exit_reason": exit_reason,
            "entry_order_id": target_pos.get("entry_order_id"),
            "sell_order_id": exit_order_id,
            "tax_vault_after_usdt": self.tax_vault_usdt,
            "trader_balance_after_usdt": self.active_balances[username],
            "portfolio_equity_after_usdt": self.total_portfolio_equity(),
            "entry_ist": target_pos.get("entry_ist", "N/A"),
            "exit_ist": now_ist_str(),
            "time_ist": now_ist_str()
        }
        self.trade_history.append(trade_record)
        self.save_state()

        repay_note = f"\n🤝 <b>Peer Loan Repaid</b>: {', '.join(repaid_summary)}" if repaid_summary else ""
        msg = (
            f"🏁 <b>BINANCE FUTURES EXIT: @{username}</b> | {exit_reason}\n"
            f"Contract: <b>{pair}</b> (<b>{direction}</b> {int(leverage)}x)\n"
            f"Entry: ${entry_price:,.4f} ➔ Exit: ${avg_exit:,.4f}\n"
            f"Net PnL: <b>{pnl_sign}{fmt_usdt(net_pnl_usdt)}</b> ({pnl_sign}{pnl_pct:.1f}%)\n"
            f"{tax_vault_note}{repay_note}\n"
            f"Active Cash (@{username}): <b>{fmt_usdt(self.active_balances[username])}</b>\n"
            f"Total Tax Vault: <b>{fmt_usdt(self.tax_vault_usdt)}</b> ({fmt_inr(self.tax_vault_usdt)})\n"
            f"Total Portfolio Wealth: <b>{fmt_usdt(self.total_portfolio_equity())}</b>"
        )
        send_telegram(msg)
        print(f"\n[Futures Exit] {msg}\n", flush=True)
        notif_level = "success" if net_pnl_usdt > 0 else "danger"
        self.add_notification(
            title=f"🏁 Exit: @{username} {pair} ({exit_reason})",
            message=f"{pnl_sign}{fmt_usdt(net_pnl_usdt)} ({pnl_sign}{pnl_pct:.1f}%) | ${entry_price:,.4f} ➔ ${avg_exit:,.4f}" + (f" | 30% Tax: +{fmt_usdt(tax_skim_usdt)}" if tax_skim_usdt > 0 else ""),
            level=notif_level
        )
        return {"success": True, "record": trade_record}

# --------------------------------------------------------------------------------------
# 5. EXECUTION LOOP & LIVE SIGNAL MONITORING
# --------------------------------------------------------------------------------------
_GLOBAL_ENGINE = None

def handle_shutdown(signum=None, frame=None):
    print("\n[Shutdown] Saving state safely...", flush=True)
    if _GLOBAL_ENGINE:
        _GLOBAL_ENGINE.save_state()
        tot = _GLOBAL_ENGINE.total_portfolio_equity()
        send_telegram(
            f"<b>Invo Binance Engine Offline</b>\n"
            f"Total Wealth: {fmt_usdt(tot)} ({fmt_inr(tot)})\n"
            f"Tax Vault: {fmt_usdt(_GLOBAL_ENGINE.tax_vault_usdt)}"
        )
    if signum is not None:
        sys.exit(0)

def check_wispbyte_countdown(engine):
    """Sends warnings 1hr, 30m, 10m, 5m, 1m before Wispbyte server shuts down."""
    close_epoch = getattr(engine, "wispbyte_close_epoch", 0.0)
    if not close_epoch or close_epoch <= 0:
        return
    rem_sec = close_epoch - time.time()
    rem_min = rem_sec / 60.0

    milestones = [
        (60, "1 Hour", "warning"),
        (30, "30 Minutes", "warning"),
        (10, "10 Minutes", "danger"),
        (5, "5 Minutes", "danger"),
        (1, "1 Minute", "danger")
    ]
    for m, label, lvl in milestones:
        if rem_min <= m and m not in engine.sent_close_warnings:
            engine.sent_close_warnings.add(m)
            title = f"⚠️ Wispbyte Closing in {label}"
            msg = f"Server closes in {label}! Renew or extend server to prevent trading downtime."
            engine.add_notification(title, msg, level=lvl)
            send_telegram(
                f"🚨 <b>Wispbyte Server Countdown Warning!</b>\n"
                f"Time Remaining: <b>{label}</b>\n"
                f"Action Required: Extend or renew Wispbyte server now to prevent position downtime."
            )
            print(f"[Wispbyte Warning] Fired {label} shutdown warning to Web Dashboard & Telegram.", flush=True)
            break

def run_binance_live_daemon():
    global _GLOBAL_ENGINE

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    atexit.register(handle_shutdown)

    print("=" * 85, flush=True)
    print(f"[{now_ist_str()}] INVO POOL 5 LIVE BINANCE TESTNET ENGINE (30% TAX VAULT)", flush=True)
    print("=" * 85, flush=True)

    # Initialize Binance Spot Testnet Client
        # Initialize Binance USDT-M Futures Client (True Bidirectional Long & Short)
    bn = BinanceFuturesClient()
    engine = Pool5LiveBinanceEngine(bn)
    _GLOBAL_ENGINE = engine

    # Check command-line test execution
    if "--test-trade" in sys.argv:
        print("\n[Test Mode] Executing immediate live roundtrip trade on Binance Testnet to verify execution...")
        u = "booobsas"
        ticker = "BTC"
        res_open = engine.open_live_trade(u, ticker, direction="LONG", leverage=1.0)
        if res_open.get("success"):
            print("[Test Mode] Holding position for 5 seconds to simulate trade fill...")
            time.sleep(5.0)
            res_close = engine.close_live_trade(u, exit_reason="Manual Test Fill")
            print("[Test Mode] Trade successfully completed and Tax Vault updated!")
        return

    # Start Micro HTTP Server only if explicitly requested (saves background socket on cloud containers)
    if os.getenv("ENABLE_LOCAL_HTTP", "0") == "1":
        start_micro_http_server(DASHBOARD_PORT)

    # Check balances
    bals = bn.get_account_balances()
    usdt_free = bals.get("USDT", {}).get("free", 0.0)
    print(f"[Account Verified] Available Testnet USDT: {fmt_usdt(usdt_free)}", flush=True)

    # Initialize Invo Signal Client
    invo_client = InvoClient(INVO_REFRESH_TOKEN)
    try:
        invo_client.ensure_token()
        print("[Invo] Authenticated to Invo Signal API.", flush=True)
    except Exception as e:
        print(f"[Invo] Signal API auth note: {e}", flush=True)

    portfolio_state = {}
    tracked_open = {}  # Tracks active Invo positions across polls & restarts for reliable 2-poll close detection
    for t in POOL5_CONFIG["traders"]:
        port_id = t["portfolio_id"]
        username = t["username"]
        raw_invs = invo_client.get_open_investments(port_id) if invo_client else None
        if raw_invs is not None:
            init_map = {p.get("ticker", "").upper(): p for p in raw_invs if isinstance(p, dict) and p.get("ticker")}
            portfolio_state[port_id] = init_map
            engine_tickers = {pos.get("ticker", "").upper() for pos in engine.active_positions.get(username, []) if pos.get("ticker")}
            tracked_open[port_id] = engine_tickers.intersection(init_map.keys())
        else:
            portfolio_state[port_id] = None
            tracked_open[port_id] = set()

    start_msg = (
        f"🌟 <b>Invo Pool5 Live Binance Engine Online</b> | {now_ist_short()}\n"
        f"API: Binance Demo Futures (True 2-Way Long/Short)\n"
        f"Tax Model: <b>Method 1 (Safe 30% Tax Vault Skim)</b>\n"
        f"Available USDT: <b>{fmt_usdt(usdt_free)}</b> ({fmt_inr(usdt_free)})\n"
        f"Tax Vault Cash: <b>{fmt_usdt(engine.tax_vault_usdt)}</b>\n"
        f"Status: Monitoring Invo Signals & Executing Live Fills"
    )
    send_telegram(start_msg)

    missing_counters = {}
    poll_count = 0
    while True:
        try:
            time.sleep(POLL_INTERVAL_SECONDS)
            poll_count += 1
            now_ts = time.time()

            # Check Wispbyte shutdown timer
            check_wispbyte_countdown(engine)

            # 1. Check Active Positions for 4-Hour Time Cut & -85% Stop-Loss Floor
            for u in engine.all_users:
                pos_list = list(engine.active_positions.get(u, []))
                for pos in pos_list:
                    pair = pos["pair"]
                    hold_sec = now_ts - pos["entry_epoch"]

                    # Strict 4-Hour Time Cut across all traders (strictly matches backtest)
                    if hold_sec >= (MAX_HOLD_HOURS * 3600.0):
                        engine.close_live_trade(u, ticker=pos["ticker"], exit_reason="Strict 4H Time Cut")
                        continue

                    # Stop-Loss, Take-Profit & Mark Price Update
                    curr_price = bn.get_ticker_price(pair)
                    if curr_price > 0:
                        pos["mark_price"] = curr_price
                        direction = pos.get("direction", "LONG")
                        lev = float(pos.get("leverage", 1.0))
                        entry_p = float(pos.get("entry_price", curr_price))
                        ret = (curr_price - entry_p) / entry_p if direction == "LONG" else (entry_p - curr_price) / entry_p
                        pos["roi_pct"] = round(ret * lev * 100.0, 2)

                        # A. Check Trader Take Profit (if set by trader)
                        trader_tp = pos.get("trader_tp_price")
                        if trader_tp and trader_tp > 0:
                            tp_hit = (direction == "LONG" and curr_price >= trader_tp) or \
                                     (direction == "SHORT" and curr_price <= trader_tp)
                            if tp_hit:
                                engine.close_live_trade(u, ticker=pos["ticker"], exit_reason="Trader Take Profit")
                                continue

                        # B. Check Trader Stop Loss (if set by trader)
                        trader_sl = pos.get("trader_sl_price")
                        if trader_sl and trader_sl > 0:
                            sl_hit = (direction == "LONG" and curr_price <= trader_sl) or \
                                     (direction == "SHORT" and curr_price >= trader_sl)
                            if sl_hit:
                                engine.close_live_trade(u, ticker=pos["ticker"], exit_reason="Trader Stop Loss")
                                continue

                        # C. Fallback: Default -85% Stop-Loss Floor (ALWAYS active)
                        sl_floor = pos.get("sl_floor_price")
                        if sl_floor and sl_floor > 0:
                            floor_hit = (direction == "LONG" and curr_price <= sl_floor) or \
                                        (direction == "SHORT" and curr_price >= sl_floor)
                            if floor_hit:
                                engine.close_live_trade(u, ticker=pos["ticker"], exit_reason="Native SL Floor (-85%)")
                                continue

            # 2. Poll Invo Portfolios for new trades and trader closes
            if invo_client:
                for target in POOL5_CONFIG["traders"]:
                    port_id = target["portfolio_id"]
                    username = target["username"]
                    time.sleep(0.2)

                    raw_invs = invo_client.get_open_investments(port_id)
                    if raw_invs is None:
                        continue

                    new_map = {p.get("ticker", "").upper(): p for p in raw_invs if isinstance(p, dict) and p.get("ticker")}

                    # If startup fetch failed for this portfolio, initialize safely without triggering stale entries
                    if portfolio_state.get(port_id) is None:
                        portfolio_state[port_id] = new_map
                        engine_tickers = {pos.get("ticker", "").upper() for pos in engine.active_positions.get(username, []) if pos.get("ticker")}
                        tracked_open[port_id] = engine_tickers.intersection(new_map.keys())
                        continue

                    old_map = portfolio_state[port_id]

                    # A. Detect New Trade Entry
                    pos_list = engine.active_positions.get(username, [])
                    u_equity = engine.active_balances.get(username, 0.0) + sum(p.get("allocated_margin_usdt", 0.0) for p in pos_list)
                    max_slots = 2 if u_equity >= 20.0 else 1

                    for ticker, p in new_map.items():
                        # Dynamic Invo Stop-Loss & Take-Profit Sync on Active Positions
                        for pos in engine.active_positions.get(username, []):
                            if pos.get("ticker", "").upper() == ticker:
                                # 1. Check for Scale-in / Size Increase
                                new_entry_size = float(p.get("entrySize") or 0.0)
                                old_entry_size = float(pos.get("invo_entry_size") or 0.0)
                                if old_entry_size > 0 and new_entry_size > (old_entry_size * 1.10):
                                    print(f"[Scale-In Signal] @{username} on {ticker}: size increased from {old_entry_size} -> {new_entry_size}", flush=True)
                                    engine.scale_in_live_trade(username, pos, p)

                                raw_sl = p.get("stopLoss")
                                new_sl = float(raw_sl) if raw_sl and float(raw_sl) > 0 else None
                                if new_sl != pos.get("trader_sl_price"):
                                    pos["trader_sl_price"] = new_sl
                                    act = f"updated to ${new_sl:.4f}" if new_sl else "removed (default -85% floor active)"
                                    print(f"[SL Sync] @{username} {ticker} Stop Loss {act}", flush=True)
                                    engine.add_notification(f"🎯 SL Sync: @{username} {ticker}", f"Stop Loss {act}", level="info")

                                raw_tp = p.get("priceTarget")
                                new_tp = float(raw_tp) if raw_tp and float(raw_tp) > 0 else None
                                if new_tp != pos.get("trader_tp_price"):
                                    pos["trader_tp_price"] = new_tp
                                    act = f"updated to ${new_tp:.4f}" if new_tp else "removed"
                                    print(f"[TP Sync] @{username} {ticker} Take Profit {act}", flush=True)
                                    engine.add_notification(f"🎯 TP Sync: @{username} {ticker}", f"Take Profit {act}", level="info")

                        # A. Detect New Trade Entry
                        if ticker not in old_map and len(engine.active_positions.get(username, [])) < max_slots:
                            # Stale Signal Guard: skip legacy positions opened >15m ago (e.g. after API flicker)
                            created_str = p.get("createdAt")
                            is_fresh = True
                            if created_str:
                                try:
                                    created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                                    if (now_ts - created_dt.timestamp()) > 900.0:
                                        is_fresh = False
                                        print(f"[Stale Signal Guard] Skipped @{username} {ticker}: opened at {created_str}", flush=True)
                                except Exception:
                                    pass
                            if not is_fresh:
                                continue

                            direction = "LONG" if p.get("directionLong") else "SHORT"
                            lev = float(p.get("leverage") or 1.0)
                            raw_sl = p.get("stopLoss")
                            trader_sl = float(raw_sl) if raw_sl and float(raw_sl) > 0 else None
                            raw_tp = p.get("priceTarget")
                            trader_tp = float(raw_tp) if raw_tp and float(raw_tp) > 0 else None

                            res_open = engine.open_live_trade(
                                username,
                                ticker,
                                direction=direction,
                                leverage=lev,
                                trader_sl=trader_sl,
                                trader_tp=trader_tp,
                                invo_entry_size=p.get("entrySize"),
                                invo_entry_price=p.get("entryPrice")
                            )
                            if res_open.get("success"):
                                tracked_open.setdefault(port_id, set()).add(ticker)

                    # B. Detect Trader Close with 2-Poll Debounce Filter
                    # Uses persistent tracked_open set so tickers are NOT lost when portfolio_state updates after Poll 1
                    if port_id not in missing_counters:
                        missing_counters[port_id] = {}

                    for ticker in list(tracked_open.get(port_id, set())):
                        if ticker not in new_map:
                            missing_counters[port_id][ticker] = missing_counters[port_id].get(ticker, 0) + 1
                            if missing_counters[port_id][ticker] >= 2: # Confirmed missing for 2 consecutive polls (~24s)
                                pos_list = engine.active_positions.get(username, [])
                                if any(p.get("ticker", "").upper() == ticker for p in pos_list):
                                    engine.close_live_trade(username, ticker=ticker, exit_reason="Invo Trader Closed")
                                tracked_open[port_id].discard(ticker)
                                missing_counters[port_id].pop(ticker, None)
                        else:
                            missing_counters[port_id][ticker] = 0

                    portfolio_state[port_id] = new_map

            # Heartbeat, live rate refresh & memory cleanup every ~5 minutes
            if poll_count % 30 == 0:
                fetch_live_usdt_inr()
                engine.save_state()
                gc.collect()
                tot = engine.total_portfolio_equity()
                print(f"[{now_ist_str()}] Heartbeat: {poll_count} polls | Total Wealth: {fmt_usdt(tot)} | Tax Vault: {fmt_usdt(engine.tax_vault_usdt)}", flush=True)

        except Exception as e:
            print(f"[{now_ist_str()}] Loop exception: {e}", flush=True)
            time.sleep(2.0)

if __name__ == "__main__":
    run_binance_live_daemon()
