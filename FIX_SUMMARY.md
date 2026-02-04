# Исправление signalsbot по логам от 2026-02-04 09:49

## Проблема 1: TwelveData early-return с latency=0ms

### Симптомы:
- Первый тест запроса EURUSD проходит (HTTP 200 OK, цена есть)
- Следующий self-check через `DataRouter.get_price_async('EURUSD')` сразу возвращает `twelve_data_unavailable` с `latency=0ms` и без httpx HTTP log
- Это указывает на early-return до HTTP вызова

### Причина:
В `_make_request()` возвращался просто `None` без детального reason, что приводило к потере информации о реальной причине ошибки. Также не было детального логирования исключений.

### Исправления:

1. **`twelve_data_client.py` - `_make_request()`**:
   - Изменен возвращаемый тип: `Optional[Dict]` → `Tuple[Optional[Dict], Optional[str]]`
   - Все места возврата теперь возвращают `(data, reason)` tuple
   - Детальные reason коды:
     - `"cooldown"` - circuit breaker открыт
     - `"http_error_429"` - rate limit (429)
     - `"timeout"` - timeout exception
     - `"network_error"` - network/transport error
     - `"parse_error"` - JSON parse error или отсутствие поля price
     - `"no_key"` - invalid API key (401)
     - `"api_error_XXX"` - другие API ошибки
     - `"unknown_exception"` - неожиданные исключения
   - Добавлено логирование traceback для всех исключений

2. **`twelve_data_client.py` - `get_price()`**:
   - Обработка нового формата `(data, reason)` из `_make_request()`
   - Маппинг внутренних reason кодов на внешние
   - Детальное логирование исключений с traceback
   - Проверка circuit breaker ДО лога "[GET_PRICE] Requesting price..."

3. **`data_router.py` - `get_price_async()`**:
   - Обработка нового формата `(price, reason)` из `get_price()`
   - Нормализация reason кодов для backward compatibility
   - Детальное логирование исключений с traceback

### Результат:
- Лог "[GET_PRICE] Requesting price..." пишется ТОЛЬКО если будет реальный HTTP запрос
- Все ошибки имеют детальный reason код
- Все исключения логируются с типом, сообщением и traceback
- `latency=0ms` больше не появляется без реальной причины

## Проблема 2: CRYPTO constraint loop

### Симптомы:
- Канал GAINMUSE_CRYPTO находится под constraint "Wait 155 minutes"
- Бот продолжает каждые ~2 секунды писать "Skipping - constraint..." много раз
- Цикл attempts/while не прекращается при constraint

### Причина:
В `bot.py` при constraint делался `continue` и `sleep(2)`, что приводило к бесконечному циклу попыток.

### Исправления:

1. **`bot.py` - `generate_channel_signals()`**:
   - При constraint: `break` вместо `continue`
   - Логирование один раз: "Skipping channel - constraint: {reason}"
   - Немедленный выход из генерации по каналу
   - Убраны `sleep(2)` и повторные попытки при constraint

### Результат:
- При constraint: одно логирование и немедленный выход из цикла канала
- Интервал генерации (60s) соблюдается: один цикл → один проход по каналам → sleep 60s
- Нет спама логов при constraint

## Измененные файлы

1. **`twelve_data_client.py`**:
   - `_make_request()`: возвращает `(data, reason)` tuple
   - Все места возврата обновлены с детальными reason кодами
   - Добавлено логирование traceback для исключений

2. **`twelve_data_client.py`**:
   - `get_price()`: обработка нового формата из `_make_request()`
   - Детальное логирование исключений

3. **`data_router.py`**:
   - `get_price_async()`: обработка нового формата из `get_price()`
   - Детальное логирование исключений

4. **`bot.py`**:
   - `generate_channel_signals()`: `break` при constraint вместо `continue`

## Проверка

### Признаки успешной работы:

1. **TwelveData диагностика**:
   - ✅ Лог "[GET_PRICE] Requesting price..." только при реальном HTTP запросе
   - ✅ Детальные reason коды: `cooldown`, `http_error_429`, `timeout`, `network_error`, `parse_error`, `no_key`
   - ✅ Все исключения логируются с типом, сообщением и traceback
   - ✅ Нет `latency=0ms` без реальной причины

2. **CRYPTO constraint**:
   - ✅ При constraint: одно логирование и немедленный выход
   - ✅ Нет спама логов "Skipping - constraint..."
   - ✅ Интервал генерации соблюдается (60s)
