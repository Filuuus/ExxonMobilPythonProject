"""
Telegram Bot — Water Consumption Reporter
=========================================
Corre este script en una terminal separada:
    python telegram_bot.py

FORMATO DEL MENSAJE (desde Telegram):
    semana 19 / total 250 / area1 50 / area2 80

Todos los campos son obligatorios y deben ir en ese orden.
Los números pueden ser enteros o decimales.

El bot guarda los reportes pendientes en 'pending_reports.json'.
Desde Streamlit (sección "New Data") puedes importarlos con un clic.
"""

import json
import os
import re
import logging
from pathlib import Path

import requests

# ── Configuración ────────────────────────────────────────────────────────────
TOKEN = "8968886332:AAGdmdP179wk2-dPOfLrfkmNwX9sIcBhGI0"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
PENDING_FILE = Path(__file__).parent / "pending_reports.json"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ── Helpers para el archivo de cola ──────────────────────────────────────────

def load_pending() -> list:
    if PENDING_FILE.exists():
        with open(PENDING_FILE, "r") as f:
            return json.load(f)
    return []


def save_pending(reports: list):
    with open(PENDING_FILE, "w") as f:
        json.dump(reports, f, indent=2)


def add_report(report: dict):
    reports = load_pending()
    reports.append(report)
    save_pending(reports)

# ── Parsing del mensaje ───────────────────────────────────────────────────────

PATTERN = re.compile(
    r"semana\s+(\d+)"
    r".*?total\s+([\d.]+)"
    r".*?area1\s+([\d.]+)"
    r".*?area2\s+([\d.]+)",
    re.IGNORECASE,
)


def parse_report(text: str) -> dict | None:
    """Devuelve un dict con los valores o None si el formato no es válido."""
    m = PATTERN.search(text)
    if not m:
        return None
    week   = int(m.group(1))
    total  = float(m.group(2))
    area1  = float(m.group(3))
    area2  = float(m.group(4))
    return {"week": week, "total": total, "area1": area1, "area2": area2}

# ── API de Telegram ───────────────────────────────────────────────────────────

def send_message(chat_id: int, text: str):
    requests.post(
        f"{BASE_URL}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )


def get_updates(offset: int) -> list:
    try:
        r = requests.get(
            f"{BASE_URL}/getUpdates",
            params={"timeout": 30, "offset": offset},
            timeout=35,
        )
        return r.json().get("result", [])
    except Exception as e:
        log.warning(f"Error al obtener updates: {e}")
        return []

# ── Mensajes de ayuda ─────────────────────────────────────────────────────────

HELP_TEXT = (
    "📋 *Water Consumption Bot*\n\n"
    "Envía tu reporte semanal con este formato:\n\n"
    "`semana 19 / total 250 / area1 50 / area2 80`\n\n"
    "• `semana` → número de semana (1-52)\n"
    "• `total`  → consumo total de entrada (m³)\n"
    "• `area1`  → Area 1 Purifika (m³)\n"
    "• `area2`  → Area 2 Sanitarios (m³)\n\n"
    "_Area 3 se calcula automáticamente: total - area1 - area2_\n\n"
    "Luego abre Streamlit → *New Data* → *Importar desde Telegram* para guardar."
)

# ── Loop principal ────────────────────────────────────────────────────────────

def main():
    log.info("Bot iniciado. Esperando mensajes...")
    offset = 0

    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            text = message.get("text", "").strip()
            chat_id = message.get("chat", {}).get("id")

            if not text or not chat_id:
                continue

            # Comandos de ayuda
            if text.lower() in ("/start", "/help", "/ayuda"):
                send_message(chat_id, HELP_TEXT)
                continue

            # Intentar parsear reporte
            report = parse_report(text)
            if report is None:
                send_message(
                    chat_id,
                    "❌ Formato no reconocido.\n\n"
                    "Usa:\n`semana 19 / total 250 / area1 50 / area2 80`\n\n"
                    "Escribe /help para ver el formato completo.",
                )
                continue

            # Validar que total >= area1 + area2
            if report["total"] < report["area1"] + report["area2"]:
                send_message(
                    chat_id,
                    f"⚠️ Error: el total ({report['total']}) no puede ser menor "
                    f"que area1 + area2 ({report['area1'] + report['area2']}).\n"
                    "Corrige y reenvía.",
                )
                continue

            area3 = report["total"] - report["area1"] - report["area2"]
            add_report(report)

            log.info(f"Reporte guardado: {report}")
            send_message(
                chat_id,
                f"✅ *Reporte recibido* — Semana {report['week']}\n\n"
                f"• Total:  {report['total']} m³\n"
                f"• Area 1: {report['area1']} m³\n"
                f"• Area 2: {report['area2']} m³\n"
                f"• Area 3: {area3:.2f} m³ _(calculado)_\n\n"
                f"Abre Streamlit → *New Data* para importarlo.",
            )


if __name__ == "__main__":
    main()
