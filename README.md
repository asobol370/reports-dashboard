# Bohatyrov Marketing — Reports Dashboard

Веб-звіти для клієнтів агентства. Публічний host: **https://reports.bogatyrov.pro/**.

Один клієнт = одна підпапка з незалежним `index.html`, `data.json`, лого. Пароль-гейт на клієнті (client-side, sessionStorage).

Кожна сторінка тягне свій `data.json`, який будується скриптом `build_data_api.py` напряму з Google Ads API під MCC `834-562-8780`. Skрипт можна ганяти вручну або з GitHub Actions за розкладом.

## Активні дашборди

| URL | Клієнт | customer_id | Пароль |
|---|---|---|---|
| `/minelly/` | Minelly Coffee (кава) | 1392573958 | `minelly2026` |

## Структура репо

```
reports-dashboard/
├── CNAME                   # reports.bogatyrov.pro
├── README.md               # цей файл
├── .gitignore
└── <client>/               # одна папка на клієнта
    ├── index.html          # сам дашборд (весь UI/JS inline)
    ├── data.json           # згенеровані метрики (перебудовується скриптом)
    ├── build_data_api.py   # генератор для цього клієнта
    ├── logo-bohatyrov.png  # лого агенції
    ├── logo-<client>.png   # лого клієнта
    └── favicon-32.png
```

## Візуальний шаблон (той, що вже погоджений на Minelly)

- Light theme: bg `#f4f5f7`, surface `#ffffff`, brand `#0f172a`, positive `#16a34a`, negative `#dc2626`.
- Font: Inter 400/500/600/700/800.
- Layout: sticky sidebar 260px (лого агенції зверху, 3 якорі — Огляд / Метрики / Кампанії) + main.
- Client card fixed в лівому нижньому куті viewport (лого клієнта чорним через `filter: brightness(0)` + назва + updated_at).
- 4 primary KPI (Виручка / Витрати / ROAS / Покупок) + 4 secondary (CPA / Ср.чек / Кф.конверсії / CPC).
- Клік по будь-якій KPI-картці — додає її на графік (макс 4 одночасно, свій колір, зелений/синій — з осями, помаранчевий/фіолетовий — нормалізовані).
- Toggle Тиждень / Місяць + archive dropdown з усіма періодами (свіжі зверху).
- Кампанії — accordion: коротка summary + повний деталізований breakdown з IS/Top/First (для Search).
- Числа: `1 902 322 грн` (nbsp тисячі, кома для дробових < 100). Вісь Y графіка: `1,10M / 880k / 18k`.

## Як додати нового клієнта

1. `cp -r minelly/ <newclient>/`
2. Замінити `logo-<client>.png`, змінити `client.name` і `password` (в HTML: `const PASSWORD = ...`) і `sessionStorage`-ключ (щоб не заходили один по одному).
3. У `build_data_api.py` — замінити `CID`, `FIRST_MONDAY`, `ATC_ACTION` (якщо інакший conversion_action), а також `EXCLUDE_CAMPAIGN_IDS` при потребі.
4. Погнати `python3 <newclient>/build_data_api.py` → перевірити `data.json`.
5. Оновити цей README (табличка активних дашбордів).
6. `git commit + push` → GitHub Pages деплоїть за 1-2 хв.

## Джерело даних

- Ключові конверсії = `metrics.conversions` без сегментації по `conversion_action` (агрегує всі primary+included: у Minelly це `Purchase (google ads)` + `Generate_lead (google ads)`).
- Виручка = `metrics.conversions_value` (без сегментації, та ж логіка).
- Add to Cart — окремий запит з фільтром по action_name = `Minelly (web) add_to_cart`.
- Impression Share — тільки для Search-кампаній (`metrics.search_impression_share/top/absolute_top`), для PMax/Display/Demand Gen буде 0.
- Weekly бʼється по ПН-НД, monthly — календарні місяці (незавершений місяць виключається автоматично).

## Дeплой / CI

Поки що вручну: перегенерувати `data.json` + `git push`. Далі варто додати GitHub Actions за прикладом [minelly-catalog](https://github.com/asobol370/minelly-catalog):
- cron `0 6 * * *` (09:00 Kyiv)
- креди Google Ads зі GitHub Secrets
- `python3 <client>/build_data_api.py && git commit + push`
