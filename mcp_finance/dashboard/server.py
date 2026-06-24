"""Zero-dependency dashboard server using Python's built-in http.server."""

from __future__ import annotations
import json, os, sys, traceback, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Import handlers ──
from mcp_finance.api import (
    handle_realtime_quote, handle_kline, handle_market_indices,
    handle_sector_ranking, handle_north_flow, handle_batch_quotes,
)
from mcp_finance.screener import handle_stock_screener
from mcp_finance.backtest import handle_backtest
from mcp_finance.analysis import handle_factor_screener
from mcp_finance.data import STOCK_MAPPING, HOT_STOCKS
from mcp_finance.logging_config import get_logger

_logger = get_logger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
CHARTS_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "charts"))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


class DashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # suppress default logging

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, content, status=200):
        body = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath, content_type):
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._send_json({"error": "not found"}, 404)

    def _safe_call(self, handler, args):
        try:
            result = handler(args)
            if isinstance(result, dict):
                return result
            return {"data": result}
        except Exception as e:
            tb = traceback.format_exc()
            _logger.warning("Handler error: %s\n%s", e, tb)
            return {"error": True, "message": str(e)}

    def _parse_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = dict(urllib.parse.parse_qsl(parsed.query))

        try:
            # Pages
            if path == "/" or path == "/index.html":
                return self._send_file(os.path.join(TEMPLATE_DIR, "index.html"), "text/html")
            if path == "/screener":
                return self._send_file(os.path.join(TEMPLATE_DIR, "screener.html"), "text/html")
            if path == "/backtest":
                return self._send_file(os.path.join(TEMPLATE_DIR, "backtest.html"), "text/html")

            # Static files
            if path.startswith("/static/"):
                fname = path[len("/static/"):]
                fp = os.path.join(STATIC_DIR, fname)
                ct = "text/javascript" if fname.endswith(".js") else "text/css" if fname.endswith(".css") else "application/octet-stream"
                return self._send_file(fp, ct)

            if path.startswith("/charts/"):
                fname = path[len("/charts/"):]
                return self._send_file(os.path.join(CHARTS_DIR, fname), "text/html")

            # API endpoints
            code = params.get("code", "600519")
            market = params.get("market", "a")

            if path == "/api/market/indices":
                return self._send_json(self._safe_call(handle_market_indices, {"market": market}))

            if path == "/api/market/sectors":
                stype = params.get("type", "industry")
                top_n = int(params.get("top_n", 15))
                return self._send_json(self._safe_call(handle_sector_ranking, {"sector_type": stype, "top_n": top_n}))

            if path == "/api/market/north_flow":
                days = int(params.get("days", 10))
                return self._send_json(self._safe_call(handle_north_flow, {"days": days}))

            if path == "/api/market/hot_stocks":
                codes = [s["代码"] for s in HOT_STOCKS if s.get("市场") == "A股"]
                return self._send_json(self._safe_call(handle_batch_quotes, {"codes": codes, "market": "a"}))

            if path == "/api/market/hot_stocks_full":
                return self._send_json(HOT_STOCKS)

            if path == "/api/realtime_quote":
                return self._send_json(self._safe_call(handle_realtime_quote, {"code": code, "market": market}))

            if path == "/api/kline":
                limit = int(params.get("limit", 120))
                return self._send_json(self._safe_call(handle_kline, {"code": code, "market": market, "ktype": "daily", "limit": limit, "adjust": "qfq"}))

            if path == "/api/search":
                kw = params.get("keyword", "").lower().strip()
                top_n = int(params.get("top_n", 10))
                matches = []
                for c, n in STOCK_MAPPING.items():
                    if kw in c.lower() or kw in n.lower():
                        matches.append({"code": c, "name": n})
                        if len(matches) >= top_n:
                            break
                return self._send_json(matches)

            # 404
            self._send_json({"error": "not found"}, 404)
        except Exception as e:
            self._send_json({"error": True, "message": str(e)}, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._parse_body()

        try:
            if path == "/api/screener":
                args = {"top_n": int(body.get("top_n", 30))}
                for key in ["min_gain", "max_gain", "min_volume_ratio", "min_turnover",
                             "max_pe", "max_pb", "min_market_cap", "min_roe", "min_pb"]:
                    v = body.get(key)
                    if v is not None and v != "":
                        args[key] = float(v)
                return self._send_json(self._safe_call(handle_stock_screener, args))

            if path == "/api/factor_screener":
                args = {"top_n": int(body.get("top_n", 30)), "min_market_cap": float(body.get("min_market_cap", 50))}
                return self._send_json(self._safe_call(handle_factor_screener, args))

            if path == "/api/backtest":
                args = {
                    "code": body.get("code", "600519"),
                    "strategy": body.get("strategy", "ma_cross"),
                    "start_date": body.get("start_date"),
                    "end_date": body.get("end_date"),
                    "initial_capital": float(body.get("initial_capital", 100000)),
                }
                fp = body.get("fast_period")
                sp = body.get("slow_period")
                if fp: args["fast_period"] = int(fp)
                if sp: args["slow_period"] = int(sp)
                return self._send_json(self._safe_call(handle_backtest, args))

            self._send_json({"error": "not found"}, 404)
        except Exception as e:
            self._send_json({"error": True, "message": str(e)}, 500)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"\n  mcp-finance Dashboard -> http://localhost:{port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
