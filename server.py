from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json
import time
import os
import functools

BASE = 'https://openapi.twse.com.tw/v1'
ENDPOINTS = {
    'valuation': f'{BASE}/exchangeReport/BWIBBU_ALL',
    'revenue': f'{BASE}/opendata/t187ap05_L',
    'quotes': f'{BASE}/exchangeReport/STOCK_DAY_ALL',
    'companies': f'{BASE}/opendata/t187ap03_L',
}

DIR_PATH = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(DIR_PATH, 'stocks_cache.json')
_cache_data = None
_cache_warnings = []
_cache_time = 0
CACHE_TTL = 900

def get_json(url, retries=2, timeout=18):
    for i in range(retries):
        try:
            req = Request(url, headers={'User-Agent': 'TaiwanStockScreener/1.2', 'Accept': 'application/json'})
            with urlopen(req, timeout=timeout) as response:
                return json.loads(response.read())
        except Exception as e:
            if i == retries - 1:
                raise e
            time.sleep(1)

def number(value):
    try:
        result = float(str(value).replace(',', '').strip())
        return result if result == result and abs(result) != float('inf') else None
    except (TypeError, ValueError):
        return None

def build_rows(force=False):
    global _cache_data, _cache_warnings, _cache_time
    now = time.time()
    if not force and _cache_data is not None and (now - _cache_time < CACHE_TTL):
        return _cache_data, _cache_warnings

    try:
        valuation = get_json(ENDPOINTS['valuation'])
        data = {}
        warnings = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {name: pool.submit(get_json, ENDPOINTS[name]) for name in ('revenue', 'quotes', 'companies')}
            for name, future in futures.items():
                try:
                    data[name] = future.result(timeout=20)
                except Exception:
                    data[name] = []
                    warnings.append(name)
        revs = {str(x.get('公司代號', '')).strip(): x for x in data['revenue']}
        quotes_map = {str(x.get('Code', '')).strip(): x for x in data['quotes']}
        shares = {str(x.get('公司代號', '')).strip(): number(x.get('已發行普通股數或TDR原股發行股數')) for x in data['companies']}
        rows = []
        for item in valuation:
            code = str(item.get('Code', '')).strip()
            q = quotes_map.get(code, {})
            price = number(q.get('ClosingPrice'))
            raw_vol = number(q.get('TradeVolume'))
            change = number(q.get('Change'))
            revenue = number(revs.get(code, {}).get('營業收入-當月營收'))
            issued = shares.get(code)
            annual_sales = revenue * 1000 * 12 if revenue and revenue > 0 else None
            market_cap = price * issued if price is not None and issued is not None else None
            pe, pb = number(item.get('PEratio')), number(item.get('PBratio'))
            rows.append({
                **item,
                'Price': price,
                'Volume': round(raw_vol / 1000, 1) if raw_vol is not None else None,
                'Change': change,
                'PSR': round(market_cap / annual_sales, 2) if market_cap is not None and annual_sales else None,
                'GrahamIndex': round(pe * pb, 2) if pe is not None and pb is not None and pe >= 0 and pb >= 0 else None
            })
        _cache_data = rows
        _cache_warnings = warnings
        _cache_time = now
        # Save to disk as durable fallback
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({'data': rows, 'warnings': warnings, 'time': now}, f, ensure_ascii=False)
        except Exception:
            pass
        return rows, warnings
    except Exception as exc:
        # Fallback to disk cache if available
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    _cache_data = cached['data']
                    _cache_warnings = cached.get('warnings', []) + ['使用本機快取資料']
                    _cache_time = cached.get('time', now)
                    return _cache_data, _cache_warnings
            except Exception:
                pass
        raise exc

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path_only = self.path.split('?', 1)[0]
        if path_only in ('/', ''):
            self.send_response(302)
            self.send_header('Location', '/tw-stock-screener.html')
            self.end_headers()
            return
        if path_only == '/api/stocks':
            try:
                force = 'force=1' in self.path
                rows, warnings = build_rows(force=force)
                body = json.dumps(rows, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                if warnings:
                    self.send_header('X-Data-Warnings', ','.join(warnings))
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                body = json.dumps({'error': f'證交所估值資料暫時無法載入：{exc}'}, ensure_ascii=False).encode('utf-8')
                self.send_response(502)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        super().do_GET()
    def log_message(self, fmt, *args):
        print('%s - %s' % (self.log_date_time_string(), fmt % args))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8765))
    print(f'台股篩選器已啟動：http://0.0.0.0:{port}/tw-stock-screener.html')
    handler = functools.partial(Handler, directory=DIR_PATH)
    ThreadingHTTPServer(('0.0.0.0', port), handler).serve_forever()
