from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json
import time
import os
import functools

# 台灣證券交易所（TWSE）官方 OpenAPI 根目錄
BASE = 'https://openapi.twse.com.tw/v1'
ENDPOINTS = {
    'valuation': f'{BASE}/exchangeReport/BWIBBU_ALL',      # 官方估值（本益比、股價淨值比、殖利率）
    'revenue': f'{BASE}/opendata/t187ap05_L',              # 官方每月營收（含 YoY 年增率、MoM 月增率）
    'quotes': f'{BASE}/exchangeReport/STOCK_DAY_ALL',        # 官方每日收盤價、成交張數、漲跌
    'companies': f'{BASE}/opendata/t187ap03_L',            # 官方公司基本資料（股本）
    'pnl': f'{BASE}/opendata/t187ap06_L_ci',               # 官方上市公司綜合損益表（每股盈餘 EPS、稅後淨利）
}

DIR_PATH = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(DIR_PATH, 'stocks_cache.json')
_cache_data = None
_cache_warnings = []
_cache_time = 0
CACHE_TTL = 900  # 快取 15 分鐘

def get_json(url, retries=2, timeout=18):
    for i in range(retries):
        try:
            req = Request(url, headers={'User-Agent': 'TaiwanStockScreener/1.4', 'Accept': 'application/json'})
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
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {name: pool.submit(get_json, ENDPOINTS[name]) for name in ('revenue', 'quotes', 'companies', 'pnl')}
            for name, future in futures.items():
                try:
                    data[name] = future.result(timeout=22)
                except Exception as e:
                    data[name] = []
                    warnings.append(name)

        revs = {str(x.get('公司代號', '')).strip(): x for x in data['revenue']}
        quotes_map = {str(x.get('Code', '')).strip(): x for x in data['quotes']}
        shares = {str(x.get('公司代號', '')).strip(): number(x.get('已發行普通股數或TDR原股發行股數')) for x in data['companies']}
        pnls = {str(x.get('公司代號', '')).strip(): x for x in data.get('pnl', [])}

        rows = []
        for item in valuation:
            code = str(item.get('Code', '')).strip()
            q = quotes_map.get(code, {})
            r = revs.get(code, {})
            p = pnls.get(code, {})

            price = number(q.get('ClosingPrice'))
            raw_vol = number(q.get('TradeVolume'))
            change = number(q.get('Change'))
            revenue = number(r.get('營業收入-當月營收'))
            yoy = number(r.get('營業收入-去年同月增減(%)'))
            cum_yoy = number(r.get('累計營業收入-前期比較增減(%)'))
            industry = r.get('產業別', '')

            raw_eps = p.get('基本每股盈餘（元）')
            eps = number(raw_eps)
            net_income = number(p.get('本期淨利（淨損）'))
            quarter_str = f"{p.get('年度', '')}Q{p.get('季別', '')}" if p.get('年度') else None

            issued = shares.get(code)
            annual_sales = revenue * 1000 * 12 if revenue and revenue > 0 else None
            market_cap = price * issued if price is not None and issued is not None else None
            pe, pb = number(item.get('PEratio')), number(item.get('PBratio'))

            # 轉機判定邏輯：
            # 1. 虧損判定：季報 EPS < 0，或本益比 PE 為空（無獲利無法計算本益比）
            # 2. 轉機潛力：虧損但最新月營收 YoY >= +10%（營收擴張有轉盈潛力）
            is_loss = (eps is not None and eps < 0) or (eps is None and pe is None)
            if is_loss:
                if yoy is not None and yoy >= 10:
                    profit_status = 'turnaround'  # 潛力轉虧為盈（黃色）
                else:
                    profit_status = 'loss'        # 實質虧損（紅色）
            else:
                profit_status = 'profitable'      # 獲利公司（正常/綠色）

            rows.append({
                **item,
                'Price': price,
                'Volume': round(raw_vol / 1000, 1) if raw_vol is not None else None,
                'Change': change,
                'PSR': round(market_cap / annual_sales, 2) if market_cap is not None and annual_sales else None,
                'GrahamIndex': round(pe * pb, 2) if pe is not None and pb is not None and pe >= 0 and pb >= 0 else None,
                'EPS': eps,
                'YoY': yoy,
                'CumYoY': cum_yoy,
                'Industry': industry,
                'Quarter': quarter_str,
                'ProfitStatus': profit_status,
            })

        _cache_data = rows
        _cache_warnings = warnings
        _cache_time = now
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({'data': rows, 'warnings': warnings, 'time': now}, f, ensure_ascii=False)
        except Exception:
            pass
        return rows, warnings
    except Exception as exc:
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
                body = json.dumps({'error': f'證交所估值與財報資料暫時無法載入：{exc}'}, ensure_ascii=False).encode('utf-8')
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
