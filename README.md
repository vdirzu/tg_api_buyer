# Telegram AI API Key Marketplace

Двуязычный Telegram-бот (RU/EN) для **тестовой** покупки API-ключей по серверному CSV.
Автоматические начисления, история, смена валюты USD/RUB, заявки на ручную выплату,
админ-панель с редактированием товаров, текстов, изображений и сетей.

**CSV не обращается к AI-провайдерам и не подтверждает реальную действительность,
права владельца или региональную доступность ключа. Используйте синтетические ключи.**
Выплата — ручное действие администратора; бот не выполняет банковские или криптопереводы.
Полная исходная спецификация: [docs/specification.md](docs/specification.md).

## Быстрый старт: Python 3.12 + PostgreSQL 16

Нужны Python 3.12+, [uv](https://docs.astral.sh/uv/), PostgreSQL 16+; Docker — для Compose.
Redis не нужен: один polling-процесс, состояния диалогов в памяти, деньги и ожидающие
проверки в PostgreSQL. После перезапуска незавершённый ввод начинается заново через /start;
созданные заявки, резервы и начисления сохраняются. Не запускайте два polling-процесса одного бота.

```bash
cp .env.example .env
uv sync --frozen
# Сгенерируйте HMAC-секрет и ключ шифрования; сохраните вывод в соответствующих полях .env.
uv run python -c 'import secrets; print(secrets.token_hex(32))'
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

В `.env` задайте:

| Переменная | Назначение |
| --- | --- |
| `BOT_TOKEN` | Токен своего бота от официального @BotFather, команда /newbot |
| `ADMIN_IDS` | JSON-массив Telegram ID первых администраторов, например `[123456789]`; замените на свой ID |
| `DATABASE_URL` | Async URL `postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE` |
| `KEY_HMAC_SECRET` | Случайный постоянный секрет длиной от 32 символов |
| `PAYMENT_ENCRYPTION_KEY` | Fernet-ключ для шифрования платёжных реквизитов |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL для Compose; рекомендуется случайная hex-строка |
| `CSV_PATH` | По умолчанию `data/keys.csv` |
| `EXCHANGE_RATE_URL` | По умолчанию `https://open.er-api.com/v6/latest/USD` |
| `EXCHANGE_RATE_TTL_SECONDS` | Время кеширования курса, по умолчанию 3600 секунд |
| `SUBMISSION_INTERVAL_SECONDS` | Пауза между проверками пользователя, по умолчанию 3 секунды |

Секреты никогда не коммитятся. `DATABASE_URL` содержит пароль — не публикуйте его в логах.
Если пароль содержит URL-символы, кодируйте его для `DATABASE_URL`; в Compose используйте
случайный hex-пароль, чтобы избежать неоднозначного экранирования.

Создайте PostgreSQL-базу и пользователя с правом миграций, затем:

```bash
uv run alembic upgrade head
uv run python -m app.cli seed
uv run python -m app.cli sample-csv
uv run python -m app.cli check
uv run python -m app.main
```

`seed` идемпотентен: создаёт первых администраторов только при пустой таблице, а также
начальные криптосети и минимумы (1 USD / 100 RUB). Он **не создаёт товары и деньги**.
После первого запуска управление администраторами выполняется через `/admin`;
изменение ADMIN_IDS не восстанавливает ранее отключённого администратора.
Откройте личный чат бота, нажмите Start, выберите язык и валюту, затем `/admin`.
Администратор должен сначала начать чат с ботом, иначе Telegram не доставит уведомления.

Через @BotFather можно задать имя, описание и аватар бота. Меню команд приложение
настраивает автоматически. Бот работает только в личных чатах, webhook не требуется;
при переносе с webhook удалите его через официальный Bot API перед polling.

## Windows: psycopg и цикл событий

Если DATABASE_URL использует `postgresql+psycopg://`, установите соответствующий extra:

```bat
uv sync --extra psycopg
uv run --extra psycopg alembic upgrade head
uv run --extra psycopg python -m app.cli seed
uv run --extra psycopg python -m app.cli sample-csv
uv run --extra psycopg python -m app.cli check
uv run --extra psycopg python -m app.main
```

Уже существующий CSV повторно генерировать не нужно. Сохраните `.env` и `data/keys.csv`
при обновлении исходников. Для исходного драйвера `postgresql+asyncpg://` extra не требуется.

Ошибка `Psycopg cannot use the 'ProactorEventLoop' to run in async mode` возникает
из-за стандартного цикла событий Windows. Все точки запуска проекта — Alembic, CLI
и бот — теперь используют `app.runtime.run_async`: на Windows он создаёт
SelectorEventLoop через `loop_factory`, без изменения глобальной политики asyncio.
На Linux используется стандартный цикл. Пароли и DATABASE_URL для этого исправления
менять не требуется. Это устраняет указанную ошибку цикла событий; доступность самой
базы, её имя и учётные данные проверяются на следующем шаге подключения.

### Windows: кодировка и доступ PostgreSQL

Файлы переводов, `.env` и создаваемый CSV используют UTF-8 явно, независимо от
системной CP1251. При `UnicodeDecodeError ... cp1251` обновите исходники проекта;
переключать кодовую страницу консоли для чтения JSON не требуется.

Если PostgreSQL отвечает, но отклоняет вход для пользователя из DATABASE_URL:

1. В pgAdmin подключитесь администратором PostgreSQL к нужному серверу/порту.
2. В Login/Group Roles проверьте наличие роли приложения и разрешение Can login.
   В Properties → Definition установите её пароль и обновите пароль в локальном `.env`.
   Не публикуйте `.env` или пароль в чате.
3. Для `tg_api_user` строка имеет вид
   `postgresql+psycopg://tg_api_user:URL_ENCODED_PASSWORD@127.0.0.1:5432/YOUR_DATABASE`.
   Замените обе заглушки своими значениями. Символы пароля вроде `@`, `:`, `/`, `#`, `%`
   необходимо URL-кодировать, иначе они могут менять разбор строки подключения.
4. Если роль не существует, создайте Login role. Проверьте, что указанная база существует
   и роль имеет право выполнять миграции в её схеме. Не удаляйте существующую базу.
5. Повторите миграции; команды seed/check/main выполняйте после их успешного завершения.

Альтернатива pgAdmin: в SQL Shell (psql) войдите администратором и выполните `\du`,
затем `\password tg_api_user` для существующей роли. Новый пароль вводится скрыто,
он не включается в SQL-строку. Пароль Windows или токен Telegram не заменяет пароль
роли PostgreSQL. Если DATABASE_URL задана также в окружении Windows, она имеет приоритет
над `.env`; проверьте настройки переменных, не печатая строку с паролем в общий лог.

## Docker Compose

Создайте `.env` и установите секреты, как выше. CSV сначала сгенерируйте локально через
`uv run python -m app.cli sample-csv`: он использует тот же KEY_HMAC_SECRET, что и бот.

```bash
docker compose up --build -d db
docker compose run --rm migrate
docker compose run --rm --no-deps bot .venv/bin/python -m app.cli seed
docker compose run --rm --no-deps bot .venv/bin/python -m app.cli check
docker compose up --build -d bot
docker compose logs --tail=50 bot
```

Compose переопределяет DATABASE_URL для внутреннего хоста `db`; база не публикуется наружу.
Данные PostgreSQL сохраняются в volume `database`, CSV монтируется read-only. Бот работает
не от root, с read-only root filesystem. Каталог `data` должен быть доступен на чтение
UID 10001. Сгенерированный файл имеет режим 0600 — перед Compose выдайте доступ нужной
группе/UID или для **синтетического** CSV выполните `chmod 644 data/keys.csv`.
Не делайте файлы с реальными секретами общедоступными.

`migrate` запускается до бота. После обновления: сделайте резервную копию, затем
`docker compose up --build -d`. Не выполняйте `docker compose down -v` на рабочей базе:
это удалит данные. Откат миграций — только на тестовой базе или после согласованного
восстановления, так как downgrade удаляет историю.

## Управление через Telegram

Все основные экраны используют inline-кнопки, Back и Main menu. Поддержка и юридические
страницы не отменяют текущий ввод ключа/реквизитов; Main menu, Profile и Catalog отменяют
незавершённый диалог. Изображения редактируются вместе с сообщением, когда это позволяет
Telegram. Длинные экраны показывают изображение отдельно от текста.

В `/admin` выберите раздел. Формы принимают JSON обычным сообщением, числовые денежные
значения передавайте **строками**. JSON-поля являются техническими идентификаторами и
одинаковы для обоих языков. Изменения применяются сразу, без перезапуска.

### Товары

Раздел «Товары: добавить / изменить». Создание:

```json
{"id":"provider_a","name_ru":"Пример AI","name_en":"Example AI","description_ru":"Тестовая покупка по CSV","description_en":"CSV test purchase","conditions_ru":"Только синтетические ключи","conditions_en":"Synthetic keys only","rate":"0.30","active":true,"display_order":10}
```

Редактирование — ID и нужные поля:

```json
{"id":"provider_a","rate":"0.35","active":false,"display_order":20}
```

Поддерживаются `name_ru/en`, `description_ru/en`, `conditions_ru/en`, `rate`, `image`
(Telegram file ID или null), `active`, `display_order`. Удаление заменено деактивацией,
чтобы не ломать финансовые ссылки. Статистика по провайдерам находится в dashboard.

### Тексты, изображения, минимумы и курс

Раздел «Тексты и настройки», формат `{"key":"...","value":...}`:

```json
{"key":"welcome.ru","value":"Добро пожаловать на тестовую площадку!"}
```

Поддерживаемые ключи:

- `welcome`, `main`, `catalog`, `profile`, `withdraw`, `support`, `about`,
  `legal_fallback`, `support_contact`, `terms_url`, `privacy_url` с суффиксом `.ru` / `.en`.
- `support_contact.en` — Telegram username без URL, например `example_support`.
- `terms_url.en` / `privacy_url.en` — HTTPS URL; пустая строка убирает ссылку.
- `minimum.USD` / `minimum.RUB` — положительная строковая сумма до двух знаков.
- `exchange.url` — HTTPS endpoint в формате Open ExchangeRate-API ниже.
- `exchange.ttl` — целое количество секунд, 1–86400.
- `image.welcome`, `image.main`, `image.catalog`, `image.profile`, `image.withdraw`,
  `image.support`, `image.about` — Telegram file ID или null для удаления.
- `message.<ключ_локали>.ru/en` — замена текста сообщения, например
  `message.progress_lookup.ru`, `message.rate_unavailable.en`. Доступные имена:
  [app/locales/ru.json](app/locales/ru.json) и [app/locales/en.json](app/locales/en.json).
  Для замен используйте обычный текст без `{}` (не шаблоны).

В разделе «Загрузить изображение» отправьте **фото**, подпись — `main`, `catalog`,
`profile`, `withdraw`, `about`, `welcome`, `support` или `product:provider_a`.
Telegram file ID сохраняется в базе. Удалить товарное фото:
`{"id":"provider_a","image":null}` в разделе товаров.

### Администраторы и сети

Администраторы: `{"id":123456789,"active":true}` добавляет/включает,
`{"id":123456789,"active":false}` отключает. Последнего активного администратора
отключить нельзя, в том числе при одновременных запросах. Каждый административный
обработчик и сервис проверяет полномочия, изменения сохраняются в audit log.

Криптоактивы и сети:

```json
{"id":"usdt_tron","asset":"USDT","network":"TRON (TRC20)","address_kind":"tron","active":true}
```

Поддерживаемые валидаторы: `evm`, `tron`, `solana`, `ton`. Проверка адреса — только
формат; она не подтверждает владельца, наличие кошелька или выполнение перевода.
Актив и сеть показываются отдельно. Выключение: `{"id":"usdt_tron","active":false}`.
Начальные варианты: USDT/TRON, USDT/Ethereum, USDT/BSC, USDC/Ethereum,
USDC/Solana, TON/The Open Network.

### Ручные выплаты

Пользователь выбирает карту (Visa/Mastercard/Mir) или актив и сеть, сумму и реквизиты.
Минимум и доступный баланс проверяются повторно в транзакции. Для карт проверяются
длина, префикс и контрольная сумма Luhn; это не банковская проверка.
При создании заявки USD-эквивалент переводится из available в reserved.
Администраторы получают уведомление с суммой, способом, ID пользователя и кнопками.
Реквизиты доступны отдельной авторизованной кнопкой; каждое открытие записывается в аудит.

- «В обработке» — резерв сохраняется.
- «Выплачено» — нажимайте **после фактического ручного перевода**, резерв списывается.
- «Отклонено» / «Возвращено» — требуется причина, резерв возвращается.
- После Paid вернуть средства этой же заявкой нельзя: это предотвратит двойную выплату.

Повторы действий не меняют баланс повторно. Пользователь получает сообщение о смене
статуса и видит результат в истории. Если Telegram не доставил уведомление, заявка
остаётся доступна в `/admin` → «Заявки на вывод»; ошибка доставки не откатывает деньги.
В разделе пользователя можно посмотреть баланс, резерв и последние ключи. Ручных
правок баланса через SQL или скрытой админ-кнопки нет.

## CSV и тестовые ключи

```csv
key_fingerprint,provider_id,balance_usd,region_restricted,test_status
```

Формат: HMAC-SHA-256 в нижнем hex-регистре (64 символа), ID товара, неотрицательный
Decimal USD до 8 знаков, `true`/`false`, `valid`/`invalid`/`ineligible`.
В файле не должно быть повторных отпечатков, повреждённых или дополнительных колонок.
Весь файл валидируется до использования. При проблеме **не начисляется ничего**.

```bash
uv run python -m app.cli sample-csv
# Только для осознанного обновления своего тестового файла:
uv run python -m app.cli sample-csv --force
```

Генератор создаёт отпечатки от `synthetic-key-1` ... `synthetic-key-10` с вашим
KEY_HMAC_SECRET, выполняя fsync и атомарный os.replace. Первые восемь относятся к
`provider_a`, девятый — к `provider_b`, десятый — invalid для `provider_b`.
Добавьте товары с этими ID через админ-панель. Баланс каждой записи — 100 USD.
`data/sample_keys.csv` показывает синтетический формат, но его отпечатки созданы
с другим локальным секретом: для своей установки **обязательно запустите генератор**.
Не меняйте HMAC-секрет без миграции отпечатков: иначе защита от повторной покупки
того же исходного значения не сможет сопоставить старые и новые отпечатки.

Для другого синтетического ключа отпечаток вычисляется функцией
`app.services.csv_verification.fingerprint(key, secret)`. Не передавайте реальные
ключи через аргументы shell, логи или Git. При ручном обновлении пишите полный
новый файл рядом и заменяйте через `os.replace`, не редактируйте рабочий CSV по месту.
Бот читает новый стабильный снимок при каждом запросе; перезапуск не нужен.

## Финансовая модель и курс

База — единственный источник финансовой истины. Все расчёты выполняются `Decimal`,
начисление округляется до центов USD (ROUND_HALF_UP); технический USD-резерв хранится
до 8 знаков, при RUB-выводе округляется вверх на последнем знаке.

`payment_usd = CSV_balance_usd × product_rate × (1 - discount)`.
Скидка 20% применяется **только ко второму успешно принятому ключу пользователя**.
Первый, третий и последующие её не получают, даже если CSV-флаг ограничения true:
этот флаг сохраняется и показывается отдельно от искусственного правила второго ключа.
Ошибки и дубли не увеличивают счётчик. Это тест, а не реальная проверка регионов.

Пользователь блокируется `SELECT ... FOR UPDATE`; fingerprint уникален глобально.
Начисление, AcceptedKey, Transaction, счётчик и AuditLog коммитятся атомарно.
Заявки сериализуют изменения доступного и резервного баланса, переходы блокируют
заявку и пользователя. Смена валюты не меняет underlying USD.

Источник курса по умолчанию: [ExchangeRate-API Open Access](https://www.exchangerate-api.com/docs/free).
Используется HTTPS без перенаправлений, таймаут 10 секунд, ограниченный кеш; ответ
должен содержать `result=success`, `base_code=USD`, `rates.RUB`,
`time_last_update_unix`. Принимается опубликованный курс не старше 48 часов
(ежедневный источник). `exchange.ttl` — срок локального кеша, а не давность публикации.
Для другого поставщика endpoint должен возвращать этот формат. Внешние запросы
передачи API-ключей провайдерам не выполняются.

Если курс недоступен, RUB-начисление не выполняется. Сохраняется одна ожидающая
проверка пользователя: отпечаток, баланс CSV, ставка, провайдер и CSV-флаг.
Профиль → «Повторить сохранённую проверку» завершает её после восстановления курса.
Новая ожидающая проверка заменяет предыдущую; исходный ключ не хранится.
При повторе сохраняется исходная ставка, но порядковый номер успешного принятия
и скидка определяются на момент коммита. Неактивный товар или уже принятый ключ
по-прежнему отклоняются. Резервирование RUB-вывода при сбое курса не выполняется;
можно повторить ввод реквизитов или начать заявку заново.

Снимки курса, источника и времени публикации записываются для начислений и выводов.
История показывает валюту и курс на момент операции; текущий профиль использует
свежий курс отображения. AuditLog, AcceptedKey и Transaction защищены PostgreSQL
триггерами от UPDATE/DELETE; исправления истории требуют отдельной осознанной миграции.

## Схема, тесты и CI

Таблицы: users, products, accepted_keys, transactions, withdrawals, administrators,
configuration, crypto_options, audit_log, verification_attempts, pending_acceptances.
Схема создаётся Alembic, приложение не вызывает create_all при запуске.

```bash
uv run alembic upgrade head
uv run alembic check
# Используйте отдельную тестовую PostgreSQL-базу с правом создавать схемы:
TEST_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/TEST_DB uv run pytest -q
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
```

Тесты создают и удаляют уникальную PostgreSQL-схему на каждый тест. Отсутствие
TEST_DATABASE_URL — ошибка, а не тихий skip. Проверяются конкурентные начисления,
повторные выплаты, откаты транзакций, курс и его сбои, CSV, права администратора,
RU/EN onboarding и полный Telegram-сценарий через тестовую сессию без внешних запросов.
GitHub Actions выполняет миграции, проверку схемы, тесты и цикл downgrade/upgrade
на одноразовой базе. Настоящий Telegram API тест требует личного токена и запуска
бота; автоматические тесты не подтверждают сетевую доставку в Telegram.

## Production и эксплуатация

1. Используйте отдельного бота и базу; не переносите синтетические деньги в рабочий учёт.
2. Задайте реальные BOT_TOKEN и ADMIN_IDS через защищённые переменные/secret manager.
   HMAC и Fernet-ключи должны быть постоянными и резервироваться отдельно от БД.
3. Сделайте зашифрованную резервную копию PostgreSQL (`pg_dump`) и проверьте восстановление.
   Утрата Fernet-ключа делает реквизиты нечитаемыми; потеря HMAC нарушает сопоставление ключей.
4. Выполните миграции отдельной привилегированной ролью, затем запустите одного polling-бота.
   Ограничьте сетевой egress PostgreSQL, api.telegram.org и выбранным курсовым endpoint.
5. Настройте действительные условия использования, privacy URL и контакт поддержки.
   Не заявляйте о реальной верификации AI-провайдеров: реализация CSV-тестовая.
6. Настройте мониторинг JSON-событий `handler_failed`, `admin_notification_failed`,
   `user_notification_failed`. Логи не содержат сырого API-ключа или реквизитов.
   Ограничьте доступ к БД и сообщениям администраторов; согласуйте срок хранения реквизитов.

Платёжные реквизиты шифруются Fernet в БД; в Telegram они видны самому пользователю
и администратору, который открыл заявку. Бот пытается удалить сообщение с ключом/
реквизитами, но не может гарантировать удаление из инфраструктуры Telegram.
Никогда не запрашивайте CVV, PIN, срок действия карты или доступ к банковскому аккаунту.

## Troubleshooting

- **Пустой каталог:** `/admin` → создать активный товар; `seed` не добавляет товары.
- **CSV unavailable:** проверьте путь, чтение (UID 10001 для Docker), заголовок, дубли,
  Decimal и флаги. `python -m app.cli check` проверяет файл и таблицу users.
- **Ключ не найден:** генератор должен использовать тот же HMAC-секрет и provider ID.
- **Rate unavailable:** проверьте HTTPS-доступ к `open.er-api.com`, формат, timestamp
  и настройки URL/TTL. Фиктивный курс не подставляется; повторите сохранённую проверку.
- **Администратор не получает заявки:** он должен запустить бота и быть активен в БД;
  незавершённые заявки всегда видны в `/admin`.
- **Нет админ-доступа:** ADMIN_IDS используется только для первой инициализации. Попросите
  текущего администратора включить нужный ID. Последнего отключить через бот нельзя.
- **Conflict: another getUpdates request:** остановите второй процесс этого же бота.
- **Webhook active:** удалите webhook официальным методом Bot API перед polling.
- **Database authentication failed:** проверьте DATABASE_URL; смена POSTGRES_PASSWORD
  не меняет пароль уже существующего PostgreSQL volume — используйте ALTER ROLE безопасно.
- **Диалог сбросился после рестарта:** это ожидаемо для memory FSM; финансовая история
  и ожидающая проверка ключа сохранены в БД. Начните ввод заново через /start.
- **Read-only cache в облаке:** задайте `UV_CACHE_DIR=/workspace/.cache/uv` перед uv-командами.

## Сборка в облаке за TLS-прокси

Если Docker build не видит DNS прокси или его корпоративный CA, используйте
`python scripts/build_cloud.py` из корня репозитория. Скрипт передаёт существующие
proxy build args, разрешённый адрес прокси и системный CA через временный BuildKit
secret `build_ca_bundle`. Сертификат не встраивается в образ, TLS остаётся включённым.
Для другого доверенного CA задайте SSL_CERT_FILE. Обычная сборка: `docker build -t tg-api-buyer:local .`.
Рантайм за TLS-прокси также должен получить доверенный CA: смонтируйте bundle read-only
и задайте SSL_CERT_FILE для httpx; для aiohttp/Telegram используйте системное хранилище CA.

## English quick reference

Copy `.env.example` to `.env`, configure your BotFather token, initial Telegram admin IDs,
PostgreSQL URL, a random stable HMAC secret and a Fernet key. Run `uv sync --frozen`,
`uv run alembic upgrade head`, `uv run python -m app.cli seed`,
`uv run python -m app.cli sample-csv`, then `uv run python -m app.main`.
Start a private chat, choose English/USD or RUB and open `/admin`. Add `provider_a`
using the product JSON example above. Test with `synthetic-key-1`, `synthetic-key-2`,
`synthetic-key-3`: at rate 0.30 and balance 100 USD, credits are 30, 24, 30 USD.
Only the second successful acceptance receives the test discount. All UI messages
and administrative prompts have English translations. Configuration key suffixes
`.en` and `.ru` edit the corresponding language. Upload photos in the image section
with the target screen or `product:ID` as the caption. Payouts are manual; mark Paid
only after making the real transfer. Reject/Return require a reason and release funds.
