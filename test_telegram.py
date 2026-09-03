import requests
import json
import time

TOKEN = "8968886332:AAGdmdP179wk2-dPOfLrfkmNwX9sIcBhGI0"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

print("=== PRUEBA DE CONEXIÓN TELEGRAM ===")
print("El bot está escuchando. Manda cualquier mensaje a tu bot en Telegram.")
print("Presiona Ctrl+C para detener.\n")

offset = 0

try:
    while True:
        try:
            resp = requests.get(
                f"{BASE_URL}/getUpdates",
                params={"offset": offset, "timeout": 10},
                timeout=15
            )
            
            if resp.status_code != 200:
                print(f"Error HTTP {resp.status_code}: {resp.text}")
                time.sleep(2)
                continue
                
            data = resp.json()
            if not data.get("ok"):
                print("Error de API:", data)
                time.sleep(2)
                continue
                
            updates = data.get("result", [])
            for upd in updates:
                offset = upd["update_id"] + 1
                
                message = upd.get("message", {})
                text = message.get("text", "<Sin texto>")
                user = message.get("from", {}).get("first_name", "Usuario")
                
                print(f"\n[+] Mensaje recibido de {user}:")
                print(f"    Texto: {text}")
                print(f"    JSON Crudo: {json.dumps(upd, ensure_ascii=False)}")
                
        except requests.exceptions.RequestException as e:
            print(f"Error de conexión: {e}")
            time.sleep(2)
            
except KeyboardInterrupt:
    print("\nPrueba detenida por el usuario.")
