# Готовий prompt для Claude

Скопіюй ВЕСЬ текст нижче (від `----- START -----` до `----- END -----`) в діалог з Claude.
Прикріпи файли CSV з Google Ads.

---

----- START -----

Мені треба згенерувати `data.json` для веб-дашборду Google Ads звіту.

## ⚠️ КРИТИЧНО: використай Python / analysis tool

**Не читай CSV очима — тільки через `analysis tool` (Python / pandas).** Причини:
- Google Ads UI експортує числа в форматі `1 234,56 грн` (nbsp тисячі + кома decimal + суфікс) — очима легко пропустити.
- Тисячі рядків daily-даних неможливо звірити вручну без помилок.
- Треба точно підсумувати по тижнях/місяцях, а не оцінити «на око».

**Workflow:**
1. Прочитай кожен прикріплений CSV через `pandas.read_csv()` (або `csv` модуль). Правильно парси числа з `грн.`, nbsp, комами.
2. Виведи мені **проміжні суми** по кожному тижню/місяцю: `spend`, `revenue`, `purchases`, `clicks`, `impressions`. Я звірю з CSV візуально — і скажу «ok» перед тим як ти згенеруєш фінальний JSON.
3. Тільки після мого «ok» — сформуй фінальний `data.json` за схемою нижче.

Якщо в чаті немає analysis tool (напр. мобільна версія Claude) — попередь мене і зупинись, а не вигадуй значення.

## Задача

Прикріплені CSV з Google Ads UI (експорт за різні тижні/місяці по одному клієнту). Треба зібрати їх у один `data.json` за такою схемою.

## Схема data.json

```json
{
  "client":  {"name": "<НАЗВА КЛІЄНТА>", "logo": "logo-client.png"},
  "agency":  {"name": "<НАЗВА АГЕНЦІЇ>", "logo": "logo-agency.png"},
  "updated_at": "<ISO 8601, зараз>",
  "source": "google_ads_csv",
  "weekly":  [ <масив тижневих періодів, відсортованих від найдавнішого до найсвіжішого> ],
  "monthly": [ <масив місячних періодів, теж від найдавнішого до найсвіжішого> ]
}
```

### Формат одного періоду (weekly і monthly однаковий)

```json
{
  "label": "DD.MM-DD.MM.YYYY",
  "period": {
    "current":  {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"},
    "previous": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}    // null для найпершого періоду
  },
  "kpi": [                              // ЗАВЖДИ рівно 4 елементи в цьому порядку
    {"key": "revenue",   "label": "Виручка", "value": <число>, "unit": "грн", "delta_pct": <число або null>, "prev": <число>, "delta_inverted": false},
    {"key": "spend",     "label": "Витрати", "value": <число>, "unit": "грн", "delta_pct": <число або null>, "prev": <число>, "delta_inverted": true},
    {"key": "roas",      "label": "ROAS",    "value": <число>, "unit": "%",   "delta_pct": <число або null>, "prev": <число>, "delta_inverted": false},
    {"key": "purchases", "label": "Покупок", "value": <ціле>,  "unit": "",    "delta_pct": <число або null>, "prev": <ціле>,  "delta_inverted": false}
  ],
  "kpi_secondary": [                    // ЗАВЖДИ рівно 4 елементи в цьому порядку
    {"key": "cpa",         "label": "CPA (ціна покупки)", "value": <число>, "unit": "грн", "delta_pct": <число або null>, "prev": <число>, "delta_inverted": true},
    {"key": "avg_check",   "label": "Ср. чек",            "value": <число>, "unit": "грн", "delta_pct": <число або null>, "prev": <число>, "delta_inverted": false},
    {"key": "cr_purchase", "label": "Кф. конверсії",      "value": <число>, "unit": "%",   "delta_pct": <число або null>, "prev": <число>, "delta_inverted": false},
    {"key": "cpc",         "label": "CPC (ціна кліку)",   "value": <число>, "unit": "грн", "delta_pct": <число або null>, "prev": <число>, "delta_inverted": true}
  ],
  "chart": {
    "labels": [<DAILY-мітки "DD.MM" за КОЖЕН день цього періоду; тиждень = 7 точок, місяць = 28-31>],
    "series": {                         // ЗАВЖДИ ці 8 ключів, довжина = кількість днів у періоді
      "revenue":     [<daily масив>],
      "spend":       [...],
      "roas":        [...],
      "purchases":   [...],
      "cpa":         [...],
      "avg_check":   [...],
      "cr_purchase": [...],
      "cpc":         [...]
    }
  },
  "metrics": [                          // ЗАВЖДИ рівно 10 елементів у цьому порядку
    {"name": "Вартість покупки",  "current": <число>, "previous": <число>, "unit": "грн", "delta_inverted": true},
    {"name": "Ср. чек",           "current": <число>, "previous": <число>, "unit": "грн"},
    {"name": "Кф. конверсії",     "current": <число>, "previous": <число>, "unit": "%"},
    {"name": "Покази",            "current": <число>, "previous": <число>, "unit": ""},
    {"name": "Кліки",             "current": <число>, "previous": <число>, "unit": ""},
    {"name": "CPC",               "current": <число>, "previous": <число>, "unit": "грн", "delta_inverted": true},
    {"name": "CTR",               "current": <число>, "previous": <число>, "unit": "%"},
    {"name": "Додавання в кошик", "current": <число>, "previous": <число>, "unit": ""},
    {"name": "CR → Add to cart",  "current": <число>, "previous": <число>, "unit": "%"},
    {"name": "Ціна дод. в кошик", "current": <число>, "previous": <число>, "unit": "грн", "delta_inverted": true}
  ],
  "campaigns": [                        // від найбільшої за spend до найменшої
    {
      "name": "<повна назва кампанії>",
      "type": "Search" | "PMax" | "Demand Gen" | "Display" | "Shopping" | "Video",
      "summary": {
        "spend":       <число>,
        "revenue":     <число>,
        "roas":        <число>,        // %
        "conversions": <ціле>,
        "delta_roas":  <число>,        // %, порівняння з попереднім періодом (0 якщо перший)
        "cpa":         <число>
      },
      "details": [                     // ЗАВЖДИ рівно 14 елементів у цьому порядку
        {"name": "Витрати",              "current": <>, "previous": <>, "unit": "грн", "delta_inverted": true},
        {"name": "Покупок",              "current": <>, "previous": <>, "unit": ""},
        {"name": "Вартість покупки",     "current": <>, "previous": <>, "unit": "грн", "delta_inverted": true},
        {"name": "Ср.чек",               "current": <>, "previous": <>, "unit": "грн"},
        {"name": "Виручка",              "current": <>, "previous": <>, "unit": "грн"},
        {"name": "Кф. конверсії",        "current": <>, "previous": <>, "unit": "%"},
        {"name": "ROAS",                 "current": <>, "previous": <>, "unit": "%"},
        {"name": "Покази",               "current": <>, "previous": <>, "unit": ""},
        {"name": "Кліки",                "current": <>, "previous": <>, "unit": ""},
        {"name": "CPC",                  "current": <>, "previous": <>, "unit": "грн", "delta_inverted": true},
        {"name": "CTR",                  "current": <>, "previous": <>, "unit": "%"},
        {"name": "Impression Share",     "current": <>, "previous": <>, "unit": "%"},   // 0 якщо тип кампанії ≠ Search
        {"name": "Показів у верхній ч.", "current": <>, "previous": <>, "unit": "%"},   // 0 якщо тип кампанії ≠ Search
        {"name": "Показів на 1-й поз.",  "current": <>, "previous": <>, "unit": "%"}    // 0 якщо тип кампанії ≠ Search
      ]
    }
  ]
}
```

## Правила розрахунку

- `revenue` = «Значення конверсії» (conversions value) — сума за весь період.
- `spend`   = «Витрати» (cost).
- `purchases` = «Конверсії» (сума primary+included actions — зазвичай Purchase + Generate Lead якщо обидва primary).
- `roas` = `revenue / spend × 100`.
- `cpa`  = `spend / purchases` (0 якщо покупок 0).
- `avg_check` = `revenue / purchases` (0 якщо покупок 0).
- `cr_purchase` = `purchases / clicks × 100`.
- `cpc` = `spend / clicks`.
- `ctr` = `clicks / impressions × 100`.
- `delta_pct` = `(current - previous) / previous × 100` (округлено до 2 знаків), або `null` якщо previous = 0 / немає.
- `delta_inverted: true` — для метрик де падіння = добре (spend, cpa, cpc, cost per add to cart).

## Тип кампанії

За назвою або з окремої колонки «Тип кампанії»:
- містить «pmax» / «performance max» → `PMax`
- «demand gen» / «demand_gen» → `Demand Gen`
- «display» / «remarketing» → `Display`
- «shopping» → `Shopping`
- «video» / «youtube» → `Video`
- інакше → `Search`

## Chart

Для кожного періоду `chart.labels` і `chart.series` — це **daily-розбивка внутрі самого періоду** (Google Ads-style):
- **Тиждень** (7 днів): 7 точок, ПН→НД.
- **Місяць** (28-31): по одній точці на кожен день.

Тобто для weekly-звіту за 20.07-26.07: labels = `["20.07","21.07","22.07","23.07","24.07","25.07","26.07"]`, а series кожної метрики — 7 значень (сума за кожен день).

Щоб зібрати daily — треба щоб у CSV з Google Ads був сегмент **Segment → Day** (додається через «Segment» кнопку зверху таблиці). Якщо його немає — попроси студента перевивантажити CSV з denniм сегментом.

## Форматування чисел

- Всі числові поля — числа, НЕ рядки (`1234.56`, не `"1 234,56 грн"`).
- Копійки округлюй до 2 знаків, %-и до 2 знаків, кількості до цілого.

## Формат виводу

Поверни ГОТОВИЙ файл `data.json`. Не описуй сам JSON — просто файл. Все українською як в схемі, без перекладу назв метрик.

Якщо якогось поля бракує в CSV (напр. Add to Cart) — постав 0, не викидай.
Якщо кампанія має spend = 0 і revenue = 0 в періоді — не включай її в цей період.

Назви клієнта та агенції — постав placeholder «Demo Client» і «Your Agency», якщо я не сказав явно як їх звати. Я поправлю сам.

----- END -----

---

## Після того як Claude поверне data.json

1. Скачай файл.
2. Поклади в папку свого клієнта (замість старого `data.json`).
3. Відкрий `index.html` у браузері — перевір що всі показники видно і графік не поламаний.
4. Опублікуй (Netlify Drop або git push) — див. `HOW_TO_USE.md`.
