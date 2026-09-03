from __future__ import annotations

import datetime
import json
import re
from io import StringIO
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st

# ── Telegram ──────────────────────────────────────────────────────────────────
TOKEN = "8968886332:AAGdmdP179wk2-dPOfLrfkmNwX9sIcBhGI0"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATASET_DIR = BASE_DIR / "dataset"
OFFSET_FILE = BASE_DIR / "tg_offset.json"
BUFFER_FILE = BASE_DIR / "tg_buffer.json"

MONTHLY_CSV = DATASET_DIR / "monthly_consumption.csv"
WEEKLY_CSV = DATASET_DIR / "weekly_consumption.csv"
DAILY_SHIFT_CSV = DATASET_DIR / "daily_shift_consumption.csv"
BITACORA_CSV = DATASET_DIR / "bitacora_daily.csv"
WEEKLY_PLANT_CSV = DATASET_DIR / "weekly_plant.csv"
MONTHLY_PLANT_CSV = DATASET_DIR / "monthly_plant_2026.csv"
REGISTRO_CSV = DATASET_DIR / "shift_register_jul2026.csv"

WEEKLY_COLUMNS = [
    "Week_Number",
    "Area2_Sanitarios_m3",
    "Area1_Purifika_m3",
    "Total_Daily_m3",
    "Area3_Fundition_m3",
]

REGISTRO_SLOTS = [
    ("MGM_01_00", "MGM · 01:00 a.m."),
    ("MGM_05_30", "MGM · 05:30 a.m."),
    ("MGM_16_00", "MGM · 04:00 p.m."),
    ("MGM_21_30", "MGM · 09:30 p.m."),
    ("M1_01_00", "M1 · 01:00 a.m."),
    ("M1_05_30", "M1 · 05:30 a.m."),
    ("M1_16_00", "M1 · 04:00 p.m."),
    ("M1_21_30", "M1 · 09:30 p.m."),
]
REGISTRO_COLS = ["Date"] + [c for c, _ in REGISTRO_SLOTS]
MGM_SLOTS = ["MGM_01_00", "MGM_05_30", "MGM_16_00", "MGM_21_30"]
M1_SLOTS = ["M1_01_00", "M1_05_30", "M1_16_00", "M1_21_30"]

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

DEFAULT_DAILY = {
    "purifika": 8.0,
    "sanitarios": 16.0,
    "diecast": 12.0,
    "mgm": 17.0,
    "m1": 7.0,
}
DEFAULT_SHARES = {"purifika": 0.25, "sanitarios": 0.45, "diecast": 0.30}
DEFAULT_KPI = 680.0  # monthly target; 2026-01 already sits just above this

AREAS = [
    ("purifika", "Purifika", "Area 1 · proceso"),
    ("sanitarios", "Sanitarios", "Area 2 · servicios"),
    ("diecast", "Diecast / Fundición", "Area 3 · residual"),
]


# ── Small helpers ─────────────────────────────────────────────────────────────

def load_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return json.loads(OFFSET_FILE.read_text()).get("offset", 0)
        except (json.JSONDecodeError, OSError):
            return 0
    return 0


def save_offset(offset: int) -> None:
    OFFSET_FILE.write_text(json.dumps({"offset": offset}))


def load_buffer() -> list:
    if BUFFER_FILE.exists():
        try:
            data = json.loads(BUFFER_FILE.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_buffer(buf: list) -> None:
    BUFFER_FILE.write_text(json.dumps(buf, indent=2))


def clear_buffer() -> None:
    BUFFER_FILE.write_text(json.dumps([]))


PATTERN_VERBOSE = re.compile(
    r"semana\s+(\d+).*?total\s+([\d.,]+).*?area1\s+([\d.,]+).*?area2\s+([\d.,]+)",
    re.IGNORECASE,
)
PATTERN_SHORT = re.compile(
    r"^\s*(\d+)\s*,\s*([\d.,]+)\s*,\s*([\d.,]+)\s*,\s*([\d.,]+)\s*$"
)


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))


def parse_report(text: str) -> dict | None:
    m = PATTERN_VERBOSE.search(text)
    if m:
        return {
            "week": int(m.group(1)),
            "total": _to_float(m.group(2)),
            "area1": _to_float(m.group(3)),
            "area2": _to_float(m.group(4)),
        }
    m = PATTERN_SHORT.match(text)
    if m:
        return {
            "week": int(m.group(1)),
            "total": _to_float(m.group(2)),
            "area1": _to_float(m.group(3)),
            "area2": _to_float(m.group(4)),
        }
    return None


def fetch_from_telegram() -> tuple[int, int]:
    offset = load_offset()
    buffer = load_buffer()
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
        st.error(f"Error connecting to Telegram: {e}")
        return 0, 0

    for upd in updates:
        offset = upd["update_id"] + 1
        message = upd.get("message")
        if not message:
            continue
        text = message.get("text", "").strip()
        if not text or text.startswith("/"):
            continue
        new_total += 1
        report = parse_report(text)
        if report and report["total"] >= report["area1"] + report["area2"]:
            buffer.append(report)
            new_valid += 1

    save_offset(offset)
    save_buffer(buffer)
    return new_total, new_valid


def _skip_conflict_markers(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [
        line
        for line in raw
        if line.strip()
        and not line.startswith("<<<<<<<")
        and not line.startswith("=======")
        and not line.startswith(">>>>>>>")
    ]


def _read_csv_resilient(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    cleaned = "\n".join(_skip_conflict_markers(path))
    if not cleaned.strip():
        return pd.DataFrame()
    return pd.read_csv(StringIO(cleaned))


def load_data() -> dict[str, pd.DataFrame]:
    return {
        "historical": _read_csv_resilient(MONTHLY_CSV),
        "weekly_areas": _read_csv_resilient(WEEKLY_CSV),
        "daily_shift": _read_csv_resilient(DAILY_SHIFT_CSV),
        "bitacora": _read_csv_resilient(BITACORA_CSV),
        "weekly_plant": _read_csv_resilient(WEEKLY_PLANT_CSV),
        "monthly_plant": _read_csv_resilient(MONTHLY_PLANT_CSV),
        "registro": _read_csv_resilient(REGISTRO_CSV),
    }


def append_weekly_rows(rows: list[dict]) -> None:
    pd.DataFrame(rows, columns=WEEKLY_COLUMNS).to_csv(
        WEEKLY_CSV, mode="a", header=False, index=False
    )


def report_to_weekly_row(week: int, total: float, a1: float, a2: float) -> dict:
    return {
        "Week_Number": week,
        "Area2_Sanitarios_m3": a2,
        "Area1_Purifika_m3": a1,
        "Total_Daily_m3": total,
        "Area3_Fundition_m3": round(total - a1 - a2, 2),
    }


def upsert_registro(row: dict) -> None:
    df = _read_csv_resilient(REGISTRO_CSV)
    incoming = pd.DataFrame([row], columns=REGISTRO_COLS)
    if df.empty:
        incoming.to_csv(REGISTRO_CSV, index=False)
        return
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    incoming["Date"] = pd.to_datetime(incoming["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df[df["Date"] != incoming["Date"].iloc[0]]
    pd.concat([df, incoming], ignore_index=True).sort_values("Date").to_csv(
        REGISTRO_CSV, index=False
    )


def last_slot_value(series: pd.Series) -> float | None:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if vals.empty:
        return None
    return float(vals.iloc[-1])


def daily_consumption_from_meters(registro: pd.DataFrame) -> pd.DataFrame:
    """Daily m³ = last reading of the day − last reading of the previous day."""
    if registro.empty:
        return pd.DataFrame(columns=["Date", "Consumo_MGM_m3", "Consumo_M1_m3", "Consumo_Total_m3"])
    df = registro.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")
    for col in MGM_SLOTS + M1_SLOTS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["MGM_last"] = df[MGM_SLOTS].apply(last_slot_value, axis=1)
    df["M1_last"] = df[M1_SLOTS].apply(last_slot_value, axis=1)
    df["Consumo_MGM_m3"] = df["MGM_last"].diff()
    df["Consumo_M1_m3"] = df["M1_last"].diff()
    df["Consumo_Total_m3"] = df["Consumo_MGM_m3"].fillna(0) + df["Consumo_M1_m3"].fillna(0)
    return df[["Date", "Consumo_MGM_m3", "Consumo_M1_m3", "Consumo_Total_m3", "MGM_last", "M1_last"]]


def slot_consumption(registro: pd.DataFrame, plant_slots: list[str]) -> pd.DataFrame:
    """Interval consumption between consecutive clock times."""
    if registro.empty:
        return pd.DataFrame()
    df = registro.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")
    for col in plant_slots:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    long = df.melt(
        id_vars=["Date"],
        value_vars=[c for c in plant_slots if c in df.columns],
        var_name="Slot",
        value_name="Reading",
    ).dropna(subset=["Reading"])
    long = long.sort_values(["Date", "Slot"])
    long["Consumption"] = long.groupby(long["Slot"].str.startswith("M1"))["Reading"].diff()
    return long


def area_shares(weekly_areas: pd.DataFrame, week: int | None) -> dict[str, float]:
    shares = dict(DEFAULT_SHARES)
    if weekly_areas is None or weekly_areas.empty:
        return shares
    df = weekly_areas.copy()
    for col in ("Area1_Purifika_m3", "Area2_Sanitarios_m3", "Area3_Fundition_m3"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").clip(lower=0)

    def from_row(row) -> dict[str, float] | None:
        p = float(row.get("Area1_Purifika_m3") or 0)
        s = float(row.get("Area2_Sanitarios_m3") or 0)
        d = float(row.get("Area3_Fundition_m3") or 0)
        tot = p + s + d
        if tot <= 0:
            return None
        return {"purifika": p / tot, "sanitarios": s / tot, "diecast": d / tot}

    if week is not None and "Week_Number" in df.columns:
        hit = df[df["Week_Number"] == week]
        if not hit.empty:
            got = from_row(hit.iloc[-1])
            if got:
                return got
    return shares


def split_daily(total: float, shares: dict[str, float]) -> dict[str, float]:
    return {k: round(total * shares[k], 2) for k in ("purifika", "sanitarios", "diecast")}


def render_card(title: str, subtitle: str, value: float, limit: float, alarm: bool, highest: bool) -> None:
    pct = (value / limit * 100) if limit else 0
    if alarm:
        bg, border, badge, badge_bg = "#3b0a0a", "#ef4444", "ALARMA", "#ef4444"
    elif highest:
        bg, border, badge, badge_bg = "#3b2a08", "#f59e0b", "MAYOR CONSUMO", "#f59e0b"
    else:
        bg, border, badge, badge_bg = "#0f172a", "#334155", "OK", "#22c55e"
    st.markdown(
        f"""
        <div style="background:{bg};border:2px solid {border};border-radius:14px;
                    padding:18px 16px;min-height:170px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;
                        color:#94a3b8;">{subtitle}</div>
            <span style="background:{badge_bg};color:#0b0b0b;font-weight:700;
                         font-size:11px;padding:3px 8px;border-radius:999px;">{badge}</span>
          </div>
          <div style="font-size:20px;font-weight:700;color:#f8fafc;margin:10px 0 4px;">{title}</div>
          <div style="font-size:32px;font-weight:800;color:#fff;">{value:.1f}
            <span style="font-size:14px;color:#cbd5e1;">m³</span></div>
          <div style="font-size:13px;color:#94a3b8;margin-top:6px;">
            Límite: {limit:.1f} m³ / día · {pct:.0f}%
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_monthly_chart(df: pd.DataFrame, kpi: float) -> alt.Chart:
    plot = df.copy()
    plot["Status"] = plot["Consumption"].apply(
        lambda v: "Sobre KPI" if v > kpi else "Dentro del KPI"
    )
    bars = (
        alt.Chart(plot)
        .mark_bar()
        .encode(
            x=alt.X("Date:T", title="Mes"),
            y=alt.Y("Consumption:Q", title="Consumo (m³)"),
            color=alt.Color(
                "Status:N",
                scale=alt.Scale(
                    domain=["Dentro del KPI", "Sobre KPI"],
                    range=["#005F86", "#BF5700"],
                ),
                legend=alt.Legend(title=""),
            ),
            tooltip=[
                alt.Tooltip("Date:T", title="Mes"),
                alt.Tooltip("Consumption:Q", title="m³", format=".1f"),
                "Status:N",
            ],
        )
    )
    rule = (
        alt.Chart(pd.DataFrame({"KPI": [kpi]}))
        .mark_rule(strokeDash=[6, 4], color="#eab308", strokeWidth=2)
        .encode(y="KPI:Q")
    )
    label = (
        alt.Chart(pd.DataFrame({"KPI": [kpi], "txt": [f"KPI {kpi:.0f} m³"]}))
        .mark_text(align="left", dx=6, dy=-8, color="#eab308")
        .encode(y="KPI:Q", text="txt:N")
    )
    return (bars + rule + label).properties(height=360)


def bar_pair(df: pd.DataFrame, x: str, y: str, title: str, color: str = "#005F86") -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_bar(color=color)
        .encode(
            x=alt.X(f"{x}:N", title="", sort=None),
            y=alt.Y(f"{y}:Q", title="m³"),
            tooltip=[x, alt.Tooltip(f"{y}:Q", format=".1f")],
        )
        .properties(title=title, height=280)
    )


# ── App ───────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Water consumption tracker", layout="wide")
data = load_data()
historical_df = data["historical"]
weekly_df = data["weekly_areas"]
daily_df = data["daily_shift"]
bitacora = data["bitacora"]
weekly_plant = data["weekly_plant"]
monthly_plant = data["monthly_plant"]
registro = data["registro"]

st.sidebar.header("Navigation")
menu = st.sidebar.radio(
    "Tools:",
    [
        "Plant floor",
        "Monthly trend",
        "Discrepancy",
        "Timeline",
        "Simulation",
        "New Data",
    ],
)

st.sidebar.divider()
st.sidebar.header("KPI mensual de planta")
st.sidebar.caption("Meta de consumo de agua de la planta. No es el nombre del gráfico.")
kpi_monthly = st.sidebar.number_input(
    "KPI (m³ / mes)",
    min_value=0.0,
    value=DEFAULT_KPI,
    help="Un poco abajo de 700. Enero 2026 ya lo rebasó (682 m³).",
)

st.sidebar.divider()
st.sidebar.header("Límites diarios (m³)")
limit_p = st.sidebar.number_input("Purifika", value=DEFAULT_DAILY["purifika"], min_value=0.0)
limit_s = st.sidebar.number_input("Sanitarios", value=DEFAULT_DAILY["sanitarios"], min_value=0.0)
limit_d = st.sidebar.number_input("Diecast / Fundición", value=DEFAULT_DAILY["diecast"], min_value=0.0)
limit_mgm = st.sidebar.number_input("Planta MGM", value=DEFAULT_DAILY["mgm"], min_value=0.0)
limit_m1 = st.sidebar.number_input("Planta M1", value=DEFAULT_DAILY["m1"], min_value=0.0)
area_limits = {"purifika": limit_p, "sanitarios": limit_s, "diecast": limit_d}
weekly_area_limits = {k: v * 7 for k, v in area_limits.items()}

st.title("Water consumption tool")
st.divider()

# ── Plant floor ───────────────────────────────────────────────────────────────
if menu == "Plant floor":
    st.header("Piso de planta · 3 secciones + 2 medidores")
    st.caption("El recuadro se pone rojo si ese día pasó el límite operacional.")

    source = bitacora.copy()
    if source.empty:
        derived = daily_consumption_from_meters(registro)
        source = derived.rename(columns={"Date": "Date"})
        source["Week_Number"] = pd.to_datetime(source["Date"], errors="coerce").dt.isocalendar().week
    if source.empty:
        st.warning("No hay bitácora ni registro.")
    else:
        b = source.copy()
        b["Date"] = pd.to_datetime(b["Date"], errors="coerce")
        b = b.dropna(subset=["Date"])
        for col in ("Consumo_MGM_m3", "Consumo_M1_m3", "Consumo_Total_m3", "Week_Number"):
            if col in b.columns:
                b[col] = pd.to_numeric(b[col], errors="coerce")
        if "Consumo_Total_m3" not in b.columns:
            b["Consumo_Total_m3"] = b.get("Consumo_MGM_m3", 0).fillna(0) + b.get("Consumo_M1_m3", 0).fillna(0)
        usable = b.dropna(subset=["Consumo_Total_m3"])
        if usable.empty:
            st.warning("No hay consumos numéricos.")
        else:
            min_d, max_d = usable["Date"].min().date(), usable["Date"].max().date()
            selected = st.date_input("Día a vigilar", value=max_d, min_value=min_d, max_value=max_d)
            day = usable[usable["Date"].dt.date == selected]
            if day.empty:
                st.info("No hay lectura ese día.")
            else:
                row = day.iloc[-1]
                total = float(row.get("Consumo_Total_m3") or 0)
                mgm = float(row.get("Consumo_MGM_m3") or 0)
                m1 = float(row.get("Consumo_M1_m3") or 0)
                week = int(row["Week_Number"]) if pd.notna(row.get("Week_Number")) else None
                areas = split_daily(total, area_shares(weekly_df, week))
                alarms = {k: areas[k] > area_limits[k] for k in area_limits}
                plant_alarms = {"MGM": mgm > limit_mgm, "M1": m1 > limit_m1}
                max_area = max(areas.values()) if areas else 0
                highest = {k for k, v in areas.items() if v == max_area and max_area > 0}

                if any(alarms.values()) or any(plant_alarms.values()):
                    names = [label for key, label, _ in AREAS if alarms[key]]
                    names += [k for k, flag in plant_alarms.items() if flag]
                    st.error("ALARMA · sobre el límite en: " + ", ".join(names))
                else:
                    st.success("Consumo del día dentro de los límites.")

                cols = st.columns(3)
                for col, (key, label, sub) in zip(cols, AREAS):
                    with col:
                        render_card(label, sub, areas[key], area_limits[key], alarms[key], key in highest)
                st.markdown("")
                pcols = st.columns(2)
                with pcols[0]:
                    render_card("MGM", "Medidor planta MGM", mgm, limit_mgm, plant_alarms["MGM"], False)
                with pcols[1]:
                    render_card("M1", "Medidor planta M1", m1, limit_m1, plant_alarms["M1"], False)

# ── Monthly trend (NOT "KPI analysis") ────────────────────────────────────────
elif menu == "Monthly trend":
    st.header("Consumo mensual")
    st.caption(
        "El KPI es la meta de agua de la planta (línea horizontal). "
        "Las barras naranjas están por encima de esa meta."
    )

    if historical_df.empty:
        st.info("No hay serie mensual.")
    else:
        melted = historical_df.melt(
            id_vars=["Year"],
            value_vars=[m for m in MONTHS if m in historical_df.columns],
            var_name="Month",
            value_name="Consumption",
        ).dropna(subset=["Consumption"])
        melted["Date"] = pd.to_datetime(
            melted["Year"].astype(str) + " " + melted["Month"],
            format="%Y %B",
        )
        melted = melted.sort_values("Date")
        over = int((melted["Consumption"] > kpi_monthly).sum())
        c1, c2, c3 = st.columns(3)
        c1.metric("KPI mensual", f"{kpi_monthly:.0f} m³")
        c2.metric("Último mes con dato", f"{melted['Consumption'].iloc[-1]:.0f} m³")
        c3.metric("Meses sobre el KPI", str(over))
        st.altair_chart(kpi_monthly_chart(melted, kpi_monthly), use_container_width=True)

    st.subheader("Gráficas automáticas · estilo bitácora")
    if monthly_plant.empty:
        st.info("No hay mensual 2026 de planta.")
    else:
        mp = monthly_plant.copy()
        shown = mp[mp["Consumo_Total_m3"].fillna(0) > 0]
        if shown.empty:
            shown = mp
        col_a, col_b = st.columns(2)
        with col_a:
            st.altair_chart(
                bar_pair(shown, "Month", "Consumo_MGM_m3", "Consumo mensual planta MGM", "#005F86"),
                use_container_width=True,
            )
        with col_b:
            st.altair_chart(
                bar_pair(shown, "Month", "Consumo_M1_m3", "Consumo mensual planta M1", "#00A9CE"),
                use_container_width=True,
            )
        col_c, col_d = st.columns(2)
        with col_c:
            st.altair_chart(
                bar_pair(shown, "Month", "Consumo_Total_m3", "Consumo mensual MGM + M1", "#1A1A2E"),
                use_container_width=True,
            )
        with col_d:
            spend = shown.melt(
                id_vars=["Month"],
                value_vars=[c for c in ("Gasto_MGM", "Gasto_M1") if c in shown.columns],
                var_name="Planta",
                value_name="Gasto",
            ).dropna()
            if not spend.empty:
                spend["Planta"] = spend["Planta"].replace({"Gasto_MGM": "MGM", "Gasto_M1": "M1"})
                spend_chart = (
                    alt.Chart(spend)
                    .mark_bar()
                    .encode(
                        x=alt.X("Month:N", title="", sort=None),
                        y=alt.Y("Gasto:Q", title="MXN"),
                        color=alt.Color("Planta:N", scale=alt.Scale(range=["#005F86", "#BF5700"])),
                        tooltip=["Month", "Planta", alt.Tooltip("Gasto:Q", format=",.0f")],
                    )
                    .properties(title="Gasto mensual", height=280)
                )
                st.altair_chart(spend_chart, use_container_width=True)

        pie_src = pd.DataFrame(
            {
                "Planta": ["MGM", "M1"],
                "Consumo": [
                    float(shown["Consumo_MGM_m3"].sum()),
                    float(shown["Consumo_M1_m3"].sum()),
                ],
            }
        )
        pie = (
            alt.Chart(pie_src)
            .mark_arc(innerRadius=50)
            .encode(
                theta="Consumo:Q",
                color=alt.Color("Planta:N", scale=alt.Scale(range=["#005F86", "#00A9CE"])),
                tooltip=["Planta", alt.Tooltip("Consumo:Q", format=".1f")],
            )
            .properties(title="Porcentaje de consumo MGM vs M1", height=280)
        )
        st.altair_chart(pie, use_container_width=True)

        cmp = shown[["Month", "Consumo_Total_m3", "Contratados_Total_m3"]].melt(
            id_vars="Month", var_name="Serie", value_name="m3"
        )
        cmp["Serie"] = cmp["Serie"].replace(
            {"Consumo_Total_m3": "Consumido", "Contratados_Total_m3": "Contratado"}
        )
        st.altair_chart(
            alt.Chart(cmp)
            .mark_bar()
            .encode(
                x=alt.X("Month:N", title="", sort=None),
                y=alt.Y("m3:Q", title="m³"),
                color=alt.Color("Serie:N", scale=alt.Scale(range=["#BF5700", "#9CADB7"])),
                xOffset="Serie:N",
                tooltip=["Month", "Serie", alt.Tooltip("m3:Q", format=".1f")],
            )
            .properties(title="Consumido vs m³ contratados", height=280),
            use_container_width=True,
        )

# ── Discrepancy ───────────────────────────────────────────────────────────────
elif menu == "Discrepancy":
    st.header("Discrepancy & Anomaly Log")

    st.subheader("Semanas de planta vs límite de bitácora")
    if weekly_plant.empty:
        st.info("No hay semanal de planta.")
    else:
        wp = weekly_plant.copy()
        for c in wp.columns:
            if c != "Week_Number":
                wp[c] = pd.to_numeric(wp[c], errors="coerce")
        mask = (
            (wp["Consumo_MGM_m3"] > wp["Limite_MGM_m3"])
            | (wp["Consumo_M1_m3"] > wp["Limite_M1_m3"])
            | (wp["Consumo_Total_m3"] > wp["Limite_Total_m3"])
        )
        bad = wp[mask]
        if bad.empty:
            st.success("Ninguna semana de planta rebasa el límite semanal.")
        else:
            st.error(f"{len(bad)} semana(s) sobre el límite semanal (MGM 118.5 / M1 47.5).")
            st.dataframe(bad.set_index("Week_Number"), use_container_width=True)
        long_w = wp.melt(
            id_vars="Week_Number",
            value_vars=["Consumo_MGM_m3", "Limite_MGM_m3", "Consumo_M1_m3", "Limite_M1_m3"],
            var_name="Serie",
            value_name="m3",
        )
        st.altair_chart(
            alt.Chart(long_w)
            .mark_line(point=True)
            .encode(
                x="Week_Number:O",
                y="m3:Q",
                color="Serie:N",
                tooltip=["Week_Number", "Serie", alt.Tooltip("m3:Q", format=".1f")],
            )
            .properties(height=280, title="Consumo semanal vs límite"),
            use_container_width=True,
        )

    st.subheader("Secciones (Purifika / Sanitarios / Diecast)")
    if weekly_df.empty:
        st.info("No weekly area data.")
    else:
        anomaly_mask = (
            (weekly_df["Area1_Purifika_m3"] > weekly_area_limits["purifika"])
            | (weekly_df["Area2_Sanitarios_m3"] > weekly_area_limits["sanitarios"])
            | (weekly_df["Area3_Fundition_m3"] > weekly_area_limits["diecast"])
            | (weekly_df["Area3_Fundition_m3"] < 0)
        )
        anomalies_df = weekly_df[anomaly_mask].copy()
        if anomalies_df.empty:
            st.success("Secciones dentro de los límites semanales.")
        else:
            st.error(f"{len(anomalies_df)} semanas fuera de límite o Area 3 negativa.")
            st.dataframe(anomalies_df.set_index("Week_Number"), use_container_width=True)

    st.subheader("Recibo vs bitácora")
    if not monthly_plant.empty:
        mp = monthly_plant.copy()
        mp = mp[mp["Consumo_Total_m3"].fillna(0) > 0]
        billed = st.number_input("m³ del recibo oficial", min_value=0.0, value=0.0)
        if not mp.empty:
            month_pick = st.selectbox("Mes", mp["Month"].tolist())
            if billed > 0:
                recorded = float(mp.loc[mp["Month"] == month_pick, "Consumo_Total_m3"].iloc[0])
                if billed > recorded + 1:
                    st.error(
                        f"Recibo {billed:.1f} m³ > bitácora {recorded:.1f} m³ "
                        f"({billed - recorded:.1f} m³ de más)."
                    )
                else:
                    st.success(f"Recibo {billed:.1f} m³ cuadra con {recorded:.1f} m³ registrados.")

# ── Timeline ──────────────────────────────────────────────────────────────────
elif menu == "Timeline":
    st.header("Timeline")
    st.caption("Todas las series que tenemos, no solo los turnos del CSV del curso.")

    series = st.multiselect(
        "Qué quieres ver",
        [
            "Bitácora MGM / M1 (diario)",
            "Turnos 1 / 2 / 3",
            "Registro 4 horarios (lecturas)",
            "Registro 4 horarios (consumo)",
            "Semanal planta vs límite",
            "Semanal por sección",
        ],
        default=[
            "Bitácora MGM / M1 (diario)",
            "Turnos 1 / 2 / 3",
            "Registro 4 horarios (consumo)",
            "Semanal planta vs límite",
        ],
    )

    # Shared date window from whatever exists
    bounds = []
    if not bitacora.empty:
        bounds += list(pd.to_datetime(bitacora["Date"], errors="coerce").dropna())
    if not daily_df.empty:
        bounds += list(pd.to_datetime(daily_df["Date"], errors="coerce").dropna())
    if not registro.empty:
        bounds += list(pd.to_datetime(registro["Date"], errors="coerce").dropna())
    if bounds:
        min_date = min(bounds).date()
        max_date = max(bounds).date()
        total_days = max((max_date - min_date).days, 1)
        window_size = st.slider("Ventana (días)", 1, total_days, min(30, total_days))
        max_start = max_date - datetime.timedelta(days=window_size)
        if max_start <= min_date:
            start_date = min_date
        else:
            start_date = st.slider(
                "Inicio",
                min_value=min_date,
                max_value=max_start,
                value=max_start,
                format="MMM DD, YYYY",
            )
        end_date = start_date + datetime.timedelta(days=window_size)
        st.write(f"**{start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}**")
    else:
        start_date = end_date = None
        st.info("No hay fechas en los CSV.")

    def in_window(frame: pd.DataFrame, col: str = "Date") -> pd.DataFrame:
        if frame.empty or start_date is None:
            return frame
        out = frame.copy()
        out[col] = pd.to_datetime(out[col], errors="coerce")
        return out[(out[col].dt.date >= start_date) & (out[col].dt.date <= end_date)]

    if "Bitácora MGM / M1 (diario)" in series:
        st.subheader("Bitácora diaria · MGM y M1")
        b = in_window(bitacora)
        if b.empty:
            st.info("Sin bitácora en esa ventana.")
        else:
            st.area_chart(b.set_index("Date")[["Consumo_MGM_m3", "Consumo_M1_m3"]].fillna(0))

    if "Turnos 1 / 2 / 3" in series:
        st.subheader("Consumo por turno")
        d = in_window(daily_df)
        if d.empty:
            st.info("Sin turnos en esa ventana.")
        else:
            st.area_chart(d.set_index("Date")[["Shift_1_m3", "Shift_2_m3", "Shift_3_m3"]])

    if "Registro 4 horarios (lecturas)" in series:
        st.subheader("Registro de lecturas · medidor")
        r = in_window(registro)
        if r.empty:
            st.info("Sin registro en esa ventana.")
        else:
            cols = [c for c, _ in REGISTRO_SLOTS if c in r.columns]
            st.line_chart(r.set_index("Date")[cols])

    if "Registro 4 horarios (consumo)" in series:
        st.subheader("Registro de lecturas · consumo automático")
        derived = daily_consumption_from_meters(registro)
        derived = in_window(derived)
        if derived.empty:
            st.info("No se pudo calcular consumo del registro.")
        else:
            st.bar_chart(derived.set_index("Date")[["Consumo_MGM_m3", "Consumo_M1_m3"]].fillna(0))
            st.caption("Consumo del día = última lectura del día − última lectura del día anterior.")

    if "Semanal planta vs límite" in series:
        st.subheader("Semanal planta")
        if weekly_plant.empty:
            st.info("Sin semanal de planta.")
        else:
            wp = weekly_plant.copy()
            st.line_chart(
                wp.set_index("Week_Number")[
                    ["Consumo_MGM_m3", "Limite_MGM_m3", "Consumo_M1_m3", "Limite_M1_m3"]
                ]
            )

    if "Semanal por sección" in series:
        st.subheader("Semanal Purifika / Sanitarios / Diecast")
        if weekly_df.empty:
            st.info("Sin semanal por sección.")
        else:
            st.bar_chart(
                weekly_df.set_index("Week_Number")[
                    ["Area1_Purifika_m3", "Area2_Sanitarios_m3", "Area3_Fundition_m3"]
                ]
            )

# ── Simulation ────────────────────────────────────────────────────────────────
elif menu == "Simulation":
    st.header("Simulation")
    action = st.text_input("Proposed action:")
    savings = st.number_input("Estimated weekly savings (m³):", min_value=0.0, value=50.0)
    if st.button("Simulate") and action:
        st.success(
            f"Action '{action}' reduces annual consumption by {savings * 52:,.2f} m³."
        )

# ── New Data ──────────────────────────────────────────────────────────────────
elif menu == "New Data":
    st.header("Log Data")
    tab_reg, tab_manual, tab_telegram = st.tabs(
        ["📋 Registro de lecturas", "✏️ Secciones semanales", "📱 Telegram"]
    )

    with tab_reg:
        st.caption(
            "Misma plantilla que la hoja **Registro de lecturas 2026**: "
            "un día, cuatro horarios, dos plantas. El consumo no se teclea — "
            "se calcula con la lectura anterior."
        )
        preview = daily_consumption_from_meters(registro)
        if not registro.empty:
            st.dataframe(
                registro.sort_values("Date", ascending=False).head(10),
                use_container_width=True,
            )
        if not preview.empty:
            last = preview.dropna(subset=["MGM_last"]).iloc[-1] if preview["MGM_last"].notna().any() else None
            cols = st.columns(2)
            if last is not None:
                cols[0].metric("Última lectura MGM", f"{last['MGM_last']:.2f} m³")
                cols[1].metric("Última lectura M1", f"{last['M1_last']:.2f} m³" if pd.notna(last["M1_last"]) else "—")

        defaults = {c: 0.0 for c, _ in REGISTRO_SLOTS}
        if not registro.empty:
            last_row = registro.sort_values("Date").iloc[-1]
            for c, _ in REGISTRO_SLOTS:
                if c in last_row and pd.notna(last_row[c]):
                    defaults[c] = float(last_row[c])

        with st.form("registro_form"):
            st.markdown("**Día**")
            dcol1, dcol2 = st.columns(2)
            with dcol1:
                reading_date = st.date_input("Fecha de lectura")
            with dcol2:
                st.write("Horarios fijos: 01:00 a.m. · 05:30 a.m. · 04:00 p.m. · 09:30 p.m.")

            st.markdown("**MGM — lectura actual (m³)**")
            mgm_cols = st.columns(4)
            mgm_vals = {}
            labels_mgm = ["01:00 a.m.", "05:30 a.m.", "04:00 p.m.", "09:30 p.m."]
            for col, key, lab in zip(mgm_cols, MGM_SLOTS, labels_mgm):
                with col:
                    mgm_vals[key] = st.number_input(lab, min_value=0.0, value=float(defaults[key]), key=f"in_{key}")

            st.markdown("**M1 — lectura actual (m³)**")
            m1_cols = st.columns(4)
            m1_vals = {}
            for col, key, lab in zip(m1_cols, M1_SLOTS, labels_mgm):
                with col:
                    m1_vals[key] = st.number_input(lab, min_value=0.0, value=float(defaults[key]), key=f"in_{key}")

            submitted = st.form_submit_button("💾 Guardar día")

        if submitted:
            row = {"Date": reading_date.isoformat(), **mgm_vals, **m1_vals}
            upsert_registro(row)
            tmp = _read_csv_resilient(REGISTRO_CSV)
            derived = daily_consumption_from_meters(tmp)
            hit = derived[pd.to_datetime(derived["Date"]).dt.date == reading_date]
            if hit.empty:
                st.success("Lecturas guardadas. Falta el día previo para calcular consumo.")
            else:
                rec = hit.iloc[-1]
                mgm_c = rec["Consumo_MGM_m3"]
                m1_c = rec["Consumo_M1_m3"]
                warn = []
                if pd.notna(mgm_c) and mgm_c < 0:
                    warn.append(f"MGM dio {mgm_c:.2f} m³ (lectura menor que ayer — revisar).")
                if pd.notna(m1_c) and m1_c < 0:
                    warn.append(f"M1 dio {m1_c:.2f} m³ (lectura menor que ayer — revisar).")
                st.success(
                    f"Día {reading_date.isoformat()} guardado. "
                    f"Consumo automático: MGM {0 if pd.isna(mgm_c) else mgm_c:.2f} m³ · "
                    f"M1 {0 if pd.isna(m1_c) else m1_c:.2f} m³."
                )
                for w in warn:
                    st.warning(w)
                st.rerun()

    with tab_manual:
        with st.form("new_data_form"):
            week = st.number_input("Week Number", min_value=1, max_value=52, step=1)
            total = st.number_input("Total Inlet (m³)", min_value=0.0)
            a1 = st.number_input("Area 1 Purifika (m³)", min_value=0.0)
            a2 = st.number_input("Area 2 Sanitarios (m³)", min_value=0.0)
            if st.form_submit_button("💾 Save"):
                if total < (a1 + a2):
                    st.error("Total cannot be less than Area 1 + Area 2.")
                else:
                    row = report_to_weekly_row(int(week), float(total), float(a1), float(a2))
                    append_weekly_rows([row])
                    st.success(f"Saved. Diecast estimado {row['Area3_Fundition_m3']:.2f} m³.")

    with tab_telegram:
        st.caption("`semana 19 / total 250 / area1 50 / area2 80`  o  `19, 250, 50, 80`")
        if st.button("🔄 Fetch from Telegram", type="primary"):
            with st.spinner("Connecting to Telegram..."):
                total_msgs, valid_msgs = fetch_from_telegram()
            if total_msgs == 0:
                st.info("No new messages on Telegram.")
            else:
                st.success(f"{total_msgs} mensaje(s), {valid_msgs} válido(s).")
        buffer = load_buffer()
        if not buffer:
            st.info("Buffer vacío.")
        else:
            preview_rows = []
            for r in buffer:
                preview_rows.append(
                    {
                        "Semana": r["week"],
                        "Total": r["total"],
                        "Purifika": r["area1"],
                        "Sanitarios": r["area2"],
                        "Diecast": round(r["total"] - r["area1"] - r["area2"], 2),
                    }
                )
            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True)
            if st.button("💾 Save all to CSV", type="primary"):
                rows = [
                    report_to_weekly_row(r["week"], r["total"], r["area1"], r["area2"])
                    for r in buffer
                ]
                append_weekly_rows(rows)
                clear_buffer()
                st.success(f"{len(rows)} reporte(s) guardados.")
                st.rerun()
