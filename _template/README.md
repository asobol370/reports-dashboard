# Шаблон дашборду Google Ads звіту для студентів

Це generic-версія дашборду [reports.bohatyrov.pro/minelly/](https://reports.bohatyrov.pro/minelly/) —
без Bohatyrov-специфіки. Для студентів агенції, у яких немає доступу до Google Ads API,
але є експорт CSV з UI кабінету.

## Файли

- **[HOW_TO_USE.md](HOW_TO_USE.md)** — покрокова інструкція для студента (з нуля до опублікованого URL клієнту) + розділ «Кастомізація» з готовими промптами (валюта, метрики, кольори, артефакт-режим)
- **[CLAUDE_PROMPT.md](CLAUDE_PROMPT.md)** — готовий prompt для Claude: копіюєш, приклеюєш свої CSV, отримуєш `data.json`
- **index.html** — сам дашборд (весь UI/JS inline, ~600 рядків, не змінювати)
- **data.json** — приклад даних (замінюєш на реальні через Claude)
- **logo-agency.png** — placeholder логотипу агенції (замінюєш на свій під тим же іменем)
- **favicon-32.png** — placeholder favicon

## Швидкий старт

1. Прочитай [HOW_TO_USE.md](HOW_TO_USE.md) від початку до кінця (~5 хв).
2. Скопіюй цю папку в `<назва-клієнта>/`.
3. Вивантаж CSV з Google Ads UI.
4. Дай Claude — отримай `data.json`.
5. Заміни, опублікуй на Netlify Drop.

Готово. Клієнт отримує URL з паролем.
