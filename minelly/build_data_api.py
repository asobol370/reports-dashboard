"""
Собирает data.json для Minelly-дашборда НАПРЯМУЮ из Google Ads API.
Все weekly + monthly периоды перезапрашиваются каждый раз — учитывает атрибуцию,
подтянутую за прошедшие 10-15 дней.

customer_id 1392573958 (minelly.com.ua)
Purchase conversion_action: "Purchase (google ads)" (id 7568983397)
Add to cart action: "Minelly (web) add_to_cart" (all_conversions)
"""
import json
import sys
from datetime import datetime, date, timedelta
from collections import defaultdict

sys.path.insert(0, '/Users/vlad/claude_gads/api mcc')
from google.ads.googleads.client import GoogleAdsClient  # noqa: E402

CID = '1392573958'
CLIENT = GoogleAdsClient.load_from_storage('/Users/vlad/claude_gads/api mcc/google-ads.yaml')
GS = CLIENT.get_service('GoogleAdsService')

# Клиентские настройки
FIRST_MONDAY = date(2026, 4, 6)  # первая неделя запуска

def _last_sunday(today):
    return today - timedelta(days=(today.weekday() + 1) % 7)

def _last_finished_month_end(today):
    return today.replace(day=1) - timedelta(days=1)

_TODAY = datetime.now().date()
LAST_SUNDAY_END = _last_sunday(_TODAY)          # weekly — до последней завершённой ВС
LAST_MONTH_END = _last_finished_month_end(_TODAY)  # monthly — только завершённые месяцы

# Ключевые конверсії клиента = все primary+included actions в кабинете
# (сейчас активны: "Purchase (google ads)" + "Generate_lead (google ads)").
# metrics.conversions без сегментации агрегирует их автоматически — не нужно перечислять.
ATC_ACTION = 'Minelly (web) add_to_cart'
EXCLUDE_CAMPAIGN_IDS = {23168314448}  # 'Lisskins' — не относится к Minelly

# ────── период-функции ──────

def weekly_ranges(first_mon, last_sun):
    """Список (mon, sun) для всех полных недель."""
    out = []
    d = first_mon
    while d <= last_sun:
        out.append((d, min(d + timedelta(days=6), last_sun)))
        d += timedelta(days=7)
    return out


def monthly_ranges(first_day, last_day):
    """Список (start, end) для календарных месяцев (первый может быть неполный)."""
    out = []
    y, m = first_day.year, first_day.month
    while True:
        # last day of month
        if m == 12:
            next_m_first = date(y + 1, 1, 1)
        else:
            next_m_first = date(y, m + 1, 1)
        month_end = next_m_first - timedelta(days=1)
        start = max(first_day, date(y, m, 1))
        end = min(last_day, month_end)
        if start > last_day:
            break
        out.append((start, end))
        y, m = next_m_first.year, next_m_first.month
    return out


def fmt(d):
    return d.strftime('%Y-%m-%d')


def label_weekly(a, b):
    return f'{a.strftime("%d.%m")}-{b.strftime("%d.%m.%Y")}'


def label_monthly(a, b):
    return f'{a.strftime("%d.%m")}-{b.strftime("%d.%m.%Y")}'


# ────── API запросы ──────

def fetch_metrics(date_from, date_to):
    """Возвращает {(campaign_id, date_str): {cost, imp, clk, purchases, revenue, is, top_is, first_is, name, channel}}.
    purchases/revenue = metrics.conversions/value (без сегментации) = Purchase + Lead."""
    query = f"""
      SELECT segments.date, campaign.id, campaign.name, campaign.advertising_channel_type,
             metrics.cost_micros, metrics.impressions, metrics.clicks,
             metrics.conversions, metrics.conversions_value,
             metrics.search_impression_share, metrics.search_top_impression_share,
             metrics.search_absolute_top_impression_share
      FROM campaign
      WHERE segments.date BETWEEN '{fmt(date_from)}' AND '{fmt(date_to)}'
    """
    out = {}
    for r in GS.search(customer_id=CID, query=query):
        cid = r.campaign.id
        if cid in EXCLUDE_CAMPAIGN_IDS:
            continue
        d = r.segments.date
        m = r.metrics
        out[(cid, d)] = {
            'name': r.campaign.name,
            'channel': r.campaign.advertising_channel_type.name,
            'cost': m.cost_micros / 1e6,
            'imp': m.impressions,
            'clk': m.clicks,
            'purchases': m.conversions,          # = Purchase + Generate_lead (primary+incl)
            'revenue':   m.conversions_value,
            'is': m.search_impression_share if m.search_impression_share else 0,
            'top_is': m.search_top_impression_share if m.search_top_impression_share else 0,
            'first_is': m.search_absolute_top_impression_share if m.search_absolute_top_impression_share else 0,
        }
    return out


def fetch_add_to_carts(date_from, date_to):
    """{(campaign_id, date_str): all_conversions_atc} — только для Add to Cart action."""
    query = f"""
      SELECT segments.date, campaign.id, segments.conversion_action_name, metrics.all_conversions
      FROM campaign
      WHERE segments.date BETWEEN '{fmt(date_from)}' AND '{fmt(date_to)}'
        AND segments.conversion_action_name = '{ATC_ACTION}'
    """
    out = {}
    for r in GS.search(customer_id=CID, query=query):
        cid = r.campaign.id
        if cid in EXCLUDE_CAMPAIGN_IDS:
            continue
        d = r.segments.date
        out[(cid, d)] = r.metrics.all_conversions
    return out


# ────── агрегация ──────

def agg_period(metrics_daily, atc_daily, campaign_ids, date_from, date_to):
    """Возвращает {'overall': {...}, 'by_camp': {cid: {...}}}."""
    def in_range(d_str):
        d = date.fromisoformat(d_str)
        return date_from <= d <= date_to

    def _empty():
        return {'name': None, 'channel': None, 'cost': 0, 'imp': 0, 'clk': 0,
                'is_num': 0, 'top_num': 0, 'first_num': 0, 'is_den': 0,
                'purchases': 0, 'revenue': 0, 'atc': 0}

    by_camp = {cid: _empty() for cid in campaign_ids}

    for (cid, d), row in metrics_daily.items():
        if not in_range(d): continue
        if cid not in by_camp: by_camp[cid] = _empty()
        b = by_camp[cid]
        b['name'] = row['name']; b['channel'] = row['channel']
        b['cost'] += row['cost']; b['imp'] += row['imp']; b['clk'] += row['clk']
        b['purchases'] += row['purchases']
        b['revenue']   += row['revenue']
        # IS weighted by impressions
        if row['imp'] > 0 and row['is']:
            b['is_num']    += row['is']       * row['imp']
            b['top_num']   += row['top_is']   * row['imp']
            b['first_num'] += row['first_is'] * row['imp']
            b['is_den']    += row['imp']

    for (cid, d), atc_val in atc_daily.items():
        if not in_range(d): continue
        if cid not in by_camp: continue
        by_camp[cid]['atc'] += atc_val

    # финализируем IS в проценты
    for cid, b in by_camp.items():
        b['is']    = (b['is_num']    / b['is_den'] * 100) if b['is_den'] > 0 else 0
        b['top']   = (b['top_num']   / b['is_den'] * 100) if b['is_den'] > 0 else 0
        b['first'] = (b['first_num'] / b['is_den'] * 100) if b['is_den'] > 0 else 0

    # overall — сумма
    overall = {'cost': 0, 'imp': 0, 'clk': 0, 'purchases': 0, 'revenue': 0, 'atc': 0}
    for b in by_camp.values():
        for k in overall: overall[k] += b[k]

    # производные
    def derive(o):
        o['ctr'] = (o['clk'] / o['imp'] * 100) if o['imp'] > 0 else 0
        o['cpc'] = (o['cost'] / o['clk']) if o['clk'] > 0 else 0
        o['cpa'] = (o['cost'] / o['purchases']) if o['purchases'] > 0 else 0
        o['avg_check'] = (o['revenue'] / o['purchases']) if o['purchases'] > 0 else 0
        o['cr_pur'] = (o['purchases'] / o['clk'] * 100) if o['clk'] > 0 else 0
        o['roas'] = (o['revenue'] / o['cost'] * 100) if o['cost'] > 0 else 0
        o['cr_atc'] = (o['atc'] / o['clk'] * 100) if o['clk'] > 0 else 0
        o['cost_atc'] = (o['cost'] / o['atc']) if o['atc'] > 0 else 0
    derive(overall)
    for b in by_camp.values(): derive(b)

    return {'overall': overall, 'by_camp': by_camp}


# ────── билд периодов ──────

def calc_delta(cur, prev, inverted=False):
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100, 2)


def daily_chart(metrics_d, atc_d, date_from, date_to):
    """Возвращает {labels, series} с daily-точками внутри периода [date_from, date_to]."""
    days = []
    d = date_from
    while d <= date_to:
        days.append(d)
        d += timedelta(days=1)

    per_day = {fmt(day): {'cost': 0, 'imp': 0, 'clk': 0, 'purchases': 0, 'revenue': 0, 'atc': 0}
               for day in days}

    for (cid, dstr), row in metrics_d.items():
        if dstr in per_day:
            per_day[dstr]['cost']      += row['cost']
            per_day[dstr]['imp']       += row['imp']
            per_day[dstr]['clk']       += row['clk']
            per_day[dstr]['purchases'] += row['purchases']
            per_day[dstr]['revenue']   += row['revenue']
    for (cid, dstr), atc in atc_d.items():
        if dstr in per_day:
            per_day[dstr]['atc'] += atc

    for stats in per_day.values():
        stats['ctr']       = (stats['clk'] / stats['imp'] * 100)    if stats['imp'] > 0 else 0
        stats['cpc']       = (stats['cost'] / stats['clk'])         if stats['clk'] > 0 else 0
        stats['cpa']       = (stats['cost'] / stats['purchases'])   if stats['purchases'] > 0 else 0
        stats['avg_check'] = (stats['revenue'] / stats['purchases']) if stats['purchases'] > 0 else 0
        stats['cr_pur']    = (stats['purchases'] / stats['clk'] * 100) if stats['clk'] > 0 else 0
        stats['roas']      = (stats['revenue'] / stats['cost'] * 100)  if stats['cost'] > 0 else 0

    labels = [day.strftime('%d.%m') for day in days]
    keys_map = [
        ('revenue', 'revenue'), ('spend', 'cost'), ('roas', 'roas'),
        ('purchases', 'purchases'), ('cpa', 'cpa'), ('avg_check', 'avg_check'),
        ('cr_purchase', 'cr_pur'), ('cpc', 'cpc'),
    ]
    series = {}
    for out_key, o_key in keys_map:
        series[out_key] = [round(per_day[fmt(day)][o_key], 2) for day in days]
    return {'labels': labels, 'series': series}


CTYPE = {
    'SEARCH':          'Search',
    'PERFORMANCE_MAX': 'PMax',
    'DEMAND_GEN':      'Demand Gen',
    'DISPLAY':         'Display',
    'SHOPPING':        'Shopping',
    'VIDEO':           'Video',
}


def build_period(agg_cur, agg_prev, label, date_from, date_to, prev_range, all_labels):
    o = agg_cur['overall']
    p = agg_prev['overall'] if agg_prev else None

    def kpi(key_cur, key_prev, label_t, unit, inverted=False):
        cur = o.get(key_cur, 0)
        prv = p.get(key_prev if key_prev else key_cur, 0) if p else None
        return {
            'key': key_cur, 'label': label_t,
            'value': round(cur, 2), 'unit': unit,
            'delta_pct': calc_delta(cur, prv, inverted),
            'prev': round(prv, 2) if prv is not None else 0,
            'delta_inverted': inverted,
        }

    # KPI key naming — для дашборда: revenue, spend, roas, purchases, cpa, avg_check, cr_purchase, cpc
    def kpi_r(key_dash, o_key, label_t, unit, inverted=False):
        cur = o.get(o_key, 0)
        prv = p.get(o_key, 0) if p else None
        return {
            'key': key_dash, 'label': label_t,
            'value': round(cur, 2), 'unit': unit,
            'delta_pct': calc_delta(cur, prv, inverted),
            'prev': round(prv, 2) if prv is not None else 0,
            'delta_inverted': inverted,
        }

    # для purchases округляем до целого
    purchases_kpi = kpi_r('purchases', 'purchases', 'Покупок', '')
    purchases_kpi['value'] = int(round(purchases_kpi['value']))
    purchases_kpi['prev']  = int(round(purchases_kpi['prev']))
    kpi_main = [
        kpi_r('revenue',   'revenue',   'Виручка',            'грн'),
        kpi_r('spend',     'cost',      'Витрати',            'грн', True),
        kpi_r('roas',      'roas',      'ROAS',               '%'),
        purchases_kpi,
    ]
    kpi_sec = [
        kpi_r('cpa',         'cpa',       'CPA (ціна покупки)', 'грн', True),
        kpi_r('avg_check',   'avg_check', 'Ср. чек',            'грн'),
        kpi_r('cr_purchase', 'cr_pur',    'Кф. конверсії',      '%'),
        kpi_r('cpc',         'cpc',       'CPC (ціна кліку)',   'грн', True),
    ]

    def m(name, o_key, unit, inverted=False):
        return {
            'name': name,
            'current': round(o.get(o_key, 0), 2),
            'previous': round(p.get(o_key, 0), 2) if p else 0,
            'unit': unit,
            **({'delta_inverted': True} if inverted else {})
        }

    metrics = [
        m('Вартість покупки',  'cpa',        'грн', True),
        m('Ср. чек',           'avg_check',  'грн'),
        m('Кф. конверсії',     'cr_pur',     '%'),
        m('Покази',            'imp',        ''),
        m('Кліки',             'clk',        ''),
        m('CPC',               'cpc',        'грн', True),
        m('CTR',               'ctr',        '%'),
        m('Додавання в кошик', 'atc',        ''),
        m('CR → Add to cart',  'cr_atc',     '%'),
        m('Ціна дод. в кошик', 'cost_atc',   'грн', True),
    ]

    # chart series — заполнится позже, пока пустышка
    chart = {'labels': [], 'series': {k: [] for k in ['revenue', 'spend', 'roas', 'purchases', 'cpa', 'avg_check', 'cr_purchase', 'cpc']}}

    # campaigns
    camps = []
    for cid, b in agg_cur['by_camp'].items():
        if b['cost'] <= 0 and b['revenue'] <= 0:
            continue
        pb = agg_prev['by_camp'].get(cid) if agg_prev else None
        ctype = CTYPE.get(b['channel'], 'Search')

        def cd(nm, o_key, unit, inverted=False):
            cur = b.get(o_key, 0)
            prv = pb.get(o_key, 0) if pb else 0
            return {
                'name': nm, 'current': round(cur, 2), 'previous': round(prv, 2),
                'unit': unit,
                **({'delta_inverted': True} if inverted else {})
            }

        details = [
            cd('Витрати',           'cost',      'грн', True),
            cd('Покупок',           'purchases', ''),
            cd('Вартість покупки',  'cpa',       'грн', True),
            cd('Ср.чек',            'avg_check', 'грн'),
            cd('Виручка',           'revenue',   'грн'),
            cd('Кф. конверсії',     'cr_pur',    '%'),
            cd('ROAS',              'roas',      '%'),
            cd('Покази',            'imp',       ''),
            cd('Кліки',             'clk',       ''),
            cd('CPC',               'cpc',       'грн', True),
            cd('CTR',               'ctr',       '%'),
            cd('Impression Share',        'is',    '%'),
            cd('Показів у верхній ч.',    'top',   '%'),
            cd('Показів на 1-й поз.',     'first', '%'),
        ]

        delta_roas = calc_delta(b['roas'], pb['roas'] if pb else None) or 0
        camps.append({
            'name': b['name'], 'type': ctype,
            'summary': {
                'spend':       round(b['cost'], 2),
                'revenue':     round(b['revenue'], 2),
                'roas':        round(b['roas'], 2),
                'conversions': int(round(b['purchases'])),
                'delta_roas':  delta_roas,
                'cpa':         round(b['cpa'], 2),
            },
            'details': details,
        })
    camps.sort(key=lambda x: -x['summary']['spend'])

    return {
        'label': label,
        'period': {
            'current': {'from': fmt(date_from), 'to': fmt(date_to)},
            'previous': {'from': fmt(prev_range[0]), 'to': fmt(prev_range[1])} if prev_range else None,
        },
        'kpi': kpi_main,
        'kpi_secondary': kpi_sec,
        'chart': chart,
        'metrics': metrics,
        'campaigns': camps,
    }


def add_chart_history(periods):
    """Заполняет chart серии историей всех периодов до текущего."""
    all_labels_short = [p['label'].split('-')[0] for p in periods]
    # значения по каждому overall
    key_to_o = {
        'revenue': 'revenue', 'spend': 'cost', 'roas': 'roas', 'purchases': 'purchases',
        'cpa': 'cpa', 'avg_check': 'avg_check', 'cr_purchase': 'cr_pur', 'cpc': 'cpc',
    }
    # достанем overall из каждого периода — но у нас в period нет объекта overall уже. Надо пересобрать из kpi.
    # проще — получить agg_by_idx отдельно. Но agg_by_idx мы уже используем при построении периодов.
    # Значит передаём отдельно.
    pass  # реализовано выше через передачу agg-cache


# ────── main ──────

def main():
    weeks = weekly_ranges(FIRST_MONDAY, LAST_SUNDAY_END)
    months = monthly_ranges(FIRST_MONDAY, LAST_MONTH_END)

    # тянем ВСЕ данные за весь период однократно
    full_from = FIRST_MONDAY
    full_to = max(LAST_SUNDAY_END, LAST_MONTH_END)
    print(f'Fetching metrics {full_from}..{full_to} ...')
    metrics_d = fetch_metrics(full_from, full_to)
    print(f'  {len(metrics_d)} (campaign, day) rows')
    print(f'Fetching add-to-carts ...')
    atc_d = fetch_add_to_carts(full_from, full_to)
    print(f'  {len(atc_d)} (campaign, day) atc rows')

    all_campaign_ids = {cid for (cid, _) in metrics_d}
    print(f'Campaigns: {len(all_campaign_ids)}')

    # аггрегируем по каждой неделе/месяцу
    weekly_agg = [agg_period(metrics_d, atc_d, all_campaign_ids, a, b) for a, b in weeks]
    monthly_agg = [agg_period(metrics_d, atc_d, all_campaign_ids, a, b) for a, b in months]

    def build_all(ranges, aggs, label_fn):
        result = []
        for i, ((a, b), agg) in enumerate(zip(ranges, aggs)):
            prev_agg = aggs[i - 1] if i > 0 else None
            prev_range = ranges[i - 1] if i > 0 else None
            p = build_period(agg, prev_agg, label_fn(a, b), a, b, prev_range, None)
            # daily chart внутри самого периода (Google Ads style)
            p['chart'] = daily_chart(metrics_d, atc_d, a, b)
            result.append(p)
        return result

    weekly_out = build_all(weeks, weekly_agg, label_weekly)
    monthly_out = build_all(months, monthly_agg, label_monthly)

    out = {
        'client': {'name': 'Minelly Coffee', 'logo': 'logo-minelly.png'},
        'agency': {'name': 'Bohatyrov Marketing'},
        'updated_at': datetime.now().isoformat() + 'Z',
        'source': 'google_ads_api',
        'weekly': weekly_out,
        'monthly': monthly_out,
    }
    path = '/Users/vlad/claude_gads/reports-dashboard/minelly/data.json'
    with open(path, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'OK: {len(weekly_out)} weeks, {len(monthly_out)} months → {path}')
    lw = weekly_out[-1]
    print(f'Latest week ({lw["label"]}): revenue={lw["kpi"][0]["value"]} spend={lw["kpi"][1]["value"]} '
          f'roas={lw["kpi"][2]["value"]:.1f}% purchases={lw["kpi"][3]["value"]} campaigns={len(lw["campaigns"])}')


if __name__ == '__main__':
    main()
