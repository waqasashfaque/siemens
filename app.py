import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime
from koboextractor import KoboExtractor

# --- API Configuration from Streamlit secrets ---
my_token = st.secrets["MY_TOKEN"]
form_id_main = st.secrets["FORM_ID_MAIN"]
form_id_child = st.secrets["FORM_ID_CHILD"]
kobo_base_url = st.secrets["KOBO_BASE_URL"]

@st.cache_data(show_spinner=True)
def fetch_kobo_data():
    kobo = KoboExtractor(my_token, kobo_base_url)
    data1 = kobo.get_data(form_id_main)
    data2 = kobo.get_data(form_id_child)
    return data1, data2

def process_kobo_data(data1, data2):
    df1 = pd.json_normalize(data1.get('results', []))
    df2 = pd.json_normalize(data2.get('results', []))

    if not df1.empty:
        df1.columns = df1.columns.str.replace('Registration/', '')
        selected_cols_df1 = ['S_Num', 'Job_Type', 'Complaint_Reg_Date', 'Product_classification', 'complaint_channel']
        df1 = df1[[col for col in selected_cols_df1 if col in df1.columns]]

    if not df2.empty:
        df2.columns = df2.columns.str.replace('C_Followup/', '')
        df2.columns = df2.columns.str.replace('C_Registration/', '')
        df2.columns = df2.columns.str.replace('C_invoice_group/', '')
        selected_cols_df2 = ['C_id_nb', 'C_Technician_Did', 'C_Job_Status', 'C_Payment_status', 'C_Payment_mode', 'C_Amount', 'C_Technician_received', '_submission_time']
        df2 = df2[[col for col in selected_cols_df2 if col in df2.columns]]
        df2.rename(columns={'C_id_nb': 'S_Num'}, inplace=True)
        df2['_submission_time'] = pd.to_datetime(df2['_submission_time'], errors='coerce')
        df2.sort_values(by=['S_Num', '_submission_time'], inplace=True)
        latest_status = df2.drop_duplicates('S_Num', keep='last')[['S_Num', 'C_Job_Status', 'C_Technician_Did']]
        df2['C_Amount'] = pd.to_numeric(df2['C_Amount'], errors='coerce').fillna(0)
        revenue = df2.groupby('S_Num')['C_Amount'].sum().reset_index(name='Total_C_Amount')
    else:
        latest_status = pd.DataFrame(columns=['S_Num', 'C_Job_Status', 'C_Technician_Did'])
        revenue = pd.DataFrame(columns=['S_Num', 'Total_C_Amount'])

    merged = pd.merge(df1, latest_status, on='S_Num', how='left')
    merged = pd.merge(merged, revenue, on='S_Num', how='left')
    merged['C_Job_Status'].fillna('Not Visited Yet', inplace=True)
    merged['Total_C_Amount'].fillna(0, inplace=True)
    merged['Complaint_Reg_Date'] = pd.to_datetime(merged['Complaint_Reg_Date'], errors='coerce')
    merged.dropna(subset=['Complaint_Reg_Date'], inplace=True)
    merged['MONTH'] = merged['Complaint_Reg_Date'].dt.strftime('%b')
    # Set MONTH as categorical with calendar order
    month_order = [
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun','Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ]
    merged['MONTH'] = pd.Categorical(merged['MONTH'], categories=month_order, ordered=True)
    merged['Year'] = merged['Complaint_Reg_Date'].dt.year
    merged['Technician_Name'] = merged['C_Technician_Did'].fillna('Not Assigned')

    return merged

# --- Streamlit UI Starts Here ---
st.set_page_config(page_title="Complaint Dashboard", layout="wide")
st.title("📊 Home Appliances Care - Complaint Management Dashboard")

if st.button("🔄 Sync Latest Data"):
    st.cache_data.clear()

try:
    data1, data2 = fetch_kobo_data()
    df = process_kobo_data(data1, data2)
except Exception as e:
    st.error(f"Error occurred: {e}")
    st.stop()

# Sidebar Filters
st.sidebar.header("⚙️ Filters")
years = ['All Years'] + sorted(df['Year'].dropna().unique().tolist())
months = ['All Months'] + [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December']
technicians = ['All Technicians'] + sorted(df['Technician_Name'].unique())
channels = ['All Channels'] + sorted(df['complaint_channel'].dropna().unique())

selected_year = st.sidebar.multiselect("Select Year", years, default='All Years')
selected_month = st.sidebar.multiselect("Select Month", months, default='All Months')
selected_technician = st.sidebar.multiselect("Select Technician", technicians, default='All Technicians')
selected_channel = st.sidebar.multiselect("Select Channel", channels, default='All Channels')

# Filter logic
filtered = df.copy()
if 'All Years' not in selected_year:
    filtered = filtered[filtered['Year'].isin(selected_year)]
if 'All Months' not in selected_month:
    filtered = filtered[filtered['MONTH'].isin(selected_month)]
if 'All Technicians' not in selected_technician:
    filtered = filtered[filtered['Technician_Name'].isin(selected_technician)]
if 'All Channels' not in selected_channel:
    filtered = filtered[filtered['complaint_channel'].isin(selected_channel)]

# KPIs
col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
col1.metric("📝 Total Complaints", len(filtered))
col2.metric("✅ Resolved", len(filtered[filtered['C_Job_Status'] == 'Resolved_Closed']))
col3.metric("⏳ Pending", len(filtered[filtered['C_Job_Status'] == 'Pending']))
col4.metric("🚶‍♂️ Not Visited", len(filtered[filtered['C_Job_Status'] == 'Not Visited Yet']))
col5.metric("❌ Cancelled", len(filtered[filtered['C_Job_Status'] == 'Cancelled']))
col6.metric("📵 Not Attending", len(filtered[filtered['C_Job_Status'] == 'Not_attending']))
col7.metric("💰 Revenue (PKR)", int(filtered['Total_C_Amount'].sum()))

# Charts
c1, c2 = st.columns(2)
if not filtered.empty:
    with c1:
        pie_data = filtered['complaint_channel'].value_counts().reset_index()
        pie_data.columns = ['Complaint Channel', 'Count']
        fig1 = px.pie(pie_data, names='Complaint Channel', values='Count', hole=0.3, title="Complaint Channels")
        st.plotly_chart(fig1, use_container_width=True)
    with c2:
        job_month = filtered.groupby(['MONTH', 'Job_Type']).size().reset_index(name='Count')
        job_month = job_month.sort_values('MONTH')  # Sort by calendar month
        fig2 = px.bar(job_month, x='MONTH', y='Count', color='Job_Type', title="Monthly Job Types", barmode='group')
        st.plotly_chart(fig2, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        top_products = filtered['Product_classification'].value_counts().head(5).reset_index()
        top_products.columns = ['Product', 'Count']
        fig3 = px.bar(top_products, x='Product', y='Count', title="Top 5 Product Complaints")
        st.plotly_chart(fig3, use_container_width=True)
    with c4:
        monthly_trend = filtered.groupby('MONTH').size().reset_index(name='Count')
        monthly_trend = monthly_trend.sort_values('MONTH')  # Sort by calendar month
        fig4 = px.line(monthly_trend, x='MONTH', y='Count', markers=True, title="Monthly Complaint Trend")
        st.plotly_chart(fig4, use_container_width=True)
else:
    st.warning("No data available for selected filters.")
