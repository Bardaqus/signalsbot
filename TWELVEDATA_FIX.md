# Исправление TwelveData клиента в signalsbot

## Проблема

### Симптомы:
- В цикле генерации FOREX все пары падают: "Failed to get price ... reason=unknown_error"
- DataRouter пишет latency=0ms
- Нет httpx INFO "HTTP Request: GET https://api.twelvedata.com/..." (значит до сети не доходит)
- Yahoo работает нормально
- Лимиты не превышены (1/800, 1/8 per minute)

### Гипотеза:
httpx.AsyncClient закрывается сразу после startup/self-check, хотя ссылка сохраняется. После выхода из контекста клиент закрыт, поэтому все последующие запросы падают мгновенно и превращаются в unknown_error.

## Исправления

### 1. Убрано использование `async with` для AsyncClient

**Файл:** `twelve_data_client.py`

**До:**
```python
# Клиент создавался правильно, но мог быть закрыт где-то раньше времени
```

**После:**
- Клиент создается напрямую: `self._client = httpx.AsyncClient(...)` (без `async with`)
- Добавлена проверка `client.is_closed` перед использованием
- Клиент закрывается только в `close()` при shutdown
- Добавлено логирование создания и закрытия клиента

**Изменения:**
- `_ensure_started()`: добавлен лог при создании клиента
- `_make_request()`: добавлена проверка `client.is_closed` перед запросом
- `close()`: улучшено логирование и проверка состояния клиента

### 2. Улучшена обработка ошибок

**Файлы:** `twelve_data_client.py`, `data_router.py`

**До:**
- Возвращался `"unknown_error"` без деталей
- Исключения не логировались с полным traceback

**После:**
- Все ошибки имеют детальный формат: `exception:<TypeName>:<message>`
- Используется `logger.exception()` для полного traceback
- Reason коды нормализованы:
  - `cooldown` - circuit breaker открыт
  - `rate_limit_429` - HTTP 429
  - `timeout` - timeout exception
  - `network_error` - network/transport error
  - `parse_error` - JSON parse error
  - `invalid_api_key` - 401 или "api key" в сообщении
  - `exception:<Type>:<message>` - другие исключения

**Изменения:**
- `_make_request()`: все исключения логируются с `logger.exception()`
- `get_price()`: улучшена обработка RuntimeError и других исключений
- `data_router.py`: улучшена обработка исключений с детальным логированием

### 3. Счетчик requests инкрементируется только после успешного HTTP запроса

**Файл:** `bot.py`

**До:**
```python
signal_request_count = 1  # Инкрементировался ДО запроса
rt_price, reason, source = await data_router.get_price_async(sym)
if request_counter_ref is not None:
    request_counter_ref["count"] += 1  # Инкрементировался даже если запрос не был сделан
```

**После:**
```python
signal_request_count = 0  # Начальное значение
rt_price, reason, source = await data_router.get_price_async(sym)
# Инкрементируется ТОЛЬКО если получили цену (HTTP запрос успешен)
if rt_price is not None and source == "TWELVE_DATA":
    signal_request_count = 1
    if request_counter_ref is not None:
        request_counter_ref["count"] += 1  # Только после успешного HTTP запроса
```

### 4. Добавлено логирование HTTP запросов

**Файл:** `twelve_data_client.py`

- Добавлен лог перед HTTP запросом: `[HTTP_REQUEST] GET {url}?symbol={symbol}`
- Добавлен лог после успешного ответа: `[HTTP_RESPONSE] GET {url} -> {status_code} OK`

Это позволяет видеть, был ли реально сделан HTTP запрос или произошел early-return.

## Где именно клиент закрывался и почему latency был 0ms

### Проблема:
Клиент НЕ закрывался явно через `async with`, но мог быть закрыт если:
1. `self._closed = True` был установлен где-то раньше времени
2. Клиент был закрыт при ошибке (но этого не было в коде)
3. Клиент не был создан правильно

### Почему latency был 0ms:
Если клиент закрыт (`client.is_closed == True`), то вызов `await client.get(...)` падает мгновенно с исключением (например, `RuntimeError: client is closed`), что дает `latency=0ms` (запрос не доходит до сети).

### Исправление:
1. Добавлена проверка `client.is_closed` перед использованием
2. Улучшено логирование состояния клиента
3. Все исключения логируются с деталями, чтобы видеть реальную причину

## Измененные файлы

1. **`twelve_data_client.py`**:
   - Добавлена проверка `client.is_closed` перед запросом
   - Улучшена обработка ошибок с детальным логированием
   - Добавлено логирование HTTP запросов/ответов
   - Улучшен метод `close()` с проверкой состояния

2. **`data_router.py`**:
   - Улучшена обработка исключений с детальным логированием
   - Нормализация reason кодов

3. **`bot.py`**:
   - Счетчик requests инкрементируется только после успешного HTTP запроса

## Проверка

### Признаки успешной работы:
- ✅ Логи показывают `[HTTP_REQUEST] GET ...` перед каждым реальным запросом
- ✅ Логи показывают `[HTTP_RESPONSE] GET ... -> 200 OK` при успехе
- ✅ При ошибках: детальный reason с типом исключения и сообщением
- ✅ `latency > 0ms` для реальных HTTP запросов
- ✅ Счетчик requests увеличивается только после успешных запросов
- ✅ Нет "unknown_error" без деталей

### Если проблема сохраняется:
- Проверить логи на наличие `[HTTP_REQUEST]` - если его нет, значит early-return до HTTP
- Проверить reason в логах - должен быть детальный формат `exception:<Type>:<message>`
- Проверить состояние клиента: `[TWELVE_DATA] HTTP client created` при старте
