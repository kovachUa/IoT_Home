# main.py
import network
import time
import machine
import onewire
import ds18x20
import urequests
import ubinascii
import ota_updater # Імпортуємо наш модуль оновлення

# --- КОНФІГУРАЦІЯ ПРИСТРОЮ ---
NODE_NAME = "node_1" # Ім'я вашого вузла
DS18B20_PIN = 2          # GPIO пін для датчика DS18B20 (D4 на багатьох ESP8266)
DATA_SEND_INTERVAL = 0.5  # Інтервал відправки даних в секундах
OTA_CHECK_INTERVAL = 600 # Інтервал перевірки оновлень в секундах (1 година)
                           # Або 0, якщо перевіряти тільки при старті
# -----------------------------

# --- КОНФІГУРАЦІЯ МЕРЕЖІ ТА СЕРВЕРА (якщо не в boot.py) ---
# SSID = 'YOUR_SSID'
# PASSWORD = 'YOUR_WIFI_PASSWORD'
SERVER_DATA_URL = 'http://192.168.1.19:5002/data' # URL для відправки даних
# ---------------------------------------------------------

# Функція підключення до Wi-Fi (якщо не в boot.py)
def connect_wifi(ssid, password):
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('Підключення до WiFi...')
        sta_if.active(True)
        sta_if.connect(ssid, password)
        timeout_wifi = 20
        while not sta_if.isconnected() and timeout_wifi > 0:
            print('.', end='')
            time.sleep(1)
            timeout_wifi -=1
        if sta_if.isconnected():
            print('\nПідключено до WiFi:', sta_if.ifconfig())
            return True
        else:
            print('\nНе вдалося підключитися до WiFi.')
            return False
    return True

# Якщо ви винесли підключення в boot.py, ця частина не потрібна тут
# if not connect_wifi(SSID, PASSWORD):
#     print("Не вдалося підключитися до Wi-Fi, перезавантаження через 10 секунд...")
#     time.sleep(10)
#     machine.reset()

# Перевірка Wi-Fi з'єднання
sta_if = network.WLAN(network.STA_IF)
if not sta_if.isconnected():
    print("Wi-Fi не підключено. Спробуйте перезавантажити або перевірити boot.py.")
    # Можна додати логіку спроби перепідключення або очікування
else:
    print('WiFi підключено:', sta_if.ifconfig())


# --- Отримання MAC-адреси ---
try:
    raw_mac = sta_if.config('mac')
    mac_address = ubinascii.hexlify(raw_mac).decode()
    print('MAC:', mac_address)
except Exception as e:
    print(f"Помилка отримання MAC: {e}")
    mac_address = "unknown_mac" # Заглушка, якщо не вдалося отримати


# --- Ініціалізація DS18B20 ---
ds_sensor = None
roms = []
try:
    dat_pin = machine.Pin(DS18B20_PIN)
    ds_sensor = ds18x20.DS18X20(onewire.OneWire(dat_pin))
    roms = ds_sensor.scan()
    if roms:
        print('Знайдено DS18B20:', [ubinascii.hexlify(rom).decode() for rom in roms])
    else:
        print('DS18B20 датчики не знайдено.')
except Exception as e:
    print(f"Помилка ініціалізації DS18B20: {e}")


# --- OTA ОНОВЛЕННЯ ПРИ СТАРТІ ---
# Перевіряємо оновлення тільки якщо є Wi-Fi
if sta_if.isconnected():
    print("--- Перевірка оновлень OTA при старті ---")
    # Якщо ota_updater.check_for_updates() викликає machine.reset(),
    # то код нижче не виконається у випадку успішного оновлення.
    update_result = ota_updater.check_for_updates()
    if update_result is True: # Була спроба оновлення (успішна чи ні, але reset має відбутись при успіху)
        print("Процес оновлення завершено (або була спроба).") # Цей рядок не має виконатись при успішному reset
    elif update_result is False:
        print("Оновлення не потрібні або не вдалися без перезавантаження.")
    print("--- Завершення перевірки OTA ---")
else:
    print("Немає Wi-Fi з'єднання, пропуск перевірки OTA.")

# --- ОСНОВНИЙ ЦИКЛ ПРОГРАМИ ---
last_ota_check_time = time.time()

print(f"\n--- Початок основного циклу програми (Версія: {ota_updater.get_local_version_info().get('version')}) ---")

while True:
    current_time = time.time()
    temperatures = {}

    if ds_sensor and roms:
        try:
            ds_sensor.convert_temp()
            time.sleep_ms(750) # Час на конвертацію температури
            for rom in roms:
                try:
                    temp = ds_sensor.read_temp(rom)
                    # Перевірка на валідність температури (85 - типове значення помилки для DS18B20)
                    if temp is not None and temp != 85.0 and temp != -127: 
                        temperatures[ubinascii.hexlify(rom).decode()] = round(temp, 2)
                    else:
                        print(f"Помилка читання або невалідна температура з датчика {ubinascii.hexlify(rom).decode()}: {temp}")
                        # Можна додати лічильник помилок і пересканувати датчики, якщо помилок багато
                except Exception as e_read:
                    print(f"Помилка читання температури з {ubinascii.hexlify(rom).decode()}: {e_read}")
        except Exception as e_conv:
            print(f"Помилка конвертації температури DS18B20: {e_conv}")
            # Спробувати пересканувати датчики, якщо виникають проблеми
            time.sleep(2) # Невелика затримка перед повторним скануванням
            try:
                roms = ds_sensor.scan()
                if roms:
                    print(f"Датчики DS18B20 перескановано: {[ubinascii.hexlify(rom).decode() for rom in roms]}")
                else:
                    print("Датчики DS18B20 все ще не знайдено після пересканування.")
            except Exception as e_scan:
                print(f"Помилка при повторному скануванні DS18B20: {e_scan}")
    elif ds_sensor and not roms: # Якщо сенсор є, а ромів немає - спробувати сканувати
        print("Датчики DS18B20 не виявлено, спроба сканування...")
        try:
            roms = ds_sensor.scan()
            if roms: print(f"Знайдено DS18B20: {[ubinascii.hexlify(rom).decode() for rom in roms]}")
        except Exception as e:
            print(f"Помилка сканування DS18B20: {e}")


    # Відправка даних на сервер, якщо є Wi-Fi
    if sta_if.isconnected():
        payload = {
            "mac": mac_address,
            "name": NODE_NAME,
            "data": temperatures if temperatures else {"status": "no_sensor_data" if not roms else "reading_error"}
        }
        
        print(f"Відправка даних: {payload}")
        try:
            response = urequests.post(SERVER_DATA_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
            print(f"Відповідь сервера ({response.status_code}): {response.text}")
            response.close()
        except Exception as e:
            print(f"Помилка відправки даних на сервер: {e}")
            # Спроба перепідключення до Wi-Fi, якщо помилка пов'язана з мережею
            if not sta_if.isconnected():
                print("Втрачено Wi-Fi з'єднання, спроба перепідключення...")
                # connect_wifi(SSID, PASSWORD) # Розкоментуйте, якщо SSID і PASSWORD визначені тут
    else:
        print("Немає Wi-Fi з'єднання, дані не відправлено.")
        # Спроба перепідключення до Wi-Fi
        # connect_wifi(SSID, PASSWORD) # Розкоментуйте, якщо SSID і PASSWORD визначені тут

    # Періодична перевірка оновлень OTA (якщо налаштовано)
    if OTA_CHECK_INTERVAL > 0 and (current_time - last_ota_check_time) > OTA_CHECK_INTERVAL:
        if sta_if.isconnected():
            print(f"--- Періодична перевірка оновлень OTA (через {OTA_CHECK_INTERVAL}с) ---")
            ota_updater.check_for_updates() # Якщо буде оновлення, пристрій перезавантажиться
            print("--- Завершення періодичної перевірки OTA ---")
        else:
            print("Немає Wi-Fi з'єднання, пропуск періодичної перевірки OTA.")
        last_ota_check_time = current_time
    
    print(f"Наступна відправка даних / перевірка через ~{DATA_SEND_INTERVAL}с.")
    print("-" * 30)
    time.sleep(DATA_SEND_INTERVAL)
