# boot.py
import network
import time
# import webrepl # Якщо використовуєте WebREPL
# webrepl.start()

SSID = ' '
PASSWORD = ' '

def connect_wifi(ssid, password):
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('Підключення до WiFi в boot.py...')
        sta_if.active(True)
        sta_if.connect(ssid, password)
        timeout_wifi = 20 # секунд
        while not sta_if.isconnected() and timeout_wifi > 0:
            print('.', end='')
            time.sleep(1)
            timeout_wifi -=1
    
    if sta_if.isconnected():
        print('\nПідключено до WiFi:', sta_if.ifconfig())
        return True
    else:
        print('\nНе вдалося підключитися до WiFi в boot.py.')
        return False

connect_wifi(SSID, PASSWORD)
# Не блокуйте boot.py нескінченними циклами, він має завершитися
