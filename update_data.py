import os
import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

BASE = 'https://openapi.twse.com.tw/v1'
ENDPOINTS = {
    'valuation': f'{BASE}/exchangeReport/BWIBBU_ALL',
    'revenue': f'{BASE}/opendata/t187ap05_L',
    'quotes': f'{BASE}/exchangeReport/STOCK_DAY_ALL',
    'companies': f'{BASE}/opendata/t187ap03_L',
}

def get_json(url, retries=3, timeout=20):
    for i in range(retries):
        try:
            req = Request(url, headers={'User-Agent': 'TaiwanStockScreener/1.3', 'Accept': 'application/json'})
            with urlopen(req, timeout=timeout) as response:
                return json.loads(response.read())
        except Exception as e:
            if i == retries - 1:
                raise e
            time.sleep(2)

def number(value):
    try:
        result = float(str(value).replace(',', '').strip())
        return result if result == result and abs(result) != float('inf') else None
    except (TypeError, ValueError):
        return None

def update():
    print('Fetching data from TWSE OpenAPI...')
    valuation = get_json(ENDPOINTS['valuation'])
    data = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {name: pool.submit(get_json, ENDPOINTS[name]) for name in ('revenue', 'quotes', 'companies')}
        for name, future in futures.items():
            try:
                data[name] = future.result(timeout=25)
            except Exception as e:
                print(f'Warning: failed to load {name}: {e}')
                data[name] = []

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

    dir_path = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(dir_path, 'data')
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, 'stocks.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False)
    print(f'Successfully updated {len(rows)} stocks to {out_file}')

if __name__ == '__main__':
    update()
