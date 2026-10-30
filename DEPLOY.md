# Запуск через Docker Compose

Пример для собственной установки. Действующие домены, серверы, ключи и данные
пользователей не входят в репозиторий. Для раздельного размещения сервисов
используйте `DEPLOY_SPLIT.md`.

## Подготовка

Установите Git, Docker Engine и Compose plugin на выбранном сервере. Скопируйте
этот репозиторий на сервер и перейдите в его корневой каталог.

```bash
cp .env.example .env
chmod 600 .env
```

Заполните `.env` собственными значениями:

```dotenv
BOT_TOKEN=replace-with-your-bot-token
BOT_USERNAME=your_bot_username
ADMIN=0
DOMAIN=https://app.example.com
FLASK_HOST=0.0.0.0
FLASK_PORT=8000
DEBUG=false
JITSI_DOMAIN=meet.example.com
POSTGRES_DB=calls_tg
POSTGRES_USER=calls_tg
POSTGRES_PASSWORD=replace-with-a-unique-random-password
```

Значения `example.com` и `replace-with-*` не являются рабочими настройками.
`ADMIN=0` оставляет административный доступ ненастроенным; укажите собственный
Telegram ID, если он нужен. Compose формирует `DATABASE_URL` из `POSTGRES_*`.
Для пароля, содержащего зарезервированные символы URL, требуется корректное
кодирование перед использованием в строке подключения.

## Запуск и проверка

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl --fail http://localhost/health/live
curl --fail http://localhost/health/ready
```

Перед стартом `web` и `bot` сервис `migrate` выполняет `alembic upgrade head`.
Liveness проверяет веб-процесс, readiness — также соединение с БД.

Простой Compose публикует Nginx на порту 80. Для удалённых звонков настройте
HTTPS reverse proxy перед ним и задайте внешний HTTPS URL в `DOMAIN`.
Этот Compose не разворачивает Jitsi и TURN: их нужно установить отдельно,
проверить TLS, доступность медиапортов и маршрут между участниками.

## Обновление

Перед обновлением сохраните резервную копию БД, проверьте миграции и сохраните
тег предыдущего image. Получите проверенную версию кода и выполните:

```bash
bash scripts/deploy-local.sh
```

Скрипт обновляет application Compose. Не добавляйте Jitsi/TURN в ту же процедуру
обновления без необходимости прерывать конференции. В этой портфолио-версии
GitHub Actions выполняет только проверки; push не подключается к серверам.

## Обслуживание

```bash
docker compose logs --tail 100 web
docker compose logs --tail 100 bot
docker compose logs --tail 100 migrate
docker compose ps
docker compose down
```

Не используйте `docker compose down -v`, если нужно сохранить PostgreSQL volume.
Логи могут содержать ссылки на звонки и идентификаторы: не публикуйте их без
обезличивания. Backup-процедуры описаны в `BACKUP.md`.
