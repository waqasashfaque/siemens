import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime
from koboextractor import KoboExtractor

# USERNAME and PASSWORD 
USER = "admin"
PASS = "mypassword"

if 'auth' not in st.session_state:
    st.session_state['auth'] = False
if 'show_dashboard' not in st.session_state:
    st.session_state['show_dashboard'] = False

def login_form():
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == USER and password == PASS:
            st.session_state['auth'] = True
            st.success("Login successful! 🚀")
        else:
            st.error("Invalid credentials!")

# Auth Logic
if not st.session_state['auth']:
    login_form()
    st.stop()
elif not st.session_state['show_dashboard']:
    st.success("Login successful! 🚀")
    if st.button("View Dashboard"):
        st.session_state['show_dashboard'] = True
        st.rerun()
    st.stop()
    
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
#Getting live data

if st.button("🔄 Sync Latest Data"):
    st.cache_data.clear()

try:
    data1, data2 = fetch_kobo_data()
    df = process_kobo_data(data1, data2)
except Exception as e:
    st.error(f"Error occurred: {e}")
    st.stop()

st.set_page_config(page_title="Complaint Dashboard", layout="wide")
st.title("📊 Home Appliances Care - Complaints Management System Dashboard")

# Filters (under the title and above KPIs)
#st.subheader("🔎 Filters")

years = ['All Years'] + sorted(df['Year'].dropna().unique().tolist())
months = ['All Months'] + [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun','Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
technicians = ['All Technicians'] + sorted(df['Technician_Name'].unique())
channels = ['All Channels'] + sorted(df['complaint_channel'].dropna().unique())

f1, f2, f3, f4 = st.columns([2,2,2,2])
with f1:
    selected_year = st.multiselect("Select Year", years, default='All Years')
with f2:
    selected_month = st.multiselect("Select Month", months, default='All Months')
with f3:
    selected_technician = st.multiselect("Select Technician", technicians, default='All Technicians')
with f4:
    selected_channel = st.multiselect("Select Complaint Channel", channels, default='All Channels')

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

# KPIs as horizontal colored cards (each box different color, white bold text)

st.markdown(
    """
    <style>.kpi-card {border-radius: 12px;padding: 20px 10px 10px 10px;margin: 5px;box-shadow: 2px 2px 10px #e6e6e6;text-align: center;
    }.kpi-label {color: #fff;font-size: 1em;font-weight: bold;}.kpi-value {font-size: 2em;color: #fff;font-weight: bold;
    }.kpi-blue {background-color: #1976d2;}.kpi-green {background-color: #43a047;}.kpi-yellow {background-color: #fbc02d;}.kpi-orange {background-color: #f57c00;}.kpi-red {background-color: #d32f2f;}
    </style>
    """,
    unsafe_allow_html=True
)

col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
with col1:
    st.markdown(f'<div class="kpi-card kpi-blue"><div class="kpi-label">📝 Total Complaints</div><div class="kpi-value">{len(filtered)}</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="kpi-card kpi-green"><div class="kpi-label">✅ Resolved/Closed</div><div class="kpi-value">{len(filtered[filtered["C_Job_Status"] == "Resolved_Closed"])}</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="kpi-card kpi-yellow"><div class="kpi-label">⏳ Pending</div><div class="kpi-value">{len(filtered[filtered["C_Job_Status"] == "Pending"])}</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="kpi-card kpi-orange"><div class="kpi-label">🚶‍♂️ Not Visited</div><div class="kpi-value">{len(filtered[filtered["C_Job_Status"] == "Not Visited Yet"])}</div></div>', unsafe_allow_html=True)
with col5:
    st.markdown(f'<div class="kpi-card kpi-red"><div class="kpi-label">❌ Cancelled</div><div class="kpi-value">{len(filtered[filtered["C_Job_Status"] == "Cancelled"])}</div></div>', unsafe_allow_html=True)
with col6:
    st.markdown(f'<div class="kpi-card kpi-yellow"><div class="kpi-label">📵 Not Attending</div><div class="kpi-value">{len(filtered[filtered["C_Job_Status"] == "Not_attending"])}</div></div>', unsafe_allow_html=True)
with col7:
    st.markdown(f'<div class="kpi-card kpi-blue"><div class="kpi-label">💰 Revenue (PKR)</div><div class="kpi-value">{int(filtered["Total_C_Amount"].sum())}</div></div>', unsafe_allow_html=True)

# KPI-style blue title box
import streamlit as st
import plotly.express as px

st.markdown("<div style='height:25px;'></div>", unsafe_allow_html=True)

def chart_title_box(title):
    st.markdown(
        f"""
        <div style="background: linear-gradient(90deg,#1976d2,#2196f3);border-radius:10px;padding:10px;margin-bottom:5px;text-align:center;color:#fff;font-weight:bold;font-size:20px;">
            {title}</div>""",unsafe_allow_html=True)

# Disable zoom/pan config
def no_zoom(fig):
    fig.update_layout(
        dragmode=False,
        xaxis=dict(fixedrange=True),
        yaxis=dict(fixedrange=True),
    )
    return fig

if not filtered.empty:
    # First row
    c1, c2 = st.columns(2)
    with c1:
        chart_title_box("Complaint Channels")
        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
        pie_data = filtered['complaint_channel'].value_counts().reset_index()
        pie_data.columns = ['Complaint Channel', 'Count']
        fig1 = px.pie(pie_data, names='Complaint Channel', values='Count')
        fig1.update_layout(title=None, margin=dict(t=0), legend=dict(orientation="h",yanchor="bottom",y=-0.2,xanchor="center",x=0.5))
        fig1 = no_zoom(fig1)
        st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})
    with c2:
        chart_title_box("Monthly Job Types")
        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
        job_month = filtered.groupby(['MONTH', 'Job_Type']).size().reset_index(name='Count')
        job_month = job_month.sort_values('MONTH')
        fig2 = px.bar(job_month, x='MONTH', y='Count', color='Job_Type', barmode='group')
        fig2.update_layout(title=None,xaxis_title=None,margin=dict(t=0),legend=dict(orientation="h",yanchor="bottom",y=-0.2,xanchor="center",x=0.5))
        fig2 = no_zoom(fig2)
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    # Second row
    c3, c4 = st.columns(2)
    with c3:
        chart_title_box("Products Complaints - Top 5")
        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
        top_products = filtered['Product_classification'].value_counts().head(5).reset_index()
        top_products.columns = ['Product', 'Count']
        fig3 = px.bar(top_products, x='Product', y='Count')
        fig3.update_layout(title=None,xaxis_title=None,margin=dict(t=0),legend=dict(orientation="h",yanchor="bottom",y=-0.2,xanchor="center",x=0.5))
        fig3 = no_zoom(fig3)
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
    with c4:
        chart_title_box("Monthly Complaint Trend")
        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
        monthly_trend = filtered.groupby('MONTH').size().reset_index(name='Count')
        monthly_trend = monthly_trend.sort_values('MONTH')
        fig4 = px.line(monthly_trend, x='MONTH', y='Count', markers=True)
        fig4.update_layout(title=None,xaxis_title=None,margin=dict(t=0),legend=dict(orientation="h",yanchor="bottom",y=-0.2,xanchor="center",x=0.5))
        fig4 = no_zoom(fig4)
        st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})
#else:
   #st.warning("No data available for selected filters.")
