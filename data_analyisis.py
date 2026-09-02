import pandas as pd
import streamlit as st
import datetime

st.set_page_config(page_title="Water consumption tracker", layout="wide")

def load_data():
    historical_df = pd.read_csv("dataset/monthly_consumption.csv")
    weekly_df = pd.read_csv("dataset/weekly_consumption.csv")
    daily_df = pd.read_csv("dataset/daily_shift_consumption.csv")
    return historical_df, weekly_df, daily_df

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
        
        st.line_chart(melted_df[['Consumption']])

elif menu == "Discrepancy":
    st.header("Discrepancy & Anomaly Log")
    
    if not weekly_df.empty:
        anomaly_mask = (
            (weekly_df['Area1_Purifika_m3'] > limit_1) |
            (weekly_df['Area2_Sanitarios_m3'] > limit_2) |
            (weekly_df['Area3_Fundition_m3'] > limit_3) |
            (weekly_df['Area3_Fundition_m3'] < 0)
        )
        
        anomalies_df = weekly_df[anomaly_mask].copy()
        
        if anomalies_df.empty:
            st.success("All consumption metrics are within established limits.")
        else:
            st.error(f"Detected {len(anomalies_df)} weeks with limit breaches or calculation errors.")
            st.dataframe(anomalies_df.set_index('Week_Number'), use_container_width=True)
            
            st.subheader("Area 3 Trend vs Limit")
            chart_data = weekly_df[['Week_Number', 'Area3_Fundition_m3']].set_index('Week_Number')
            st.line_chart(chart_data)

elif menu == "Timeline":
    st.header("Timeline analysis")
    if not daily_df.empty:
        daily_df['Date'] = pd.to_datetime(daily_df['Date'])
        min_date = daily_df['Date'].min().date()
        max_date = daily_df['Date'].max().date()
        total_days = (max_date - min_date).days

        st.subheader("Timeline control")
        window_size = st.slider("Select Timeframe (Days):", min_value=1, max_value=total_days, value=14)
        max_start_date = max_date - datetime.timedelta(days=window_size)
            
        if max_start_date <= min_date:
            start_date = min_date
        else:
            start_date = st.slider(
                "Pan Timeline:",
                min_value=min_date,
                max_value=max_start_date,
                value=max_start_date,  
                format="MMM DD, YYYY"
            )
            
        end_date = start_date + datetime.timedelta(days=window_size)
        
        mask = (daily_df['Date'].dt.date >= start_date) & (daily_df['Date'].dt.date <= end_date)
        filtered_daily = daily_df.loc[mask].set_index('Date')
        
        st.subheader(f"Shift Trends ({start_date.strftime('%b %d')} - {end_date.strftime('%b %d')})")
        st.area_chart(filtered_daily[['Shift_1_m3', 'Shift_2_m3', 'Shift_3_m3']])

elif menu == "Simulation":
    st.header("Simulation")
    action = st.text_input("Proposed action:")
    savings = st.number_input("Estimated weekly savings (m³):", min_value=0.0, value=50.0)
    
    if st.button("Simulate") and action:
        st.success(f"Action '{action}' reduces the annual KPI by {savings * 52:,.2f} m³.")

elif menu == "New Data":
    st.header("Log Data")
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