# KNITU StudyHub 1.3.0-dev — серверный каркас

Не публиковать как рабочую замену 1.2. Корневая PWA и действующие GitHub Actions остаются без изменений. Все файлы этого комплекта размещаются в каталоге `server/` отдельной ветки `develop`.

## Состояние

- MySQL 8.4 LTS, InnoDB, utf8mb4, SQLAlchemy 2, Alembic, FastAPI.
- 11 таблиц, привязка учебной информации к группе и семестру, уникальные коды задач внутри группы. Составные внешние ключи не позволяют связать прогресс с задачей другой группы. Участник может состоять в нескольких группах. Предусмотрены роли владельца, администратора группы и студента.
- API чтения общих учебных данных, фильтрация дат и вариантов. Закрытые группы не публикуются.
- Учётная запись привязана к идентификатору MAX. Вход и API изменения пользовательских данных **отключены**, до реализации серверной проверки подлинности MAX и сессий. Никаких тестовых паролей, токенов или обхода авторизации.
- Миграция 0001_initial и справочный SQL для MySQL. Выполнять миграции через Alembic, не запускать schema.sql дополнительно.
- Импорт исходных JSON без удаления существующего прогресса; отсутствующие задания архивируются (active=false), идентификаторы не меняются. Импорт расписания и контента выполняется по доверенным файлам оператором. Пока только группа 661-М52, первый семестр. Автоматический импорт GitHub Actions в БД ещё не подключён.
- Встроенная тестовая база общих данных совпадает по содержимому с файлами data.json и content.json ветки main, проверенными при подготовке комплекта: 7 дисциплин, 38 заданий, 40 формулировок СРС, 49 событий, 3 записи дедлайнов, 1 тестовое объявление. Расписание из выгрузки 24.11.2026; контент обновлён 26.11.2026. Личных отметок, списков студентов и паролей в seed нет. Перед первым реальным импортом заново взять актуальные data.json и content.json из main.

## Развёртывание в тестовой среде

Нужны Docker Engine и Compose v2 на локальном ПК или Linux-сервере. Сервер не требуется арендовать до согласования. Контейнер MySQL не публикует порт наружу; API привязан к localhost. Для удалённой проверки использовать SSH-туннель, не открывать порт 8000 в Интернет.

Из каталога server:

```bash
cp .env.example .env
# Заполнить .env локально: разные уникальные сложные пароли MYSQL_ROOT_PASSWORD и MYSQL_PASSWORD.
# Никогда не загружать .env в GitHub.
docker compose up -d db
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.import_data
docker compose up -d api
curl http://127.0.0.1:8000/health
```

Документация API: http://127.0.0.1:8000/docs. Перед повторным импортом скопировать свежие проверенные JSON в seed/, пересобрать api, запустить импорт. Не выполнять `docker compose down -v`: это удаляет том MySQL. Для резервного копирования и восстановления нужен отдельный регламент перед production.

## API

| Метод | Путь | Назначение |
|---|---|---|
| GET | /health | Проверка БД |
| GET | /api/v1/groups | Публичные группы |
| GET | /api/v1/groups/{slug}/bundle | Учебная база в структуре, совместимой с JSON PWA |
| GET | /api/v1/groups/{slug}/tasks | Активные задания |
| GET | /api/v1/groups/{slug}/schedule?start=2026-11-25&end=2026-11-25 | Расписание и сведения о покрытии; границы включены |
| GET | /api/v1/groups/{slug}/variants/{digit} | СРС по последней цифре 0–9 |
| POST | /api/v1/auth/max | 503, намеренно отключено |

Текущий slug: `knitu-661-m52-2026-1`. API отдаёт только общие данные и не содержит маршрутов чтения/изменения личного прогресса. Публичный интерфейс 1.2 пока использует статические JSON.

## Тестирование

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

7 тестов пройдены в SQLite: точность импорта, 10 вариантов, фильтрация, закрытые группы, блокировка входа, повторный импорт с сохранением прогресса, ограничения и роли. Выполнены миграция Alembic и импорт на SQLite; сгенерирован SQL для MySQL. Реальное исполнение MySQL и Docker в среде разработки не проверялось. Перед релизом выполнить интеграционный тест на MySQL 8.4.

## Следующий этап

1. Развернуть и протестировать в отдельной среде MySQL 8.4.
2. Подключить автоматический импорт только проверенного расписания, сохраняя прошлый снимок при сбое КНИТУ; отделить административный контент от расписания, обеспечить журнал и резервное копирование.
3. Реализовать MAX-авторизацию: проверять исходные подписанные данные на сервере согласно актуальной документации MAX, срок действия и повторное использование, выдавать серверные сессии, назначать владельца по проверенному ID вне публичного API. Не доверять клиентским user_id/role. Не хранить токен бота в PWA или GitHub Pages.
4. Реализовать API для администратора и личных отметок; добавить журнал действий, серверную валидацию и тесты разграничения групп. Определить основания обработки, сроки хранения и локализацию персональных данных до их сбора.
5. Перевести интерфейс 1.2 на API через адаптер, сохранив импорт/экспорт локального прогресса и режим гостя. Не включать авторизацию или публичную запись, пока серверная проверка не готова. Настроить HTTPS и прокси Nginx; предпочтительно обслуживать приватное приложение и API с одного российского серверного origin.
6. После верификации MAX: бот, мини-приложение, пользовательские уведомления по согласию и настройкам, проверка платформой. Обычный браузерный вход проектировать отдельно, не предполагая наличие OAuth.

## 1.3.1-dev: MAX sessions and protected operations

The above 1.3.0 notes describe the original baseline. In 1.3.1 the MAX
endpoint is implemented but stays disabled while MAX_BOT_TOKEN is empty.
Use Alembic upgrade head (migration 0002_auth, 14 application tables).
The live PWA is still 1.2; no client-side login UI is included in this release.

- POST /api/v1/auth/max with JSON {"init_data":"raw MAX Bridge initData"}.
  Official signature algorithm: https://dev.max.ru/docs/webapps/validation/.
  Launch validity: 5 min, future clock skew <=30 sec, signature accepted once.
  Only operator-provisioned, active accounts can log in; no client role grants.
  Response contains an opaque bearer token, valid for 8 hours. Only its SHA-256
  digest is persisted. Keep token in memory, never URLs or public localStorage.
- GET /api/v1/me and POST /api/v1/auth/logout (Authorization: Bearer TOKEN).
- GET /api/v1/groups/{slug}/me/progress; PUT .../me/digit with digit 0..9 or null;
  PUT .../me/progress/{task_code} with status. Personal marks are not grades.
- POST .../admin/tasks, PUT .../admin/tasks/{code}; body: subject, title,
  description, deadline (ISO date or null), deadlineNote, source, show_deadline
  (optional boolean; omitted preserves list inclusion if deadline exists).
- GET/POST .../admin/announcements, PUT .../admin/announcements/{id}; body:
  date, title, body, source. GET .../admin/audit lists 100 recent group edits.
  Task and announcement writes and audit records commit together.
- No access tokens, launch data, bot tokens, or private progress in public bundle.
  Closed-group academic bundle still not served through public API.

Provision a verified MAX user ID through trusted server shell only, e.g.
`python -m app.access_cli grant VERIFIED_NUMERIC_ID owner --group knitu-661-m52-2026-1`
(replace VERIFIED_NUMERIC_ID with verified numeric ID, not student-book number).
Roles student/admin require --group. Owner is a global flag; group membership
role changes do not revoke it. Disable accounts with `... disable ID` (also
revokes sessions). Run `python -m app.access_cli cleanup` periodically to remove
expired sessions and launch signatures. Keep bot token solely in server .env.
Before enabling: HTTPS, origin and reverse proxy configuration, request-size
and rate limits, access-log redaction, backup/restore and privacy documentation.
Real MAX Mini App, browser login, automated bot notifications and deployment
are separate later steps. Test credentials are synthetic only.

### Timetable update without overwriting content

Initial import is unchanged before administrative writes. After an audited
admin edit, full JSON re-import is deliberately blocked. Run
`python -m app.sync_schedule /path/to/verified-published-data.json` on a trusted
server-side file from StudyHub after a successful check (sync.status=ok, age
<=12h, fixed semester/coverage). It replaces timetable records only, not tasks,
announcements or progress. Failed/stale sync is rejected. This is an operator
command; automated transfer from GitHub to the server is not connected yet.

### Tests

Run `python -m pytest -q` for SQLite tests. The CI installer also runs migration
and imports in disposable MySQL 8.4 and private API tests on dedicated database
studyhub_private_ci. Those tests drop their own tables; NEVER point
STUDYHUB_PRIVATE_TEST_DB at a production database. No real MAX token needed.

## Кабинет 1.3.2-dev

- FastAPI раздаёт новый адаптивный интерфейс по `/cabinet/` на том же origin, что и API. Старый PWA 1.2 в корне репозитория не изменён. Новый кабинет пока не является офлайн-PWA: публичный режим требует доступного API.
- Гость видит общие сведения и ведёт локальные отметки; пользователь MAX после проверки подписи работает с MySQL. Пока отображаются только публичные учебные группы, а вход из обычного браузера не реализован. Доступ выдаётся оператором через `app.access_cli`, без регистрации по неподтверждённому ID.
- Подключена официальная библиотека `https://st.max.ru/js/max-web-app.js`. В запрос на вход передаётся только исходная строка `WebApp.initData`. Сессионный Bearer-токен хранится только в памяти вкладки, после перезагрузки требуется новый запуск из MAX. Не сохранять токен или приватные API-ответы в Service Worker, localStorage или логах. Для реального запуска нужен HTTPS и зарегистрированный бот. Не совмещать новый кабинет с областью действия старого Service Worker.
- Администратор и владелец видят раздел управления, студент не видит. Сервер самостоятельно проверяет права. Создание/изменение задач и объявлений записывается в MySQL и аудит; удаление пока не реализовано.
- Импорт экспортированного JSON 1.2 или гостевых отметок требует подтверждения. `POST /api/v1/groups/{slug}/me/import` атомарно добавляет отсутствующие отметки и цифру только если она ещё не задана. Существующие серверные данные не заменяются. Экспорт JSON и календаря ICS доступен в кабинете.
- Изменения не требуют новой миграции: используется 0002_auth. Для развёртывания пересобрать API-образ (`docker compose build api`) и выполнить `docker compose up -d api`.
- В CI предусмотрены 15 тестов SQLite, 8 тестов на отдельной временной MySQL и мобильный браузерный smoke-тест Playwright с синтетическим запуском MAX, а не с настоящим аккаунтом. Локально 15 тестов SQLite пройдены, запуск Chromium на localhost заблокирован политикой среды. Реальная интеграция MAX и эксплуатация HTTPS требуют отдельной проверки.

## Эксплуатационная подготовка 1.3.3-dev

См. [ops/DEPLOY.md](ops/DEPLOY.md) — развёртывание, HTTPS, Docker hardening, операторские роли, локальные backup и восстановление, таймеры и проверка состояния. Новая миграция не требуется (0002_auth). Ключ гостевых отметок не изменён. Секреты и реальные дампы не должны попадать в GitHub. Реальный VPS, домен, MAX и внешний мониторинг ещё не подключены.
