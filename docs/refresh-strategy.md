# Refresh strategy: why no auto-refresh, and what to do instead

> [!NOTE]
> В этом документе под «refresh» понимается переиздание короткоживущей
> сессии `_sm_sess`, а не классический OAuth `refresh_token`. Подробный
> разбор протокола — в [gigachat-auth-refresh-flow.md](gigachat-auth-refresh-flow.md).

## TL;DR

- В этом клиенте **нет** auto-refresh `_sm_sess`. Намеренно.
- Вместо него на старте выполняется **preflight-проверка** через
  `GET /api/check`, и если токен истёк, MCP-сервер сразу возвращает
  `AuthExpiredError` с понятной инструкцией.
- Полноценный refresh требует SSO-редирект через Keymaster, который
  нельзя воспроизвести в headless/HTTP-клиенте.

## Почему auto-refresh невозможен из MCP-клиента

Из [gigachat-auth-refresh-flow.md](gigachat-auth-refresh-flow.md):

1. В HAR нет отдельного HTTP-endpoint вида `POST /refresh-token`.
2. Refresh сессии завязан на SSO-редирект через Keymaster:
   - `POST /api/keymaster/auth/state` с `lightAuthorize=REFRESH`;
   - редирект на `authUrl` (Sber ID);
   - возврат на `/oidc-result?code=...&state=...`;
   - восстановление состояния из IndexedDB (`authHandoffStorage`);
   - браузер получает новую короткоживущую cookie `_sm_sess`.
3. В headless-клиенте у нас нет:
   - `IndexedDB` для сохранения `authHandoff`;
   - JavaScript-движка для обработки `lightAuthorize` и связанных условий
     (например, подавление auto-refresh после failed login / manual logout);
   - cookies с флагами `HttpOnly` / `SameSite`, которые браузер
     проставляет автоматически.

Попытка имитировать весь этот поток из Python привела бы к хрупкой
обвязке поверх Keymaster, которая ломалась бы на каждом изменении их
JS-клиента. Вместо этого мы делаем явную диагностику и просим
пользователя обновить cookie в браузере — это занимает 30 секунд.

## Что делает preflight

Файл: [`src/gigaplexity/preflight.py`](../src/gigaplexity/preflight.py).

| Шаг | Что проверяется | Если не ОК |
|-----|----------------|------------|
| 1. Локальный JWT | `exp` из `_sm_sess` vs `now + GIGACHAT_PREFLIGHT_SKEW` | `should_refresh=True`, без сети |
| 2. `GET /api/check` | HTTP 200 + `result=true` | `should_refresh=True` |
| 2'. Сетевая ошибка | `httpx.HTTPError` | `ok=False`, `should_refresh=False` (warning) |

Сетевые ошибки **не валят** старт MCP-сервера — лучше дать
пользователю шанс выполнить реальный запрос и увидеть настоящую ошибку.

`preflight` вызывается ровно один раз — при первом обращении к
`_get_client()`. Дальнейшие запросы идут как обычно. Если в середине
сессии приходит HTTP 401/403 или body с маркерами `token has expired`
/ `GC-ATT-E005`, клиент сам поднимает `AuthExpiredError`.

## Что делать при `AuthExpiredError`

Полное сообщение уже встроено в исключение. Короткая версия:

1. Откройте [giga.chat](https://giga.chat) в браузере, в котором
   авторизованы.
2. `F12` → вкладка **Network**.
3. Отправьте любое сообщение в чат.
4. Найдите запрос к `https://giga.chat/api/giga-back-web/api/v0/sessions/request`.
5. Скопируйте полное значение заголовка `Cookie`.
6. Замените `GIGACHAT_COOKIES` (или `GIGACHAT_SM_SESS`) в конфиге
   MCP-клиента на новую строку.
7. Перезапустите MCP-сервер.

Для вложений шаги те же — но в HAR лучше смотреть запрос
`/api/attachments-upload/api/v0/gc/otr/...`, потому что attachments
могут использовать дополнительные browser-issued токены.

> [!WARNING]
> HAR-файлы содержат cookies, идентификаторы сессий и токены. **Не
> публикуйте** их и **вычищайте** cookies / `Authorization` / `Cookie`
> заголовки перед шерингем в issue / PR.

## Настройки

| Переменная | Назначение | По умолчанию |
|------------|------------|--------------|
| `GIGACHAT_PREFLIGHT_ON_START` | Запускать `GET /api/check` при первом обращении к клиенту | `true` |
| `GIGACHAT_PREFLIGHT_SKEW` | Запас в секундах до `exp`, после которого токен считается истёкшим локально | `60` |

`GIGACHAT_PREFLIGHT_ON_START=false` отключает только сетевую проверку.
Локальная JWT-проверка остаётся — она дешёвая и не делает HTTP-запросов.

## Что **не** делается (и почему это правильно)

- Не запускается headless-браузер (puppeteer / playwright) ради одного
  refresh. Лишний десяток мегабайт зависимостей и секунды старта ради
  операции, которая случается раз в несколько минут — плохая сделка.
- Не хранится `refresh_token` — его просто нет в протоколе GigaChat.
- Не лезем в IndexedDB / Sber ID в обход — это сломает сессию активного
  пользователя и не принесёт ничего, кроме блокировки.
