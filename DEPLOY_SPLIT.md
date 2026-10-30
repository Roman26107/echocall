# EchoCall: раздельное размещение backend и Telegram-сервисов

Ниже приведена схема для собственной установки, а не описание действующих
серверов. Все адреса `*.example.com` и IP из env-примеров необходимо заменить.
Имена ролей `rf` и `foreign` сохранены для совместимости со скриптами.
Jitsi/TURN разворачиваются отдельно; настройку необязательного UI overlay
см. в `docker/jitsi-web/README.md`.

## 1. Итоговая архитектура

```text
Пользователи РФ
  └─ HTTPS app.example.com
       └─ RF VPS
          ├─ Nginx
           ├─ Flask web
          ├─ Internal API /internal/v1
          ├─ PostgreSQL (только Docker data network)
          ├─ Redis (только Docker data network)
          └─ migrations / backups

Foreign VPS
  ├─ Telegram bot (polling api.telegram.org)
  ├─ Telegram Gateway (HTTPS, allow только RF IP)

RF VPS также запускает Jitsi Web / Prosody / Jicofo / JVB и coturn; браузерный
медиатрафик не проходит через foreign VPS.

Foreign bot ──HTTPS + bearer + IP allowlist──> RF Internal API
RF web      ──HTTPS + bearer + IP allowlist──> Foreign Telegram Gateway
```

Бот никогда не получает `DATABASE_URL`. RF web никогда не получает `BOT_TOKEN`.
Jitsi/TURN управляются отдельными Compose-проектами на RF и не включены в
application Compose, поэтому deploy приложения не перезапускает конференции.

## 2. API и модель безопасности

### RF Internal API

`POST /internal/v1/operations/<operation>` — только операции из явного allowlist
в `shared/services/*`; произвольные SQL, импорт или имя Python-функции выполнить
нельзя. Формат:

```json
{"args": [], "kwargs": {"telegram_id": 123}}
```

Ответ:

```json
{"ok": true, "result": {}, "request_id": "uuid"}
```

Для mutation-запросов обязателен `Idempotency-Key`. Результат хранится в Redis
24 часа. Клиент выставляет `X-Request-ID`, использует короткий timeout и не
повторяет мутации автоматически. Ошибки имеют стабильный `error.code`.
Если Redis недоступен, mutation fail-closed с `503`, чтобы повтор запроса не
создал дубликаты; read-only операции продолжают работать.

### Telegram Gateway

Gateway предоставляет только:

- `POST /internal/v1/telegram/send-message`;
- `POST /internal/v1/telegram/edit-message-text`.

В payload разрешены `chat_id`, `message_id`, `text`, `parse_mode` и валидная
inline keyboard. Telegram token остаётся только на foreign VPS.

Оба API защищаются одновременно:

1. TLS с проверяемым сертификатом;
2. разными bearer secrets длиной от 32 случайных байт;
3. Nginx `allow <peer-public-IP>; deny all`;
4. UFW allow только peer IP;
5. лимитом body 64 KiB, rate limit и короткими proxy timeout.

WireGuard остаётся preferred route, если UDP между провайдерами двусторонний.
Если handshake не устанавливается, используйте restricted reverse-SSH fallback:
foreign VPS сам подключается к RF по TCP/22 и публикует foreign Caddy только на
закреплённом gateway RF app-сети `${TUNNEL_GATEWAY_IP}:8443` (по умолчанию
`172.29.0.1:8443`). В таком режиме задайте на RF
`TELEGRAM_GATEWAY_URL=https://gateway.example.com:8443`; Compose сопоставляет
это имя с этим gateway, сохраняя TLS SNI и проверку сертификата. Перед первым
запуском убедитесь, что `APP_NETWORK_SUBNET` не пересекается с существующими
Docker/VPN сетями; после настройки tunnel не меняйте subnet без синхронного
изменения SSH-конфигурации. Remote forward
не должен слушать `0.0.0.0`; отдельному SSH-пользователю разрешается только
`PermitListen <TUNNEL_GATEWAY_IP>:8443`, без shell/TTY и без других forward.
Если UFW активен, разрешите доступ к listener только из закреплённой app-сети и
только через её Docker bridge (имя bridge вычисляется на RF сервере):

```bash
bridge="br-$(docker network inspect -f '{{.Id}}' echocall-rf_app | cut -c1-12)"
sudo ufw allow in on "$bridge" from 172.29.0.0/24 to 172.29.0.1 \
  port 8443 proto tcp comment 'EchoCall app to restricted gateway tunnel'
```

Подставьте значения `APP_NETWORK_SUBNET` и `TUNNEL_GATEWAY_IP`, если меняли
defaults. Не добавляйте публичное правило на `8443/tcp`.

Если прямой foreign → RF TLS также нестабилен, тот же SSH-процесс может создать
local forward на закреплённом gateway foreign app-сети (по умолчанию
`172.30.0.1:8444`) к `127.0.0.1:443` RF сервера. Foreign Compose сопоставляет
`api.example.com` с этим gateway, поэтому SNI и проверка сертификата не
отключаются. Для SSH-пользователя одновременно задайте только
`PermitOpen 127.0.0.1:443`; не разрешайте произвольный local forwarding.
На foreign UFW разрешите `172.30.0.0/24 → 172.30.0.1:8444` только на bridge
`echocall-foreign_app`, аналогично RF-правилу выше. Полная пара forward:

```text
-R 172.29.0.1:8443:127.0.0.1:443
-L 172.30.0.1:8444:127.0.0.1:443
```

В fallback-режиме установите `INTERNAL_API_URL=https://api.example.com:8444`.
Также установите `INTERNAL_API_CONNECT_IP=172.30.0.1`; при прямом HTTPS эта
переменная должна содержать публичный RF IP.

## 3. Jitsi/TURN на RF edge

RF Nginx завершает публичный TLS для `meet.example.com`. Отдельный upstream
docker-jitsi-meet подключает только сервис `web` к external-сети
`echocall-rf_app` с alias `jitsi-web`; его HTTP-порт наружу не публикуется.

Публичные media bindings на RF:

- JVB: `10000/udp`, `JVB_ADVERTISE_IPS=<RF_PUBLIC_IP>`;
- coturn: `3478/udp+tcp`, `5349/tcp` и ограниченный UDP relay range;
- одинаковый `TURN_CREDENTIALS` в Jitsi и coturn, только вне Git/логов.

До DNS cutover новый stack проверяется на RF локально; старый media stack не
останавливается до успешного звонка с двух устройств без VPN.

## 4. DNS и сертификаты

До переключения создайте DNS-only A records:

| Имя | Адрес |
| --- | --- |
| `staging-app.example.com` | RF VPS (удалить после cutover) |
| `app.example.com` | RF VPS |
| `api.example.com` | RF VPS |
| `gateway.example.com` | foreign VPS |
| `meet.example.com` | RF VPS после preflight |
| `turn.example.com` | RF VPS, DNS-only, после preflight |

На RF разместите сертификаты:

```text
/etc/echocall/certs/app/{fullchain.pem,privkey.pem}
/etc/echocall/certs/api/{fullchain.pem,privkey.pem}
/etc/echocall/certs/meet/{fullchain.pem,privkey.pem}
```

ACME challenge webroot хранится в `/var/www/echocall-acme` и монтируется в
Nginx read-only. Certbot renewal hook должен копировать обновлённые сертификаты
в `/etc/echocall/certs/{app,api}` и выполнить `docker compose ... exec nginx
nginx -s reload`; приватные ключи имеют права `600`.

На foreign TLS завершает уже работающий host Caddy. Gateway публикуется только
как `127.0.0.1:8010`; добавьте в `/opt/reverse-proxy/Caddyfile`:

```caddy
gateway.example.com {
    # 127.0.0.1 нужен только для restricted reverse-SSH fallback.
    @rf remote_ip <RF_PUBLIC_IP> 127.0.0.1
    handle @rf {
        reverse_proxy 127.0.0.1:8010
    }
    respond 403
}
```

Caddy автоматически получает и обновляет сертификат. Не публикуйте порт 8010
наружу и не добавляйте отдельный TLS proxy рядом с Caddy.

## 5. Переменные и запуск

Никогда не коммитьте рабочие env:

```bash
cp .env.rf.example .env.rf
cp .env.foreign.example .env.foreign
chmod 600 .env.rf .env.foreign
```

`APP_IMAGE` задавайте immutable tag текущего Git commit, например
`echocall-rf-app:release-1` и `echocall-foreign-app:release-1`. Все Python-сервисы
одной роли используют один и тот же image. `deploy-role.sh` строит его ровно
один раз, затем запускает Compose с `--no-build`; для rollback верните предыдущий
tag и снова выполните role deploy. Не используйте `latest` в production.

Сгенерируйте **два разных** секрета, например `openssl rand -hex 32`:

- `INTERNAL_API_TOKEN` одинаковый только в `.env.rf` и `.env.foreign`;
- `TELEGRAM_GATEWAY_TOKEN` одинаковый только в `.env.rf` и `.env.foreign`.

Проверка и запуск RF:

```bash
docker compose --env-file .env.rf -f docker-compose.rf.yml config
bash scripts/deploy-role.sh rf
```

Foreign:

```bash
docker compose --env-file .env.foreign -f docker-compose.foreign.yml config
bash scripts/deploy-role.sh foreign
```

Монолит остаётся обратно совместимым и запускается прежней командой
`docker compose up -d`; по умолчанию `DATA_ACCESS_MODE=direct`.

## 6. Firewall

Сначала убедитесь, что текущая SSH-сессия и резервный SSH-доступ работают. Не
включайте UFW вслепую.

RF VPS (подставить foreign IP и реальный SSH source/range):

```bash
sudo ufw allow from <ADMIN_IP> to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 10000/udp
sudo ufw allow 3478/tcp
sudo ufw allow 3478/udp
sudo ufw allow 5349/tcp
# Открыть настроенный coturn UDP relay range, например 49160:49200/udp.
# Дополнительная защита api hostname; оба vhost используют 443, поэтому
# окончательное IP-ограничение делает Nginx.
sudo ufw enable
```

Foreign VPS:

```bash
sudo ufw allow from <ADMIN_IP> to any port 22 proto tcp
# Gateway идёт через существующий Caddy на 443; порт 8010 только loopback.
# Существующие Jitsi/TURN правила НЕ удалять:
# 10000/udp, 3478/tcp+udp, 5349/tcp+udp, TURN relay range.
```

PostgreSQL `5432` и Redis `6379` не публикуются Compose и не открываются UFW.

## 7. Миграция PostgreSQL с минимальным downtime

1. Снизить DNS TTL `app` до 300 минимум за сутки.
2. Поднять RF stack и проверить health без переключения `app`.
3. Сделать предварительный backup текущей БД и тестовый restore на RF.
4. Проверить количество строк по таблицам и `alembic current`.
5. Объявить короткое окно обслуживания; остановить **только старые web и bot**,
   чтобы прекратить записи. Jitsi/TURN не останавливать.
6. Выполнить финальный `pg_dump` custom format:

```bash
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > echocall-final.dump
```

7. Безопасно передать dump на RF, проверить checksum, восстановить в пустую БД:

```bash
docker compose --env-file .env.rf -f docker-compose.rf.yml exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner < echocall-final.dump
docker compose --env-file .env.rf -f docker-compose.rf.yml run --rm migrate
```

8. Поднять foreign Gateway и RF stack. Сначала проверить API, затем запустить bot
   в remote mode и только после этого переключить DNS `app`.
9. Старую БД оставить выключенной и read-only как rollback copy минимум 7 дней.

Dump содержит персональные данные и access tokens: хранить зашифрованно, права
`600`, после принятого retention безопасно удалить.

## 8. Проверки

Короткие команды (каждая имеет timeout):

```bash
bash scripts/smoke-role.sh rf
bash scripts/smoke-role.sh foreign
curl --connect-timeout 5 --max-time 10 -fsS https://app.example.com/health/ready
```

Internal API/Gateway health проверяются скриптом внутри контейнерной сети. Это
ожидаемо: публичный Nginx отклоняет проверку с любого IP, кроме peer-сервера.

Проверить сценарии: `/start`, профиль, настройки, контакты, blacklist, начало
звонка, ответ с web, status polling, завершение звонка и обновление обоих
Telegram-сообщений. Не выводить request payload, bearer token или call URL в логи.

## 9. Rollback

До появления новых записей на RF:

1. остановить RF web/internal-api и foreign remote bot;
2. вернуть DNS `app` на старый VPS;
3. запустить старый монолит с сохранённым `.env` и volume;
4. проверить один звонок.

После появления записей на RF нельзя просто включить старую БД: получится
split-brain и потеря новых данных. Сначала остановить записи, сделать обратный
dump RF → old PostgreSQL, проверить checksum/counts и только затем возвращать DNS.

## 10. CI

Workflow `.github/workflows/ci.yml` запускает Python- и JavaScript-тесты и
валидацию всех трёх Compose-конфигураций. Он не содержит SSH-деплоя и не требует
production-секретов. Скрипты развёртывания выполняются вручную на собственной
инфраструктуре после проверки конфигурации.
