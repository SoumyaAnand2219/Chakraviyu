import streamlit as st
import pandas as pd
import numpy as np
import datetime as dt
import pyotp
from SmartApi.smartConnect import SmartConnect
import plotly.graph_objects as go
from scipy import stats
import time
import warnings

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Cycle Detection Scanner", layout="wide")
st.title("📊 30–45 Day Cycle Detection Scanner (Angel One)")

# ================= LOGIN =================
api_key = "g5o6vfTl"
client_id = "R59803990"
password = "1234"
totp_secret = "5W4MC6MMLANC3UYOAW2QDUIFEU"

@st.cache_resource
def angel_login():
    obj = SmartConnect(api_key=api_key)
    totp = pyotp.TOTP(totp_secret).now()
    obj.generateSession(client_id, password, totp)
    return obj

try:
    obj = angel_login()
    st.success("Login Successful")
except:
    st.error("Login Failed")
    st.stop()

# ================= STOCK TOKENS =================
from Stock_tokens import stock_list

# ================= FETCH DATA =================
def fetch_data(token):
    try:
        params = {
            "exchange": "NSE",
            "symboltoken": str(token),
            "interval": "ONE_DAY",
            "fromdate": "2000-01-01 09:15",
            "todate": dt.datetime.now().strftime("%Y-%m-%d 15:30"),
        }

        response = obj.getCandleData(params)

        if not response or response["status"] != True:
            return None

        df = pd.DataFrame(response["data"],
                          columns=["Date","Open","High","Low","Close","Volume"])

        df["Date"] = pd.to_datetime(df["Date"])
        df["Close"] = df["Close"].astype(float)

        return df

    except:
        return None

# ================= CYCLE DETECTION =================
def identify_cycles(data, threshold):

    cycles = []
    i = 0
    n = len(data)

    while i < n - 1:

        start_date = data['Date'][i]
        start_price = data['Close'][i]

        for j in range(i+1, min(i+46, n)):

            end_date = data['Date'][j]
            end_price = data['Close'][j]

            days = (end_date - start_date).days
            pct_change = ((end_price - start_price) / start_price) * 100

            if 30 <= days <= 45 and pct_change > threshold:

                cycles.append({
                    'Start Date': start_date,
                    'End Date': end_date,
                    'Duration Days': days,
                    'Return %': round(pct_change,2)
                })

                i = j
                break
        else:
            i += 1

    return pd.DataFrame(cycles)

# ================= SEASONALITY FIXED =================
def analyze_seasonality(cycles):

    cycles['Start Month'] = cycles['Start Date'].dt.month

    # Force all 12 months to exist
    month_counts = cycles['Start Month'].value_counts().reindex(range(1,13), fill_value=0)

    observed = month_counts.values
    expected = np.full(12, cycles.shape[0] / 12)

    chi2, p_value = stats.chisquare(f_obs=observed, f_exp=expected)

    return month_counts, chi2, p_value

# ================= NEXT CYCLE =================
def predict_next_cycle(cycles):

    if cycles.empty:
        return None

    most_common_month = cycles['Start Month'].mode()[0]
    today = pd.Timestamp.today()

    year = today.year if today.month <= most_common_month else today.year + 1

    return pd.Timestamp(year=year, month=most_common_month, day=1)

# ================= TABS =================
tab1, tab2 = st.tabs(["📦 Batch Scanner", "📊 Single Stock Analysis"])

# ======================================================
# ================= TAB 1 ===============================
# ======================================================
with tab1:

    st.subheader("Batch Cycle Scanner")

    threshold = st.number_input("Return Threshold %", value=30.0)

    items = list(stock_list.items())
    batch_size = 40
    batches = [items[i:i+batch_size] for i in range(0,len(items),batch_size)]

    batch_no = st.selectbox("Select Batch", list(range(1,len(batches)+1)))

    if st.button("Run Batch Scan"):

        results = []
        overall_month_tracker = []

        selected_batch = batches[batch_no-1]
        progress = st.progress(0)

        for i,(symbol,token) in enumerate(selected_batch):

            df = fetch_data(token)

            if df is not None:

                cycles = identify_cycles(df, threshold)

                if not cycles.empty:

                    cycles['Start Month'] = cycles['Start Date'].dt.month

                    most_common_month = cycles['Start Month'].mode()[0]
                    avg_return = cycles["Return %"].mean()

                    overall_month_tracker.extend(cycles['Start Month'].tolist())

                    month_name = ['Jan','Feb','Mar','Apr','May','Jun',
                                  'Jul','Aug','Sep','Oct','Nov','Dec'][most_common_month-1]

                    results.append({
                        "Symbol":symbol,
                        "Cycle Count":len(cycles),
                        "Avg Return %":round(avg_return,2),
                        "Peak Month":month_name
                    })

            progress.progress((i+1)/len(selected_batch))
            time.sleep(0.5)   # rate-limit protection

        if results:

            result_df = pd.DataFrame(results)
            st.dataframe(result_df, use_container_width=True)

            # ===== OVERALL HISTOGRAM =====
            st.subheader("📊 Overall Month Distribution (All Stocks)")

            overall_series = pd.Series(overall_month_tracker)
            overall_counts = overall_series.value_counts().reindex(range(1,13), fill_value=0)

            peak_month = overall_counts.idxmax()
            peak_month_name = ['Jan','Feb','Mar','Apr','May','Jun',
                               'Jul','Aug','Sep','Oct','Nov','Dec'][peak_month-1]

            st.success(f"🔥 Strongest Month Overall: {peak_month_name}")

            month_names = ['Jan','Feb','Mar','Apr','May','Jun',
                           'Jul','Aug','Sep','Oct','Nov','Dec']

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=month_names,
                y=overall_counts.values
            ))

            fig.update_layout(height=400, template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)

        else:
            st.warning("No cycles found")

# ======================================================
# ================= TAB 2 ===============================
# ======================================================
with tab2:

    st.subheader("Single Stock Deep Analysis")

    selected_stock = st.selectbox("Select Stock", list(stock_list.keys()))
    threshold_single = st.number_input("Return Threshold %", value=30.0, key="single_threshold")

    if st.button("Analyze Stock"):

        token = stock_list[selected_stock]
        df = fetch_data(token)

        if df is None:
            st.error("Data not available")
        else:

            cycles = identify_cycles(df, threshold_single)

            if cycles.empty:
                st.warning("No cycles found")
            else:

                month_counts, chi2, p_value = analyze_seasonality(cycles)

                col1,col2,col3 = st.columns(3)
                col1.metric("Total Cycles", len(cycles))
                col2.metric("Chi-Square", round(chi2,2))
                col3.metric("P-Value", round(p_value,4))

                if p_value < 0.10:
                    st.success("Seasonality statistically significant")
                else:
                    st.warning("Seasonality not statistically significant")

                next_cycle = predict_next_cycle(cycles)

                if next_cycle:
                    st.info(f"Next likely cycle month: {next_cycle.strftime('%Y-%m-%d')}")

                st.dataframe(cycles)

                # ===== PRICE CHART =====
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df["Date"],
                    y=df["Close"],
                    mode='lines',
                    name="Close Price"
                ))

                for _,cycle in cycles.iterrows():
                    fig.add_vrect(
                        x0=cycle["Start Date"],
                        x1=cycle["End Date"],
                        fillcolor="orange",
                        opacity=0.3,
                        line_width=0
                    )

                fig.update_layout(height=600, template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)

                # ===== MONTH HISTOGRAM =====
                month_names = ['Jan','Feb','Mar','Apr','May','Jun',
                               'Jul','Aug','Sep','Oct','Nov','Dec']

                fig2 = go.Figure()
                fig2.add_trace(go.Bar(
                    x=month_names,
                    y=month_counts.values
                ))

                fig2.update_layout(height=400, template="plotly_dark")
                st.plotly_chart(fig2, use_container_width=True)
