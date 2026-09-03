<<<<<<< HEAD
import json
import re
import requests
import pandas as pd
import streamlit as st
import datetime
from pathlib import Path

# ── Telegram config ───────────────────────────────────────────────────────────
TOKEN      = "8968886332:AAGdmdP179wk2-dPOfLrfkmNwX9sIcBhGI0"
BASE_URL   = f"https://api.telegram.org/bot{TOKEN}"

# ── Archivos de estado (misma carpeta que este script) ────────────────────────
BASE_DIR    = Path(__file__).parent
OFFSET_FILE = BASE_DIR / "tg_offset.json"   # recuerda hasta dónde leímos
BUFFER_FILE = BASE_DIR / "tg_buffer.json"   # mensajes parseados, listos para guardar

# ── Helpers de offset ─────────────────────────────────────────────────────────

def load_offset() -> int:
    if OFFSET_FILE.exists():
        return json.loads(OFFSET_FILE.read_text()).get("offset", 0)
    return 0

def save_offset(offset: int):
    OFFSET_FILE.write_text(json.dumps({"offset": offset}))

# ── Helpers de buffer ─────────────────────────────────────────────────────────

def load_buffer() -> list:
    if BUFFER_FILE.exists():
        return json.loads(BUFFER_FILE.read_text())
    return []

def save_buffer(buf: list):
    BUFFER_FILE.write_text(json.dumps(buf, indent=2))

def clear_buffer():
    BUFFER_FILE.write_text(json.dumps([]))

# ── Parsing de mensajes ───────────────────────────────────────────────────────

# Format 1 (verbose): semana 19 / total 250 / area1 50 / area2 80
PATTERN_VERBOSE = re.compile(
    r"semana\s+([\d]+)"
    r".*?total\s+([\d.,]+)"
    r".*?area1\s+([\d.,]+)"
    r".*?area2\s+([\d.,]+)",
    re.IGNORECASE,
)

# Format 2 (short): 19, 250.5, 50.3, 80.2
PATTERN_SHORT = re.compile(
    r"^\s*([\d]+)\s*,\s*([\d.,]+)\s*,\s*([\d.,]+)\s*,\s*([\d.,]+)\s*$"
)

def _to_float(s: str) -> float:
    """Accepts both '250.5' and '250,5' as decimal separators."""
    return float(s.replace(",", "."))

def parse_report(text: str) -> dict | None:
    # Try verbose format first
    m = PATTERN_VERBOSE.search(text)
    if m:
        return {
            "week":  int(m.group(1)),
            "total": _to_float(m.group(2)),
            "area1": _to_float(m.group(3)),
            "area2": _to_float(m.group(4)),
        }
    # Try short format: week, total, area1, area2
    m = PATTERN_SHORT.match(text)
    if m:
        return {
            "week":  int(m.group(1)),
            "total": _to_float(m.group(2)),
            "area1": _to_float(m.group(3)),
            "area2": _to_float(m.group(4)),
        }
    return None

# ── Llamada a Telegram (solo al picar el botón) ───────────────────────────────

def fetch_from_telegram() -> tuple[int, int]:
    """
    Lee los mensajes nuevos desde Telegram, parsea los válidos
    y los agrega al buffer local.
    Devuelve (mensajes_nuevos, mensajes_parseados).
    """
    offset    = load_offset()
    buffer    = load_buffer()
    new_total = 0
    new_valid = 0

    try:
        resp = requests.get(
            f"{BASE_URL}/getUpdates",
            params={"offset": offset, "limit": 100, "timeout": 5},
            timeout=10,
        )
        updates = resp.json().get("result", [])
    except Exception as e:
        st.error(f"Error al conectar con Telegram: {e}")
        return 0, 0

    for upd in updates:
        offset = upd["update_id"] + 1

        # Skip non-message updates (edited messages, inline queries, etc.)
        message = upd.get("message")
        if not message:
            continue

        text = message.get("text", "").strip()

        # Skip bot commands (/start, /help, etc.)
        if text.startswith("/"):
            continue

        new_total += 1
        report = parse_report(text)
        if report:
            # Validación básica
            if report["total"] >= report["area1"] + report["area2"]:
                buffer.append(report)
                new_valid += 1

    save_offset(offset)
    save_buffer(buffer)
    return new_total, new_valid

# ── Streamlit ─────────────────────────────────────────────────────────────────
=======
import pandas as pd
import streamlit as st
import datetime
>>>>>>> 6366685967d81879c4d683207c53ba5dea628a18

st.set_page_config(page_title="Water consumption tracker", layout="wide")

def load_data():
<<<<<<< HEAD
    try:
        historical_df = pd.read_csv("dataset/monthly_consumption.csv")
        weekly_df     = pd.read_csv("dataset/weekly_consumption.csv")
        daily_df      = pd.read_csv("dataset/daily_shift_consumption.csv")
        return historical_df, weekly_df, daily_df
    except FileNotFoundError as e:
        st.error(f"❌ CSV file not found: {e}")
        st.stop()
=======
    historical_df = pd.read_csv("dataset/monthly_consumption.csv")
    weekly_df = pd.read_csv("dataset/weekly_consumption.csv")
    daily_df = pd.read_csv("dataset/daily_shift_consumption.csv")
    return historical_df, weekly_df, daily_df
>>>>>>> 6366685967d81879c4d683207c53ba5dea628a18

historical_df, weekly_df, daily_df = load_data()

st.sidebar.header("Navigation")
menu = st.sidebar.radio(
    "Tools:",
    ["Historical", "Discrepancy", "Timeline", "Simulation", "New Data"]
)

st.sidebar.divider()
st.sidebar.header("Target limits (m³)")
limit_1 = st.sidebar.number_input("Area 1 limit: ", value=100.0)
limit_2 = st.sidebar.number_input("Area 2 limit: ", value=180.0)
limit_3 = st.sidebar.number_input("Area 3 limit: ", value=150.0)

st.title("Water consumption tool")
st.divider()

<<<<<<< HEAD
# ─────────────────────────────────────────────────────────────────────────────
if menu == "Historical":
    st.header("KPI analysis (Monthly)")
    if not historical_df.empty:
        months = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December']
        melted_df = historical_df.melt(
            id_vars=['Year'], value_vars=months,
            var_name='Month', value_name='Consumption'
        )
        melted_df = melted_df.dropna(subset=['Consumption'])
        melted_df['Date'] = pd.to_datetime(melted_df['Year'].astype(str) + ' ' + melted_df['Month'], format="%Y %B")
        melted_df = melted_df.sort_values('Date').set_index('Date')
=======
if menu == "Historical":
    st.header("KPI analysis (Monthly)")
    if not historical_df.empty:
        months = ['January', 'February', 'March', 'April', 'May', 'June', 
                  'July', 'August', 'September', 'October', 'November', 'December']
        
        melted_df = historical_df.melt(
            id_vars=['Year'], 
            value_vars=months, 
            var_name='Month', 
            value_name='Consumption'
        )
        
        melted_df = melted_df.dropna(subset=['Consumption'])
        
        melted_df['Date'] = pd.to_datetime(melted_df['Year'].astype(str) + ' ' + melted_df['Month'])
        melted_df = melted_df.sort_values('Date').set_index('Date')
        
>>>>>>> 6366685967d81879c4d683207c53ba5dea628a18
        st.line_chart(melted_df[['Consumption']])

elif menu == "Discrepancy":
    st.header("Discrepancy & Anomaly Log")
<<<<<<< HEAD
    if not weekly_df.empty:
        anomaly_mask = (
            (weekly_df['Area1_Purifika_m3']  > limit_1) |
            (weekly_df['Area2_Sanitarios_m3'] > limit_2) |
            (weekly_df['Area3_Fundition_m3']  > limit_3) |
            (weekly_df['Area3_Fundition_m3']  < 0)
        )
        anomalies_df = weekly_df[anomaly_mask].copy()
=======
    
    if not weekly_df.empty:
        anomaly_mask = (
            (weekly_df['Area1_Purifika_m3'] > limit_1) |
            (weekly_df['Area2_Sanitarios_m3'] > limit_2) |
            (weekly_df['Area3_Fundition_m3'] > limit_3) |
            (weekly_df['Area3_Fundition_m3'] < 0)
        )
        
        anomalies_df = weekly_df[anomaly_mask].copy()
        
>>>>>>> 6366685967d81879c4d683207c53ba5dea628a18
        if anomalies_df.empty:
            st.success("All consumption metrics are within established limits.")
        else:
            st.error(f"Detected {len(anomalies_df)} weeks with limit breaches or calculation errors.")
            st.dataframe(anomalies_df.set_index('Week_Number'), use_container_width=True)
<<<<<<< HEAD
=======
            
>>>>>>> 6366685967d81879c4d683207c53ba5dea628a18
            st.subheader("Area 3 Trend vs Limit")
            chart_data = weekly_df[['Week_Number', 'Area3_Fundition_m3']].set_index('Week_Number')
            st.line_chart(chart_data)

elif menu == "Timeline":
    st.header("Timeline analysis")
    if not daily_df.empty:
        daily_df['Date'] = pd.to_datetime(daily_df['Date'])
<<<<<<< HEAD
        min_date  = daily_df['Date'].min().date()
        max_date  = daily_df['Date'].max().date()
        total_days = (max_date - min_date).days

        st.subheader("Timeline control")
        window_size    = st.slider("Select Timeframe (Days):", min_value=1, max_value=total_days, value=14)
        max_start_date = max_date - datetime.timedelta(days=window_size)

=======
        min_date = daily_df['Date'].min().date()
        max_date = daily_df['Date'].max().date()
        total_days = (max_date - min_date).days

        st.subheader("Timeline control")
        window_size = st.slider("Select Timeframe (Days):", min_value=1, max_value=total_days, value=14)
        max_start_date = max_date - datetime.timedelta(days=window_size)
            
>>>>>>> 6366685967d81879c4d683207c53ba5dea628a18
        if max_start_date <= min_date:
            start_date = min_date
        else:
            start_date = st.slider(
<<<<<<< HEAD
                "Pan Timeline:", min_value=min_date, max_value=max_start_date,
                value=max_start_date, format="MMM DD, YYYY"
            )
        end_date = start_date + datetime.timedelta(days=window_size)
        mask = (daily_df['Date'].dt.date >= start_date) & (daily_df['Date'].dt.date <= end_date)
        filtered_daily = daily_df.loc[mask].set_index('Date')
=======
                "Pan Timeline:",
                min_value=min_date,
                max_value=max_start_date,
                value=max_start_date,  
                format="MMM DD, YYYY"
            )
            
        end_date = start_date + datetime.timedelta(days=window_size)
        
        mask = (daily_df['Date'].dt.date >= start_date) & (daily_df['Date'].dt.date <= end_date)
        filtered_daily = daily_df.loc[mask].set_index('Date')
        
>>>>>>> 6366685967d81879c4d683207c53ba5dea628a18
        st.subheader(f"Shift Trends ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d')})")
        st.area_chart(filtered_daily[['Shift_1_m3', 'Shift_2_m3', 'Shift_3_m3']])

elif menu == "Simulation":
    st.header("Simulation")
<<<<<<< HEAD
    action  = st.text_input("Proposed action:")
    savings = st.number_input("Estimated weekly savings (m³):", min_value=0.0, value=50.0)
=======
    action = st.text_input("Proposed action:")
    savings = st.number_input("Estimated weekly savings (m³):", min_value=0.0, value=50.0)
    
>>>>>>> 6366685967d81879c4d683207c53ba5dea628a18
    if st.button("Simulate") and action:
        st.success(f"Action '{action}' reduces the annual KPI by {savings * 52:,.2f} m³.")

elif menu == "New Data":
    st.header("Log Data")
<<<<<<< HEAD

    tab_manual, tab_telegram = st.tabs(["✏️ Manual entry", "📱 Import from Telegram"])

    # ── Tab 1: Manual entry ───────────────────────────────────────────────────
    with tab_manual:
        with st.form("new_data_form"):
            week  = st.number_input("Week Number", min_value=1, max_value=52, step=1)
            total = st.number_input("Total Inlet (m³)", min_value=0.0)
            a1    = st.number_input("Area 1 (m³)", min_value=0.0)
            a2    = st.number_input("Area 2 (m³)", min_value=0.0)

            if st.form_submit_button("💾 Save"):
                if total < (a1 + a2):
                    st.error("Error: Total consumption cannot be less than the sum of Area 1 and Area 2.")
                else:
                    a3 = total - (a1 + a2)
                    pd.DataFrame({
                        'Week_Number':         [week],
                        'Area2_Sanitarios_m3': [a2],
                        'Area1_Purifika_m3':   [a1],
                        'Total_Daily_m3':      [total],
                        'Area3_Fundition_m3':  [a3],
                    }).to_csv("dataset/weekly_consumption.csv", mode='a', header=False, index=False)
                    st.success(f"Data saved. Area 3 estimated at {a3:.2f} m³.")

    # ── Tab 2: Importar desde Telegram (on-demand) ────────────────────────────
    with tab_telegram:
        st.subheader("📱 Import from Telegram")
        st.caption(
            "Manda tu reporte al bot con este formato:\n\n"
            "`semana 19 / total 250 / area1 50 / area2 80`\n\n"
            "Luego pica **Fetch** para jalarlo aquí."
        )

        # ── Botón FETCH ────────────────────────────────────────────────────────
        if st.button("🔄 Fetch from Telegram", type="primary"):
            with st.spinner("Conectando con Telegram..."):
                total_msgs, valid_msgs = fetch_from_telegram()
            if total_msgs == 0:
                st.info("No hay mensajes nuevos en Telegram.")
            else:
                st.success(
                    f"Se leyeron **{total_msgs}** mensaje(s) nuevo(s), "
                    f"**{valid_msgs}** con formato válido agregados al buffer."
                )

        st.divider()

        # ── Buffer actual ──────────────────────────────────────────────────────
        buffer = load_buffer()

        if not buffer:
            st.info("El buffer está vacío. Pica **Fetch** para revisar si hay mensajes nuevos.")
        else:
            rows = []
            for r in buffer:
                a3 = r["total"] - r["area1"] - r["area2"]
                rows.append({
                    "Semana":      r["week"],
                    "Total (m³)":  r["total"],
                    "Area 1 (m³)": r["area1"],
                    "Area 2 (m³)": r["area2"],
                    "Area 3 (m³)": round(a3, 2),
                })

            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            st.write(f"**{len(buffer)} reporte(s) listos para guardar.**")

            # ── Botón SAVE ─────────────────────────────────────────────────────
            if st.button("💾 Save all to CSV", type="primary"):
                pd.DataFrame([
                    {
                        'Week_Number':         r["week"],
                        'Area2_Sanitarios_m3': r["area2"],
                        'Area1_Purifika_m3':   r["area1"],
                        'Total_Daily_m3':      r["total"],
                        'Area3_Fundition_m3':  round(r["total"] - r["area1"] - r["area2"], 2),
                    }
                    for r in buffer
                ]).to_csv("dataset/weekly_consumption.csv", mode='a', header=False, index=False)
                clear_buffer()
                st.success(f"✅ {len(buffer)} reporte(s) guardados. Buffer limpiado.")
                st.rerun()
=======
    with st.form("new_data_form"):
        week = st.number_input("Week Number", min_value=1, max_value=52, step=1)
        total = st.number_input("Total Inlet (m³)", min_value=0.0)
        a1 = st.number_input("Area 1 (m³)", min_value=0.0)
        a2 = st.number_input("Area 2 (m³)", min_value=0.0)
        
        if st.form_submit_button("Save"):
            if total < (a1 + a2):
                st.error("Error: Total consumption cannot be less than the sum of Area 1 and Area 2.")
            else:
                a3 = total - (a1 + a2)
                new_row = pd.DataFrame({
                    'Week_Number': [week],
                    'Area2_Sanitarios_m3': [a2],
                    'Area1_Purifika_m3': [a1],
                    'Total_Daily_m3': [total],
                    'Area3_Fundition_m3': [a3]
                })
                
                new_row.to_csv("weekly_consumption.csv", mode='a', header=False, index=False)
                st.success(f"Data saved. Area 3 estimated at {a3:.2f} m³.")
>>>>>>> 6366685967d81879c4d683207c53ba5dea628a18
