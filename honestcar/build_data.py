"""
HonestCar (автосервіс, Варшава) — сборка data.json для месячного отчёта.

Отличие от e-com шаблонов: конверсия = лид, денег в кабинете нет.
Ручные поля (клиенты, маржа, закрытия по направлениям) — в manual.json,
билдер их подтягивает и считает производные (ціна клієнта, ROMI и т.д.).

customer_id 3978684249 (honestcar pro / HonestCarService), валюта PLN (zł).
"""
import json
import os
import sys
from datetime import datetime, date, timedelta
from collections import defaultdict

sys.path.insert(0, '/Users/vlad/claude_gads/api mcc')
from google.ads.googleads.client import GoogleAdsClient  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CID = '3978684249'
CLIENT = GoogleAdsClient.load_from_storage('/Users/vlad/claude_gads/api mcc/google-ads.yaml')
GS = CLIENT.get_service('GoogleAdsService')

FIRST_MONTH_DAY = date(2026, 1, 1)
_TODAY = datetime.now().date()
LAST_DAY = _TODAY  # включаємо поточний місяць частково — фіналізується наступною пересборкою

# Конверсии с другого сайта — не показываем в звіті
EXCLUDE_CONV_IDS = {6657394267}  # 'honestcar.pro GA4 (web) Отправка форм Zapisatsja_PL'

# Локальные конверсионные действия (карты, звонки из smart, визиты в СТО)
# дзвінкові дії (Calls from Smart, виклики з карт/оголошень) показуємо разом з
# click_on_phone у блоці сайту — всі дзвінки в одному місці
LOCAL_IDS = {6640719757, 6643534495, 6746953657, 6659996110}

# Направления услуг: имя → slugs всех языковых версий (CONTAINS по URL)
SERVICES = [
    ('Кузов і фарбування',   ['blacharstwo-i-lakiernictwo', 'kuzovnoy-remont', 'kuzovni-roboti-ta-farbuvannya']),
    ('Кондиціонер',          ['klimatyzacja-samochodowa', 'avtomobilnyy-konditsioner', 'avtomobilniy-konditsioner']),
    ('Двигун і турбіни',     ['naprawa-silnika', 'remont-dvigatelya', 'remont-dviguna']),
    ('АКПП і трансмісія',    ['uklad-napedowy-i-skrzynia-biegow', 'transmissiya-i-korobka-peredach', 'prividna-sistema-ta-korobka-peredach']),
    ('Гальма',               ['uklad-hamulcowy', 'tormoznaya-sistema', '/galma']),
    ('Ходова і підвіска',    ['zawieszenie-i-uklad-jezdny', 'podveska-i-khodovaya-chast', 'pidviska-i-khodova-chastina']),
    ('Сервіс і діагностика', ['serwis-i-diagnostyka', 'servis-i-diagnostika']),
    ('Рідини і фільтри',     ['wymiana-plynow-i-filtrow', 'zamena-zhidkostey-i-filtrov', 'zmina-ridin-i-filtriv']),
    ('Кермове управління',   ['uklad-kierowniczy', 'rulevoe-upravlenie', 'rulove-keruvannya']),
    ('Шини і шиномонтаж',    ['opony-i-wulkanizacja', 'shiny-i-shinomontazh', 'shini-ta-shinomontazh']),
    ('Електроніка',          ['elektronika-samochodowa', 'avtomobilnaya-elektronika']),
    ('Евакуатор і допомога', ['pomoc-drogowa-i-laweta', 'dorozhnaya-pomoshch-i-evakuator', 'dorozhnya-dopomoga-ta-evakuator']),
]

MONTH_NAMES = ['Січень', 'Лютий', 'Березень', 'Квітень', 'Травень', 'Червень',
               'Липень', 'Серпень', 'Вересень', 'Жовтень', 'Листопад', 'Грудень']
MONTH_SHORT = ['Січ', 'Лют', 'Бер', 'Кві', 'Тра', 'Чер', 'Лип', 'Сер', 'Вер', 'Жов', 'Лис', 'Гру']


def fmt(d):
    return d.strftime('%Y-%m-%d')


def month_key(mfirst):
    return mfirst[:7]  # '2026-07'


def month_ranges(first_day, last_day):
    out = []
    y, m = first_day.year, first_day.month
    while True:
        start = date(y, m, 1)
        if start > last_day:
            break
        nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        end = min(nxt - timedelta(days=1), last_day)
        out.append((start, end))
        y, m = nxt.year, nxt.month
    return out


def sdiv(a, b):
    return a / b if b else 0


def calc_delta(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100, 2)


# ────── API ──────

def fetch_customer_monthly(a, b):
    q = f"""SELECT segments.month, metrics.cost_micros, metrics.impressions, metrics.clicks,
                   metrics.conversions, metrics.all_conversions
            FROM customer WHERE segments.date BETWEEN '{fmt(a)}' AND '{fmt(b)}'"""
    out = defaultdict(lambda: defaultdict(float))
    for r in GS.search(customer_id=CID, query=q):
        k = month_key(r.segments.month)
        o = out[k]
        o['cost'] += r.metrics.cost_micros / 1e6
        o['imp'] += r.metrics.impressions
        o['clk'] += r.metrics.clicks
        o['conv'] += r.metrics.conversions
        o['conv_all'] += r.metrics.all_conversions
    return out


def fetch_conversions_monthly(a, b):
    # cost_micros нельзя селектить вместе с conversion_action_name (PROHIBITED_SEGMENT_WITH_METRIC)
    q = f"""SELECT segments.month, segments.conversion_action, segments.conversion_action_name,
                   metrics.all_conversions
            FROM customer WHERE segments.date BETWEEN '{fmt(a)}' AND '{fmt(b)}'"""
    out = defaultdict(lambda: defaultdict(float))
    names = {}
    for r in GS.search(customer_id=CID, query=q):
        k = month_key(r.segments.month)
        aid = int(r.segments.conversion_action.split('/')[-1])
        out[k][aid] += r.metrics.all_conversions
        names[aid] = r.segments.conversion_action_name
    return out, names


def fetch_campaigns_monthly(a, b):
    q = f"""SELECT segments.month, campaign.id, campaign.name, campaign.advertising_channel_type,
                   metrics.cost_micros, metrics.impressions, metrics.clicks,
                   metrics.conversions, metrics.all_conversions
            FROM campaign WHERE segments.date BETWEEN '{fmt(a)}' AND '{fmt(b)}'"""
    out = defaultdict(dict)
    for r in GS.search(customer_id=CID, query=q):
        k = month_key(r.segments.month)
        cid = r.campaign.id
        o = out[k].setdefault(cid, {'name': r.campaign.name,
                                    'type': r.campaign.advertising_channel_type.name,
                                    'cost': 0, 'imp': 0, 'clk': 0, 'conv': 0, 'conv_all': 0})
        o['cost'] += r.metrics.cost_micros / 1e6
        o['imp'] += r.metrics.impressions
        o['clk'] += r.metrics.clicks
        o['conv'] += r.metrics.conversions
        o['conv_all'] += r.metrics.all_conversions
    return out


def fetch_ad_groups_monthly(a, b):
    q = f"""SELECT segments.month, campaign.id, ad_group.id, ad_group.name,
                   metrics.cost_micros, metrics.impressions, metrics.clicks,
                   metrics.conversions, metrics.all_conversions
            FROM ad_group WHERE segments.date BETWEEN '{fmt(a)}' AND '{fmt(b)}'"""
    out = defaultdict(lambda: defaultdict(dict))
    for r in GS.search(customer_id=CID, query=q):
        k = month_key(r.segments.month)
        cid = r.campaign.id
        gid = r.ad_group.id
        o = out[k][cid].setdefault(gid, {'name': r.ad_group.name,
                                         'cost': 0, 'imp': 0, 'clk': 0, 'conv': 0, 'conv_all': 0})
        o['cost'] += r.metrics.cost_micros / 1e6
        o['imp'] += r.metrics.impressions
        o['clk'] += r.metrics.clicks
        o['conv'] += r.metrics.conversions
        o['conv_all'] += r.metrics.all_conversions
    return out


def fetch_landing_monthly(a, b):
    # campaign.id обязателен в SELECT для landing_page_view
    q = f"""SELECT segments.month, campaign.id, landing_page_view.unexpanded_final_url,
                   metrics.cost_micros, metrics.clicks, metrics.conversions
            FROM landing_page_view WHERE segments.date BETWEEN '{fmt(a)}' AND '{fmt(b)}'"""
    out = defaultdict(lambda: defaultdict(lambda: {'cost': 0, 'clk': 0, 'conv': 0}))
    for r in GS.search(customer_id=CID, query=q):
        k = month_key(r.segments.month)
        u = r.landing_page_view.unexpanded_final_url or ''
        o = out[k][u]
        o['cost'] += r.metrics.cost_micros / 1e6
        o['clk'] += r.metrics.clicks
        o['conv'] += r.metrics.conversions
    return out


def classify_url(url):
    u = url.lower()
    if 'vip.honestcar' in u:
        return 'VIP-лендінги'
    if 'google.com/maps' in u:
        return 'Google Maps'
    for name, slugs in SERVICES:
        if any(s in u for s in slugs):
            return name
    return 'Не розподілено'


# ────── manual.json ──────

def load_manual(month_keys):
    path = os.path.join(HERE, 'manual.json')
    manual = {'_readme': ('Ручні дані. months: clients = закриті клієнти за місяць, margin = маржа (zł). '
                          'services: список записів {week, service, closed, revenue} — з тижневих скрінів клієнта; '
                          'service має збігатися з назвою напрямку у звіті.'),
              'months': {}, 'services': {}}
    if os.path.exists(path):
        with open(path) as f:
            manual.update(json.load(f))
    changed = False
    for mk in month_keys:
        if mk not in manual['months']:
            manual['months'][mk] = {'clients': None, 'margin': None}
            changed = True
        if mk not in manual['services']:
            manual['services'][mk] = []
            changed = True
    if changed or not os.path.exists(path):
        with open(path, 'w') as f:
            json.dump(manual, f, ensure_ascii=False, indent=2)
    return manual


# ────── сборка месяца ──────

def derive_all(tot, man):
    cost, clk, imp = tot['cost'], tot['clk'], tot['imp']
    conv, conv_all = tot['conv'], tot['conv_all']
    clients = man.get('clients')
    margin = man.get('margin')
    return {
        'cost': cost, 'imp': imp, 'clk': clk,
        'cpc': sdiv(cost, clk), 'ctr': sdiv(clk, imp) * 100,
        'clients': clients,
        'client_price': (sdiv(cost, clients) if clients else None),
        'conv_all': conv_all, 'cpa_all': sdiv(cost, conv_all),
        'conv': conv, 'cpa': sdiv(cost, conv),
        'site_cr': sdiv(conv, clk) * 100,
        'margin': margin,
        'margin_per_client': (sdiv(margin, clients) if (margin is not None and clients) else None),
        'client_cr': (sdiv(clients, conv) * 100 if (clients is not None and conv) else None),
        'romi': (sdiv(margin - cost, cost) * 100 if (margin is not None and cost) else None),
    }


def kpi_rows(c, p):
    """KPI-карточки верхнего дашборда."""
    def card(key, label, unit='', inverted=False, manual=False, integer=False):
        cv = c[key]
        pv = p[key] if p else None
        rnd = (lambda v: int(round(v))) if integer else (lambda v: round(v, 2))
        return {'key': key, 'label': label,
                'value': rnd(cv) if cv is not None else None,
                'prev': rnd(pv) if pv is not None else None,
                'delta_pct': calc_delta(cv, pv),
                'unit': unit, 'manual': manual,
                'delta_inverted': inverted}
    return [
        card('cost', 'Бюджет', 'zł', inverted=True),
        card('clients', 'Всього клієнтів', '', manual=True, integer=True),
        card('client_price', 'Ціна клієнта', 'zł', inverted=True, manual=True),
        card('margin', 'Маржа', 'zł', manual=True),
        card('margin_per_client', 'Сер. чек', 'zł', manual=True),
        card('client_cr', 'Конверсія в клієнта', '%', manual=True),
        card('romi', 'ROMI', '%', manual=True),
        card('cpc', 'CPC', 'zł', inverted=True),
    ]


def head_rows(cur, prev, man_cur, man_prev):
    """Блок 1: строки (name, current, previous, unit, manual, delta_inverted)."""
    c = derive_all(cur, man_cur)
    p = derive_all(prev, man_prev) if prev is not None else None

    def row(name, key, unit='', manual=False, inverted=False, integer=False):
        cv = c[key]
        pv = p[key] if p else None
        rnd = (lambda v: int(round(v))) if integer else (lambda v: round(v, 2))
        return {'name': name,
                'current': rnd(cv) if cv is not None else None,
                'previous': rnd(pv) if pv is not None else None,
                'unit': unit, 'manual': manual,
                **({'delta_inverted': True} if inverted else {})}

    return [
        row('Бюджет', 'cost', 'zł', inverted=True),
        row('Покази', 'imp', '', integer=True),
        row('Кліки', 'clk', '', integer=True),
        row('CPC', 'cpc', 'zł', inverted=True),
        row('CTR', 'ctr', '%'),
        row('Клієнтів', 'clients', '', manual=True, integer=True),
        row('Ціна клієнта', 'client_price', 'zł', manual=True, inverted=True),
        row('Конверсії (усі)', 'conv_all', '', integer=True),
        row('Ціна конверсії (усі)', 'cpa_all', 'zł', inverted=True),
        row('Конверсії (основні)', 'conv', '', integer=True),
        row('Ціна конверсії (основні)', 'cpa', 'zł', inverted=True),
        row('Конверсія сайту', 'site_cr', '%'),
        row('Маржа', 'margin', 'zł', manual=True),
        row('Маржа 1 клієнта (сер. чек)', 'margin_per_client', 'zł', manual=True),
        row('Конверсія в клієнта', 'client_cr', '%', manual=True),
        row('ROMI', 'romi', '%', manual=True),
    ]


def conv_rows(cur_map, prev_map, names):
    ids = set(cur_map) | set(prev_map or {})
    web, local = [], []
    for aid in ids:
        if aid in EXCLUDE_CONV_IDS:
            continue
        cv = round(cur_map.get(aid, 0), 1)
        pv = round((prev_map or {}).get(aid, 0), 1)
        if cv == 0 and pv == 0:
            continue
        row = {'id': aid, 'name': names.get(aid, str(aid)), 'current': cv, 'previous': pv}
        (local if aid in LOCAL_IDS else web).append(row)
    web.sort(key=lambda r: -r['current'])
    local.sort(key=lambda r: -r['current'])
    return {'web': web, 'local': local}


def camp_entry(b, pb):
    return {
        'spend': round(b['cost'], 2), 'prev_spend': round(pb['cost'], 2) if pb else None,
        'imp': int(b['imp']), 'clk': int(b['clk']),
        'ctr': round(sdiv(b['clk'], b['imp']) * 100, 2),
        'cpc': round(sdiv(b['cost'], b['clk']), 2),
        'conv': round(b['conv'], 1), 'prev_conv': round(pb['conv'], 1) if pb else None,
        'conv_all': round(b['conv_all'], 1),
        'cpa': round(sdiv(b['cost'], b['conv']), 2),
        'prev_cpa': round(sdiv(pb['cost'], pb['conv']), 2) if pb else None,
    }


def build_campaigns(cur, prev, groups_cur, groups_prev):
    out = []
    for cid, b in cur.items():
        if b['cost'] <= 0 and b['imp'] <= 0:
            continue
        pb = (prev or {}).get(cid)
        e = {'name': b['name'], 'type': b['type'].replace('PERFORMANCE_MAX', 'PMax').replace('SEARCH', 'Search'),
             **camp_entry(b, pb), 'groups': []}
        gcur = (groups_cur or {}).get(cid, {})
        gprev = (groups_prev or {}).get(cid, {})
        for gid, g in sorted(gcur.items(), key=lambda kv: -kv[1]['cost']):
            if g['cost'] <= 0 and g['imp'] <= 0:
                continue
            e['groups'].append({'name': g['name'], **camp_entry(g, gprev.get(gid))})
        out.append(e)
    out.sort(key=lambda x: -x['spend'])
    return out


def build_services(landing_cur, manual_entries):
    spend = defaultdict(lambda: {'spend': 0.0, 'clicks': 0, 'conv': 0.0})
    for url, o in (landing_cur or {}).items():
        k = classify_url(url)
        if k == 'Google Maps':
            continue  # живе в блоці локальних конверсій, у послугах не дублюємо
        s = spend[k]
        s['spend'] += o['cost']; s['clicks'] += o['clk']; s['conv'] += o['conv']

    has_manual = bool(manual_entries)
    closed = defaultdict(lambda: {'closed': 0, 'revenue': 0.0})
    for rec in manual_entries or []:
        c = closed[rec.get('service', '?')]
        c['closed'] += rec.get('closed', 0) or 0
        c['revenue'] += rec.get('revenue', 0) or 0

    service_order = [n for n, _ in SERVICES] + ['VIP-лендінги', 'Не розподілено']
    all_names = [n for n in service_order if n in spend or n in closed]
    all_names += [n for n in closed if n not in service_order]

    rows = []
    for n in all_names:
        sp = spend.get(n, {'spend': 0, 'clicks': 0, 'conv': 0})
        cl = closed.get(n, {'closed': 0, 'revenue': 0})
        has_spend = sp['spend'] > 0
        has_close = cl['closed'] > 0
        if not has_spend and not has_close:
            continue
        flag = None
        if has_manual and n != 'Не розподілено':
            if has_spend and not has_close:
                flag = 'no_close'
            elif has_close and not has_spend:
                flag = 'no_spend'
        rows.append({
            'name': n,
            'spend': round(sp['spend'], 2), 'clicks': int(sp['clicks']), 'conv': round(sp['conv'], 1),
            'closed': cl['closed'], 'revenue': round(cl['revenue'], 2),
            'avg_check': round(sdiv(cl['revenue'], cl['closed']), 2) if cl['closed'] else None,
            'romi': (round(sdiv(cl['revenue'] - sp['spend'], sp['spend']) * 100, 1) if has_spend and cl['revenue'] else None),
            'flag': flag,
        })
    rows.sort(key=lambda r: -r['spend'])
    return rows


def main():
    months = month_ranges(FIRST_MONTH_DAY, LAST_DAY)
    if not months:
        print('Немає завершених місяців'); return
    full_a, full_b = months[0][0], months[-1][1]
    print(f'Fetching {full_a}..{full_b} ({len(months)} months)...')

    cust = fetch_customer_monthly(full_a, full_b)
    convs, conv_names = fetch_conversions_monthly(full_a, full_b)
    camps = fetch_campaigns_monthly(full_a, full_b)
    groups = fetch_ad_groups_monthly(full_a, full_b)
    landing = fetch_landing_monthly(full_a, full_b)
    print(f'  customer months: {len(cust)}, conv actions: {len(conv_names)}')

    month_keys = [a.strftime('%Y-%m') for a, _ in months]
    manual = load_manual(month_keys)

    monthly = []
    for i, (a, b) in enumerate(months):
        mk = a.strftime('%Y-%m')
        pk = months[i - 1][0].strftime('%Y-%m') if i > 0 else None
        cur_tot = cust.get(mk, defaultdict(float))
        prev_tot = cust.get(pk, defaultdict(float)) if pk else None
        man_cur = manual['months'].get(mk, {})
        man_prev = manual['months'].get(pk, {}) if pk else {}

        monthly.append({
            'label': f'{MONTH_NAMES[a.month - 1]} {a.year}',
            'month': mk,
            'period': {
                'current': {'from': fmt(a), 'to': fmt(b)},
                'previous': ({'from': fmt(months[i-1][0]), 'to': fmt(months[i-1][1])} if i > 0 else None),
            },
            'kpi': kpi_rows(derive_all(cur_tot, man_cur),
                            derive_all(prev_tot, man_prev) if prev_tot is not None else None),
            'head': head_rows(cur_tot, prev_tot, man_cur, man_prev),
            'conversions': conv_rows(convs.get(mk, {}), convs.get(pk, {}) if pk else None, conv_names),
            'campaigns': build_campaigns(camps.get(mk, {}), camps.get(pk, {}) if pk else None,
                                         groups.get(mk, {}), groups.get(pk, {}) if pk else None),
            'services': build_services(landing.get(mk, {}), manual['services'].get(mk, [])),
        })

    # тренд по всем месяцам
    trend = {'labels': [], 'budget': [], 'clients': [], 'romi': []}
    for (a, _), entry in zip(months, monthly):
        trend['labels'].append(f'{MONTH_SHORT[a.month - 1]} {str(a.year)[2:]}')
        h = {r['name']: r for r in entry['head']}
        trend['budget'].append(h['Бюджет']['current'])
        trend['clients'].append(h['Клієнтів']['current'])
        trend['romi'].append(h['ROMI']['current'])

    out = {
        'client': {'name': 'HonestCar', 'logo': 'logo-honestcar.png'},
        'agency': {'name': 'Bohatyrov Marketing'},
        'currency': 'zł',
        'updated_at': datetime.now().isoformat() + 'Z',
        'source': 'google_ads_api + manual.json',
        'monthly': monthly,
        'trend': trend,
    }
    path = os.path.join(HERE, 'data.json')
    with open(path, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    lm = monthly[-1]
    h = {r['name']: r for r in lm['head']}
    print(f'OK: {len(monthly)} months → data.json')
    print(f'Last ({lm["label"]}): budget={h["Бюджет"]["current"]} zł, clicks={h["Кліки"]["current"]}, '
          f'conv={h["Конверсії (основні)"]["current"]}, campaigns={len(lm["campaigns"])}, '
          f'services={len(lm["services"])}, web conv rows={len(lm["conversions"]["web"])}, '
          f'local rows={len(lm["conversions"]["local"])}')


if __name__ == '__main__':
    main()
