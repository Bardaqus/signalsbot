# Исправление Circuit Breaker для TwelveData

## Проблема
При `twelve_data_unavailable` бот продолжал делать `get_price` для каждой пары в каждом FOREX канале (FOREX_DEGRAM, затем FOREX_LINGRID), что видно по логам: attempt 1/8..8/8 и снова 1/8..8/8.

## Решение

### 1. Глобальный Circuit Breaker API (`twelve_data_client.py`)

Добавлены явные методы для работы с circuit breaker:
- `before_request() -> bool` - проверка разрешения запроса (возвращает False если breaker открыт)
- `on_success()` - запись успешного запроса и сброс breaker
- `on_failure(reason, exception)` - запись ошибки и открытие breaker при необходимости

**Параметры circuit breaker:**
- `FAIL_THRESHOLD = 3` - открывается после 3 последовательных ошибок
- `COOLDOWN_START = 120s` - начальный cooldown (2 минуты)
- `COOLDOWN_MAX = 900s` - максимальный cooldown (15 минут)
- `BACKOFF_MULT = 2` - экспоненциальный множитель

### 2. Изменение `get_price()` (`twelve_data_client.py`)

**До:**
```python
async def get_price(...) -> Optional[float]:
    if self._is_circuit_breaker_open():
        return None  # Неясная причина
    print("[GET_PRICE] Requesting price...")  # Логируется даже при breaker open
    ...
```

**После:**
```python
async def get_price(...) -> Tuple[Optional[float], Optional[str]]:
    if not self.before_request():
        return None, "twelve_data_cooldown"  # Явная причина
    print("[GET_PRICE] Requesting price...")  # Логируется ТОЛЬКО если будет HTTP запрос
    ...
    return price, None  # или None, "twelve_data_unavailable"
```

**Ключевые изменения:**
- Возвращает `(price, reason)` tuple вместо просто `price`
- Проверка breaker ДО лога "[GET_PRICE] Requesting price..."
- Явный reason `"twelve_data_cooldown"` при открытом breaker
- Вызов `on_success()` при успехе
- Вызов `on_failure(reason, exception)` при ошибках (429, timeout, network, etc.)

### 3. Обновление `data_router.py`

**Изменения:**
- Обработка нового формата возврата `(price, reason)` из `get_price()`
- Нормализация reason кодов: `"twelve_data_cooldown"` → `"twelve_data_cooldown"`
- Исправлены синхронные вызовы через `asyncio.run()` для распаковки tuple

### 4. Логика генерации сигналов (`bot.py`)

**Добавлено:**
- Глобальный флаг `forex_unavailable` для отслеживания недоступности FOREX источника
- Проверка `forex_unavailable` перед обработкой FOREX каналов
- При `reason == "twelve_data_cooldown"` или `"twelve_data_unavailable"` для FOREX:
  - `break` из цикла генерации для текущего канала
  - Установка `forex_unavailable = True`
  - Пропуск остальных FOREX каналов в этом цикле
- Логирование один раз на канал: "TwelveData cooldown active, skipping channel"

**Пример логики:**
```python
for config in channel_configs:
    # Skip FOREX channels if FOREX source is unavailable
    if asset_type == "FOREX" and forex_unavailable:
        print(f"⏸️ {channel_name}: Skipping - TwelveData cooldown active")
        continue
    
    while signals_generated < signals_needed:
        rt_price, reason, source = await data_router.get_price_async(sym)
        
        if rt_price is None:
            if reason == "twelve_data_cooldown" and asset_type == "FOREX":
                forex_unavailable = True
                print(f"⏸️ {channel_name}: TwelveData cooldown active, skipping channel")
                break  # Прекратить попытки по текущему каналу
```

## Результат

### До исправления:
```
[GENERATE_SIGNALS] FOREX_DEGRAM: Analyzing EURUSD (attempt 1/8)...
[GET_PRICE] Requesting price for EURUSD...
[DATA_ROUTER] EURUSD: price=None, reason=twelve_data_unavailable
[GENERATE_SIGNALS] FOREX_DEGRAM: Analyzing GBPUSD (attempt 2/8)...
[GET_PRICE] Requesting price for GBPUSD...
... (8 попыток)
[GENERATE_SIGNALS] FOREX_LINGRID: Analyzing EURUSD (attempt 1/8)...
[GET_PRICE] Requesting price for EURUSD...
... (8 попыток снова)
```

### После исправления:
```
[GENERATE_SIGNALS] FOREX_DEGRAM: Analyzing EURUSD (attempt 1/8)...
[DATA_ROUTER] EURUSD: price=None, reason=twelve_data_cooldown
⏸️ FOREX_DEGRAM: TwelveData cooldown active, skipping channel (will skip remaining FOREX channels)
[GENERATE_SIGNALS] FOREX_LINGRID: Skipping - TwelveData cooldown active (FOREX source unavailable)
```

## Измененные файлы

1. **`twelve_data_client.py`**:
   - Добавлены методы `before_request()`, `on_success()`, `on_failure()`
   - `get_price()` теперь возвращает `(price, reason)` tuple
   - Проверка breaker ДО лога "[GET_PRICE] Requesting price..."
   - Все ошибки записываются через `on_failure()` с явным reason

2. **`data_router.py`**:
   - Обновлена обработка нового формата `(price, reason)` из `get_price()`
   - Исправлены синхронные вызовы для распаковки tuple

3. **`bot.py`**:
   - Добавлен флаг `forex_unavailable` для пропуска FOREX каналов
   - При cooldown/unavailable для FOREX: `break` из цикла канала
   - Пропуск остальных FOREX каналов в цикле генерации

## Проверка

### Признаки успешной работы:
- ✅ При circuit breaker open: "[GET_PRICE] Requesting price..." НЕ логируется
- ✅ При cooldown: бот прекращает попытки по текущему каналу (break)
- ✅ При cooldown: остальные FOREX каналы пропускаются в этом цикле
- ✅ Логирование один раз на канал, без спама на каждую пару
- ✅ Reason коды: `"twelve_data_cooldown"` при открытом breaker
