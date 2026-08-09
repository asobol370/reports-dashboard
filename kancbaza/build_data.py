"""
Kancbaza — сборка data.json (схема идентична Minelly + поле channels).

Источники:
1. Horoshop API  — успешные заказы (статусы 2=Узгоджено, 6=Доставляється, 3=Виконано)
2. Google Ads API — customer_id 7320619864
3. Meta Ads CSV  — файлы в папке meta/ (выгрузка из Ads Manager, диапазон дат = период)

KPI (первый экран) — Horoshop: Виручка / Замовлень / Ср.чек / ДРР
KPI secondary — реклама: Витрати / Покупки з реклами / Blended ROAS / Вартість замовлення
"""
import csv
import glob
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, date, timedelta

sys.path.insert(0, '/Users/vlad/claude_gads/api mcc')
from google.ads.googleads.client import GoogleAdsClient  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

GOOGLE_CID = '7320619864'
HOROSHOP_DOMAIN = 'kancbaza.com.ua'
HOROSHOP_CREDS = '/Users/vlad/claude_gads/api mcc/horoshop_kancbaza.txt'
SUCCESS_STATUSES = {2, 3, 6}
FIRST_MONDAY = date(2026, 7, 6)
FIRST_MONTH_DAY = date(2026, 7, 1)
EXCLUDE_GOOGLE_CAMPAIGNS = set()

_TODAY = datetime.now().date()
LAST_SUNDAY = _TODAY - timedelta(days=(_TODAY.weekday() + 1) % 7)
if _TODAY.weekday() == 6:
    LAST_SUNDAY = _TODAY
LAST_MONTH_END = _TODAY.replace(day=1) - timedelta(days=1)


def fmt(d): return d.strftime('%Y-%m-%d')
def sdiv(a, b): return a / b if b else 0


def weekly_ranges(a, b):
    out, d = [], a
    while d <= b:
        out.append((d, min(d + timedelta(days=6), b)))
        d += timedelta(days=7)
    return out


def monthly_ranges(a, b):
    out = []
    y, m = a.year, a.month
    while True:
        nm = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        s, e = max(a, date(y, m, 1)), min(b, nm - timedelta(days=1))
        if s > b:
            break
        out.append((s, e))
        y, m = nm.year, nm.month
    return out


# ─── Horoshop ───

def horoshop_token():
    login, password = open(HOROSHOP_CREDS).read().strip().split(':', 1)
    req = urllib.request.Request(
        f'https://{HOROSHOP_DOMAIN}/api/auth/',
        data=json.dumps({'login': login, 'password': password}).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())['response']['token']


def horoshop_daily(token, date_from, date_to):
    daily = defaultdict(lambda: {'orders': 0, 'revenue': 0.0, 'total': 0})
    offset = 0
    while True:
        req = urllib.request.Request(
            f'https://{HOROSHOP_DOMAIN}/api/orders/get/',
            data=json.dumps({'token': token, 'from': fmt(date_from), 'to': fmt(date_to),
                             'limit': 1000, 'offset': offset}).encode(),
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as r:
            batch = json.loads(r.read()).get('response', {}).get('orders', [])
        for o in batch:
            d = o['stat_created'][:10]
            daily[d]['total'] += 1
            if int(o['stat_status']) in SUCCESS_STATUSES:
                daily[d]['orders'] += 1
                daily[d]['revenue'] += float(o['total_sum'])
        if len(batch) < 1000:
            break
        offset += 1000
    return daily


# ─── Google ───

def google_daily(date_from, date_to):
    client = GoogleAdsClient.load_from_storage('/Users/vlad/claude_gads/api mcc/google-ads.yaml')
    gs = client.get_service('GoogleAdsService')
    q = f"""
      SELECT segments.date, campaign.id, campaign.name, campaign.advertising_channel_type,
             metrics.cost_micros, metrics.impressions, metrics.clicks,
             metrics.conversions, metrics.conversions_value
      FROM campaign
      WHERE segments.date BETWEEN '{fmt(date_from)}' AND '{fmt(date_to)}'
    """
    out = {}
    for r in gs.search(customer_id=GOOGLE_CID, query=q):
        if r.campaign.id in EXCLUDE_GOOGLE_CAMPAIGNS:
            continue
        m = r.metrics
        out[(r.segments.date, r.campaign.id)] = {
            'name': r.campaign.name,
            'channel_type': r.campaign.advertising_channel_type.name,
            'spend': m.cost_micros / 1e6, 'impressions': m.impressions, 'clicks': m.clicks,
            'purchases': m.conversions, 'revenue': m.conversions_value,
        }
    return out


# ─── Meta CSV ───

def mnum(s):
    if s is None or str(s).strip() in ('', '--', '—'):
        return 0.0
    return float(str(s).replace(',', '.').replace(' ', '').replace(' ', ''))


def meta_rows_all():
    rows = []
    for path in sorted(glob.glob(os.path.join(HERE, 'meta', '*.csv'))):
        with open(path, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                name = (row.get('Название кампании') or '').strip()
                if not name:
                    continue
                rows.append({
                    'from': row.get('Дата начала отчетности', '').strip(),
                    'to': row.get('Окончание отчетности', '').strip(),
                    'campaign': name,
                    'spend': mnum(row.get('Потраченная сумма (UAH)')),
                    'purchases': mnum(row.get('Покупки')),
                    'revenue': mnum(row.get('Ценность конверсий покупки')),
                    'clicks': mnum(row.get('Клики по ссылке')),
                    'impressions': mnum(row.get('Показы')),
                    'atc': mnum(row.get('Добавления в корзину')),
                })
    return rows


def meta_for(meta_rows, a, b):
    hits = [r for r in meta_rows if r['from'] == fmt(a) and r['to'] == fmt(b)]
    return hits or None


# ─── агрегация одного периода ───

def days_of(a, b):
    out, d = [], a
    while d <= b:
        out.append(fmt(d))
        d += timedelta(days=1)
    return out


def agg_period(shop_d, g_daily, meta_rows, a, b):
    """Возвращает сырые агрегаты периода."""
    days = days_of(a, b)
    shop_orders = sum(shop_d.get(dd, {}).get('orders', 0) for dd in days)
    shop_revenue = sum(shop_d.get(dd, {}).get('revenue', 0) for dd in days)
    shop_total = sum(shop_d.get(dd, {}).get('total', 0) for dd in days)

    g = {'spend': 0, 'purchases': 0, 'revenue': 0, 'clicks': 0, 'impressions': 0}
    g_camp = defaultdict(lambda: {'spend': 0, 'purchases': 0, 'revenue': 0, 'clicks': 0, 'impressions': 0, 'channel_type': ''})
    for (dd, cid), row in g_daily.items():
        if dd in days:
            for k in ('spend', 'purchases', 'revenue', 'clicks', 'impressions'):
                g[k] += row[k]
                g_camp[row['name']][k] += row[k]
            g_camp[row['name']]['channel_type'] = row['channel_type']

    meta_hits = meta_for(meta_rows, a, b)
    m = {'spend': 0, 'purchases': 0, 'revenue': 0, 'clicks': 0, 'impressions': 0}
    m_camp = {}
    has_meta = meta_hits is not None
    if has_meta:
        for r in meta_hits:
            for k in ('spend', 'purchases', 'revenue', 'clicks', 'impressions'):
                m[k] += r[k]
            m_camp[r['campaign']] = r

    ad_spend = g['spend'] + m['spend']
    ad_purchases = g['purchases'] + m['purchases']
    ad_revenue = g['revenue'] + m['revenue']

    return {
        'a': a, 'b': b, 'days': days,
        'shop_orders': shop_orders, 'shop_revenue': shop_revenue,
        'shop_total': shop_total,
        'avg_check': sdiv(shop_revenue, shop_orders),
        'dropoff': (1 - sdiv(shop_orders, shop_total)) * 100 if shop_total else 0,
        'drr': sdiv(ad_spend, shop_revenue) * 100,
        'ad_spend': ad_spend, 'ad_purchases': ad_purchases, 'ad_revenue': ad_revenue,
        'blended_roas': sdiv(shop_revenue, ad_spend) * 100,
        'cpo': sdiv(ad_spend, shop_orders),
        'g': g, 'm': m, 'has_meta': has_meta,
        'g_camp': dict(g_camp), 'm_camp': m_camp,
    }


CTYPE = {'SEARCH': 'Search', 'PERFORMANCE_MAX': 'PMax', 'DEMAND_GEN': 'Demand Gen',
         'DISPLAY': 'Display', 'SHOPPING': 'Shopping', 'VIDEO': 'Video'}


def calc_delta(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100, 2)


def build_period(cur, prev, shop_d, g_daily):
    """Minelly-схема + channels."""
    a, b, days = cur['a'], cur['b'], cur['days']

    def kpi(key, label, cur_v, prev_v, unit, inverted=False, integer=False):
        return {
            'key': key, 'label': label,
            'value': int(round(cur_v)) if integer else round(cur_v, 2),
            'unit': unit,
            'delta_pct': calc_delta(cur_v, prev_v) if prev else None,
            'prev': (int(round(prev_v)) if integer else round(prev_v, 2)) if prev else 0,
            'delta_inverted': inverted,
        }

    p = prev or {}
    kpi_main = [
        kpi('shop_revenue', 'Виручка (Horoshop)', cur['shop_revenue'], p.get('shop_revenue'), 'грн'),
        kpi('shop_orders',  'Успішних замовлень', cur['shop_orders'],  p.get('shop_orders'),  '', integer=True),
        kpi('avg_check',    'Ср. чек',            cur['avg_check'],    p.get('avg_check'),    'грн'),
        kpi('dropoff',      '% відвалів',         cur['dropoff'],      p.get('dropoff'),      '%', inverted=True),
    ]
    kpi_sec = [
        kpi('ad_spend',     'Витрати на рекламу', cur['ad_spend'],     p.get('ad_spend'),     'грн', inverted=True),
        kpi('all_orders',   'Усі замовлення',     cur['shop_total'],   p.get('shop_total'),   '', integer=True),
        kpi('blended_roas', 'Blended ROAS',       cur['blended_roas'], p.get('blended_roas'), '%'),
        kpi('cpo',          'Вартість замовлення', cur['cpo'],         p.get('cpo'),          'грн', inverted=True),
    ]

    # chart: daily внутри периода. Meta daily неизвестна → размазываем ровно по дням.
    n = len(days)
    meta_spend_pd = cur['m']['spend'] / n if n else 0
    meta_purch_pd = cur['m']['purchases'] / n if n else 0

    def g_day(dd, key):
        return sum(r[key] for (d2, _), r in g_daily.items() if d2 == dd)

    sr = [round(shop_d.get(dd, {}).get('revenue', 0), 2) for dd in days]
    so = [shop_d.get(dd, {}).get('orders', 0) for dd in days]
    st = [shop_d.get(dd, {}).get('total', 0) for dd in days]
    ads = [round(g_day(dd, 'spend') + meta_spend_pd, 2) for dd in days]

    chart = {
        'labels': [dd[8:10] + '.' + dd[5:7] for dd in days],
        'series': {
            'shop_revenue': sr,
            'shop_orders':  so,
            'avg_check':    [round(sdiv(sr[i], so[i]), 2) for i in range(n)],
            'dropoff':      [round((1 - sdiv(so[i], st[i])) * 100, 2) if st[i] else 0 for i in range(n)],
            'ad_spend':     ads,
            'all_orders':   st,
            'blended_roas': [round(sdiv(sr[i], ads[i]) * 100, 2) for i in range(n)],
            'cpo':          [round(sdiv(ads[i], so[i]), 2) for i in range(n)],
        },
    }

    def mrow(name, cur_v, prev_v, unit, inverted=False):
        return {'name': name, 'current': round(cur_v, 2), 'previous': round(prev_v, 2) if prev else 0,
                'unit': unit, **({'delta_inverted': True} if inverted else {})}

    metrics = [
        mrow('Усі замовлення',       cur['shop_total'],   p.get('shop_total', 0), ''),
        mrow('Успішних замовлень',   cur['shop_orders'],  p.get('shop_orders', 0), ''),
        mrow('Виручка (Horoshop)',   cur['shop_revenue'], p.get('shop_revenue', 0), 'грн'),
        mrow('Ср. чек',              cur['avg_check'],    p.get('avg_check', 0), 'грн'),
        mrow('% відвалів',           cur['dropoff'],      p.get('dropoff', 0), '%', True),
        mrow('ДРР',                  cur['drr'],          p.get('drr', 0), '%', True),
        mrow('Витрати Google Ads',   cur['g']['spend'],   (p.get('g') or {}).get('spend', 0), 'грн', True),
        mrow('Витрати Meta Ads',     cur['m']['spend'],   (p.get('m') or {}).get('spend', 0), 'грн', True),
        mrow('Виручка за кабінетами', cur['ad_revenue'],  p.get('ad_revenue', 0), 'грн'),
        mrow('Кліки (реклама)',      cur['g']['clicks'] + cur['m']['clicks'],
             ((p.get('g') or {}).get('clicks', 0) + (p.get('m') or {}).get('clicks', 0)), ''),
        mrow('Покази (реклама)',     cur['g']['impressions'] + cur['m']['impressions'],
             ((p.get('g') or {}).get('impressions', 0) + (p.get('m') or {}).get('impressions', 0)), ''),
    ]

    # campaigns — Minelly формат + ch
    campaigns = []

    def camp_details(c, pc):
        """14 рядков как в Minelly (без IS — добавим позже), current vs previous."""
        pc = pc or {}
        def d(nm, ck, unit, inverted=False, pct_of=None):
            cv = c.get(ck, 0); pv = pc.get(ck, 0)
            return {'name': nm, 'current': round(cv, 2), 'previous': round(pv, 2),
                    'unit': unit, **({'delta_inverted': True} if inverted else {})}
        cpa_c = sdiv(c['spend'], c['purchases']); cpa_p = sdiv(pc.get('spend', 0), pc.get('purchases', 0)) if pc else 0
        avg_c = sdiv(c['revenue'], c['purchases']); avg_p = sdiv(pc.get('revenue', 0), pc.get('purchases', 0)) if pc else 0
        cr_c = sdiv(c['purchases'], c['clicks']) * 100; cr_p = sdiv(pc.get('purchases', 0), pc.get('clicks', 0)) * 100 if pc else 0
        roas_c = sdiv(c['revenue'], c['spend']) * 100; roas_p = sdiv(pc.get('revenue', 0), pc.get('spend', 0)) * 100 if pc else 0
        cpc_c = sdiv(c['spend'], c['clicks']); cpc_p = sdiv(pc.get('spend', 0), pc.get('clicks', 0)) if pc else 0
        ctr_c = sdiv(c['clicks'], c['impressions']) * 100; ctr_p = sdiv(pc.get('clicks', 0), pc.get('impressions', 0)) * 100 if pc else 0
        return [
            d('Витрати', 'spend', 'грн', True),
            {'name': 'Покупок', 'current': int(round(c['purchases'])), 'previous': int(round(pc.get('purchases', 0))), 'unit': ''},
            {'name': 'Вартість покупки', 'current': round(cpa_c, 2), 'previous': round(cpa_p, 2), 'unit': 'грн', 'delta_inverted': True},
            {'name': 'Ср.чек', 'current': round(avg_c, 2), 'previous': round(avg_p, 2), 'unit': 'грн'},
            d('Виручка', 'revenue', 'грн'),
            {'name': 'Кф. конверсії', 'current': round(cr_c, 2), 'previous': round(cr_p, 2), 'unit': '%'},
            {'name': 'ROAS', 'current': round(roas_c, 2), 'previous': round(roas_p, 2), 'unit': '%'},
            d('Покази', 'impressions', ''),
            d('Кліки', 'clicks', ''),
            {'name': 'CPC', 'current': round(cpc_c, 2), 'previous': round(cpc_p, 2), 'unit': 'грн', 'delta_inverted': True},
            {'name': 'CTR', 'current': round(ctr_c, 2), 'previous': round(ctr_p, 2), 'unit': '%'},
        ]

    prev_g_camp = (prev or {}).get('g_camp', {})
    prev_m_camp = (prev or {}).get('m_camp', {})

    for name, c in cur['g_camp'].items():
        if c['spend'] <= 0 and c['revenue'] <= 0:
            continue
        pc = prev_g_camp.get(name)
        roas = sdiv(c['revenue'], c['spend']) * 100
        proas = sdiv(pc['revenue'], pc['spend']) * 100 if pc and pc['spend'] else None
        campaigns.append({
            'ch': 'google', 'name': name, 'type': CTYPE.get(c['channel_type'], 'Search'),
            'summary': {
                'spend': round(c['spend'], 2), 'revenue': round(c['revenue'], 2),
                'roas': round(roas, 2), 'conversions': int(round(c['purchases'])),
                'delta_roas': calc_delta(roas, proas) or 0,
                'cpa': round(sdiv(c['spend'], c['purchases']), 2),
            },
            'details': camp_details(c, pc),
        })
    for name, c in cur['m_camp'].items():
        if c['spend'] <= 0 and c['revenue'] <= 0:
            continue
        pc = prev_m_camp.get(name)
        roas = sdiv(c['revenue'], c['spend']) * 100
        proas = sdiv(pc['revenue'], pc['spend']) * 100 if pc and pc['spend'] else None
        campaigns.append({
            'ch': 'meta', 'name': name, 'type': 'Meta',
            'summary': {
                'spend': round(c['spend'], 2), 'revenue': round(c['revenue'], 2),
                'roas': round(roas, 2), 'conversions': int(round(c['purchases'])),
                'delta_roas': calc_delta(roas, proas) or 0,
                'cpa': round(sdiv(c['spend'], c['purchases']), 2),
            },
            'details': camp_details(c, pc),
        })
    campaigns.sort(key=lambda x: -x['summary']['spend'])

    channels = {
        'google': {k: round(v, 2) for k, v in cur['g'].items()},
        'meta': ({k: round(v, 2) for k, v in cur['m'].items()} if cur['has_meta'] else None),
    }

    return {
        'label': f'{a.strftime("%d.%m")}-{b.strftime("%d.%m.%Y")}',
        'period': {
            'current': {'from': fmt(a), 'to': fmt(b)},
            'previous': ({'from': fmt(prev['a']), 'to': fmt(prev['b'])} if prev else None),
        },
        'kpi': kpi_main,
        'kpi_secondary': kpi_sec,
        'chart': chart,
        'metrics': metrics,
        'channels': channels,
        'campaigns': campaigns,
    }


def main():
    print('Auth Horoshop...')
    token = horoshop_token()
    full_from = min(FIRST_MONDAY, FIRST_MONTH_DAY)
    full_to = max(LAST_SUNDAY, LAST_MONTH_END)

    print(f'Horoshop orders {full_from}..{full_to}...')
    shop_d = horoshop_daily(token, full_from, full_to)
    print(f'  {sum(v["orders"] for v in shop_d.values())} successful orders')

    print('Google Ads...')
    g_daily = google_daily(full_from, full_to)
    print(f'  {len(g_daily)} rows')

    meta_rows = meta_rows_all()
    print(f'Meta CSV rows: {len(meta_rows)}')

    def build_all(ranges):
        aggs = [agg_period(shop_d, g_daily, meta_rows, a, b) for a, b in ranges]
        out = []
        for i, cur in enumerate(aggs):
            out.append(build_period(cur, aggs[i - 1] if i > 0 else None, shop_d, g_daily))
        return out

    weekly = build_all(weekly_ranges(FIRST_MONDAY, LAST_SUNDAY))
    monthly = build_all(monthly_ranges(FIRST_MONTH_DAY, LAST_MONTH_END))

    out = {
        'client': {'name': 'Kancbaza', 'logo': 'logo-kancbaza.png'},
        'agency': {'name': 'Bohatyrov Marketing'},
        'updated_at': datetime.now().isoformat() + 'Z',
        'source': 'horoshop_api + google_ads_api + meta_csv',
        'weekly': weekly,
        'monthly': monthly,
    }
    path = os.path.join(HERE, 'data.json')
    json.dump(out, open(path, 'w'), ensure_ascii=False, indent=2, allow_nan=False)
    lw = weekly[-1]
    print(f'\nOK → {path}')
    print(f'Weeks: {len(weekly)}, months: {len(monthly)}')
    print(f"Last week {lw['label']}: {lw['kpi'][1]['value']} orders, {lw['kpi'][0]['value']:.0f} грн, "
          f"ДРР {lw['kpi'][3]['value']}%, campaigns {len(lw['campaigns'])}, meta={'YES' if lw['channels']['meta'] else 'no'}")


if __name__ == '__main__':
    main()
