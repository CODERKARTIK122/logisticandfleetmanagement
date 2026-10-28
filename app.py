import io
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ---------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------
st.set_page_config(
    page_title="Logistics & Fleet Management",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# CUSTOM STYLING
# ---------------------------------------------------------
st.markdown(
    """
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
        [data-testid="stMetric"] {
            background: #111827;
            border: 1px solid #263449;
            padding: 16px 18px;
            border-radius: 12px;
        }
        [data-testid="stMetricLabel"] {color: #cbd5e1;}
        [data-testid="stMetricValue"] {color: #ffffff;}
        div[data-testid="stSidebar"] {background-color: #0b1220;}
        .small-note {color: #94a3b8; font-size: 0.85rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

REQUIRED_COLUMNS = [
    "Vehicle_ID",
    "Vehicle_No",
    "Type",
    "Capacity_Kg",
    "Fuel_Type",
    "Current_Km",
    "Status",
    "Driver_ID",
]


# ---------------------------------------------------------
# DATA LOADING AND CLEANING
# ---------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_uploaded_file(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    buffer = io.BytesIO(file_bytes)
    suffix = Path(file_name).suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(buffer)
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(buffer)

    raise ValueError("Please upload a CSV or Excel file.")


def prepare_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    data = raw_df.copy()
    data.columns = data.columns.astype(str).str.strip()

    missing = [col for col in REQUIRED_COLUMNS if col not in data.columns]
    if missing:
        raise ValueError(
            "The uploaded dataset is missing these required columns: "
            + ", ".join(missing)
        )

    # Match the notebook's duplicate-removal and missing-value handling.
    data = data.drop_duplicates().copy()

    for col in ["Capacity_Kg", "Current_Km"]:
        data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    for col in ["Vehicle_ID", "Vehicle_No", "Type", "Fuel_Type", "Status", "Driver_ID"]:
        data[col] = data[col].fillna("Unknown").astype(str).str.strip()
        data.loc[data[col].eq(""), col] = "Unknown"

    # Keep zero as the notebook's unassigned-driver convention.
    data["Driver_ID"] = data["Driver_ID"].replace(
        {"0.0": "0", "nan": "Unknown", "None": "Unknown"}
    )

    if len(data) == 0:
        raise ValueError("The dataset has no records after duplicate removal.")

    # Same three-bin usage grouping used in the Kaggle notebook.
    if data["Current_Km"].nunique() >= 3:
        data["Usage_Level"] = pd.cut(
            data["Current_Km"],
            bins=3,
            labels=["Low", "Medium", "High"],
            include_lowest=True,
        ).astype("object")
    else:
        data["Usage_Level"] = "Low"
        data.loc[data["Current_Km"] == data["Current_Km"].max(), "Usage_Level"] = "High"

    data["Usage_Level"] = data["Usage_Level"].fillna("Low")
    return data


def format_number(value):
    return f"{value:,.0f}"


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------
st.title("🚚 Logistics & Fleet Management Platform")
st.caption(
    "Fleet performance | Vehicle status | Driver allocation | Usage analytics"
)

# ---------------------------------------------------------
# SIDEBAR: DATA SOURCE
# ---------------------------------------------------------
st.sidebar.title("⚙️ Control Panel")
st.sidebar.subheader("Dataset")

uploaded_file = st.sidebar.file_uploader(
    "Upload your fleet dataset",
    type=["xlsx", "xls", "csv"],
    help="Upload the Excel or CSV file used in your Kaggle notebook.",
)

raw_df = None
source_label = None

if uploaded_file is not None:
    try:
        raw_df = load_uploaded_file(uploaded_file.getvalue(), uploaded_file.name)
        source_label = uploaded_file.name
    except Exception as exc:
        st.error(f"Could not read the uploaded file: {exc}")
        st.stop()
else:
    # Optional local dataset paths. Put the Excel/CSV file beside app.py
    # or inside a data/ folder. The user can also upload it in the sidebar.
    possible_files = [
        Path("Logistics_Fleet_Management_Dataset-2.xlsx"),
        Path("Logistics_Fleet_Management_Dataset.xlsx"),
        Path("fleet_data.xlsx"),
        Path("fleet_data.csv"),
        Path("data/Logistics_Fleet_Management_Dataset-2.xlsx"),
        Path("data/fleet_data.xlsx"),
        Path("data/fleet_data.csv"),
    ]
    for candidate in possible_files:
        if candidate.exists():
            try:
                if candidate.suffix.lower() == ".csv":
                    raw_df = pd.read_csv(candidate)
                else:
                    raw_df = pd.read_excel(candidate)
                source_label = str(candidate)
                break
            except Exception:
                continue

if raw_df is None:
    st.info(
        "Upload the Excel/CSV dataset from your Kaggle notebook using the "
        "sidebar to open the dashboard."
    )
    st.markdown("### Expected dataset columns")
    st.code(", ".join(REQUIRED_COLUMNS), language="text")
    st.markdown(
        """
        **Deployment note:** Add your dataset to the GitHub repository beside
        `app.py`, or upload it after opening the Streamlit app.
        """
    )
    st.stop()

try:
    df = prepare_data(raw_df)
except Exception as exc:
    st.error(str(exc))
    st.stop()

st.sidebar.success(f"Loaded: {source_label}")
st.sidebar.caption(f"{len(df):,} records after duplicate removal")

# ---------------------------------------------------------
# SIDEBAR FILTERS
# ---------------------------------------------------------
st.sidebar.divider()
st.sidebar.subheader("🔎 Filters")

def multiselect_filter(label, column):
    values = sorted(df[column].dropna().astype(str).unique().tolist())
    return st.sidebar.multiselect(
        label,
        options=values,
        default=values,
    )

selected_types = multiselect_filter("Vehicle Type", "Type")
selected_fuels = multiselect_filter("Fuel Type", "Fuel_Type")
selected_statuses = multiselect_filter("Vehicle Status", "Status")
selected_usage = multiselect_filter("Usage Level", "Usage_Level")

filtered_df = df[
    df["Type"].astype(str).isin(selected_types)
    & df["Fuel_Type"].astype(str).isin(selected_fuels)
    & df["Status"].astype(str).isin(selected_statuses)
    & df["Usage_Level"].astype(str).isin(selected_usage)
].copy()

# ---------------------------------------------------------
# OVERVIEW DASHBOARD
# ---------------------------------------------------------
st.subheader("📊 Fleet Overview")

total_vehicles = filtered_df["Vehicle_ID"].nunique()
total_drivers = filtered_df.loc[
    ~filtered_df["Driver_ID"].isin(["0", "Unknown", ""])
    , "Driver_ID"
].nunique()
total_capacity = filtered_df["Capacity_Kg"].sum()
average_capacity = filtered_df["Capacity_Kg"].mean() if len(filtered_df) else 0
average_km = filtered_df["Current_Km"].mean() if len(filtered_df) else 0
active_vehicles = (
    filtered_df["Status"].str.strip().str.lower().eq("active").sum()
)
active_pct = (active_vehicles / len(filtered_df) * 100) if len(filtered_df) else 0
unassigned_count = filtered_df["Driver_ID"].isin(["0", "Unknown", ""]).sum()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Vehicles", format_number(total_vehicles))
m2.metric("Assigned Drivers", format_number(total_drivers))
m3.metric("Total Capacity", f"{format_number(total_capacity)} Kg")
m4.metric("Average Current Km", format_number(average_km))

m5, m6, m7, m8 = st.columns(4)
m5.metric("Active Vehicles", format_number(active_vehicles))
m6.metric("Active Fleet", f"{active_pct:.1f}%")
m7.metric("Average Capacity", f"{average_capacity:,.1f} Kg")
m8.metric("Unassigned Vehicles", format_number(unassigned_count))

if filtered_df.empty:
    st.warning("No records match the selected filters. Change the sidebar filters.")
    st.stop()

st.divider()

# ---------------------------------------------------------
# CHARTS
# ---------------------------------------------------------
st.subheader("📈 Fleet Analytics")

left, right = st.columns(2)

with left:
    status_data = filtered_df["Status"].value_counts().rename_axis("Status").reset_index(name="Vehicles")
    fig = px.pie(
        status_data,
        names="Status",
        values="Vehicles",
        hole=0.48,
        title="Vehicle Status Distribution",
    )
    fig.update_layout(legend_title_text="Status")
    st.plotly_chart(fig, use_container_width=True)

with right:
    fuel_data = filtered_df["Fuel_Type"].value_counts().rename_axis("Fuel Type").reset_index(name="Vehicles")
    fig = px.bar(
        fuel_data,
        x="Fuel Type",
        y="Vehicles",
        color="Fuel Type",
        title="Vehicles by Fuel Type",
        text="Vehicles",
    )
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)

with left:
    type_data = filtered_df["Type"].value_counts().rename_axis("Vehicle Type").reset_index(name="Vehicles")
    fig = px.bar(
        type_data,
        x="Vehicle Type",
        y="Vehicles",
        color="Vehicle Type",
        title="Number of Vehicles by Type",
        text="Vehicles",
    )
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with right:
    usage_order = ["Low", "Medium", "High"]
    usage_data = (
        filtered_df["Usage_Level"]
        .value_counts()
        .reindex(usage_order, fill_value=0)
        .rename_axis("Usage Level")
        .reset_index(name="Vehicles")
    )
    fig = px.bar(
        usage_data,
        x="Usage Level",
        y="Vehicles",
        color="Usage Level",
        title="Vehicle Usage Level",
        category_orders={"Usage Level": usage_order},
        text="Vehicles",
    )
    st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)

with left:
    avg_km_type = (
        filtered_df.groupby("Type", as_index=False)["Current_Km"]
        .mean()
        .sort_values("Current_Km", ascending=False)
    )
    fig = px.bar(
        avg_km_type,
        x="Type",
        y="Current_Km",
        color="Type",
        title="Average Current Km by Vehicle Type",
        labels={"Current_Km": "Average Current Km", "Type": "Vehicle Type"},
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    fig = px.scatter(
        filtered_df,
        x="Capacity_Kg",
        y="Current_Km",
        color="Fuel_Type",
        hover_data=["Vehicle_No", "Type", "Status", "Driver_ID"],
        title="Vehicle Capacity vs Current Km",
        labels={"Capacity_Kg": "Capacity (Kg)", "Current_Km": "Current Km"},
    )
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# VEHICLE AND FUEL ANALYSIS
# ---------------------------------------------------------
st.divider()
st.subheader("🚛 Vehicle & Capacity Analysis")

left, right = st.columns(2)

with left:
    capacity_type = (
        filtered_df.groupby("Type", as_index=False)["Capacity_Kg"]
        .mean()
        .sort_values("Capacity_Kg", ascending=False)
    )
    fig = px.bar(
        capacity_type,
        x="Type",
        y="Capacity_Kg",
        color="Type",
        title="Average Capacity by Vehicle Type",
        labels={"Capacity_Kg": "Average Capacity (Kg)", "Type": "Vehicle Type"},
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    capacity_fuel = (
        filtered_df.groupby(["Type", "Fuel_Type"], as_index=False)["Capacity_Kg"]
        .mean()
    )
    fig = px.bar(
        capacity_fuel,
        x="Type",
        y="Capacity_Kg",
        color="Fuel_Type",
        barmode="group",
        title="Average Capacity by Vehicle Type and Fuel",
        labels={"Capacity_Kg": "Average Capacity (Kg)", "Type": "Vehicle Type"},
    )
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# DRIVER ANALYSIS
# ---------------------------------------------------------
st.divider()
st.subheader("👨‍✈️ Driver Analysis")

driver_df = filtered_df[
    ~filtered_df["Driver_ID"].isin(["0", "Unknown", ""])
]
driver_counts = (
    driver_df.groupby("Driver_ID", as_index=False)["Vehicle_ID"]
    .nunique()
    .rename(columns={"Vehicle_ID": "Assigned Vehicles"})
    .sort_values("Assigned Vehicles", ascending=False)
    .head(10)
)

left, right = st.columns(2)

with left:
    if not driver_counts.empty:
        fig = px.bar(
            driver_counts,
            x="Driver_ID",
            y="Assigned Vehicles",
            color="Assigned Vehicles",
            title="Top 10 Drivers by Assigned Vehicles",
            text="Assigned Vehicles",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No assigned driver records are available for the selected filters.")

with right:
    st.metric("Unassigned Vehicles", format_number(unassigned_count))
    unassigned_df = filtered_df[
        filtered_df["Driver_ID"].isin(["0", "Unknown", ""])
    ]
    if not unassigned_df.empty:
        st.dataframe(
            unassigned_df[["Vehicle_ID", "Vehicle_No", "Type", "Status", "Driver_ID"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("All filtered vehicles have a driver ID.")

# ---------------------------------------------------------
# TOP VEHICLES
# ---------------------------------------------------------
st.divider()
st.subheader("🏆 Vehicle Highlights")

tab1, tab2, tab3 = st.tabs(
    ["Highest Usage", "Highest Capacity", "Lowest Usage"]
)

vehicle_columns = [
    "Vehicle_ID", "Vehicle_No", "Type", "Capacity_Kg",
    "Fuel_Type", "Current_Km", "Status", "Driver_ID", "Usage_Level"
]

with tab1:
    st.dataframe(
        filtered_df.sort_values("Current_Km", ascending=False)[vehicle_columns].head(10),
        use_container_width=True,
        hide_index=True,
    )

with tab2:
    st.dataframe(
        filtered_df.sort_values("Capacity_Kg", ascending=False)[vehicle_columns].head(10),
        use_container_width=True,
        hide_index=True,
    )

with tab3:
    st.dataframe(
        filtered_df.sort_values("Current_Km", ascending=True)[vehicle_columns].head(10),
        use_container_width=True,
        hide_index=True,
    )

# ---------------------------------------------------------
# FULL VEHICLE RECORDS
# ---------------------------------------------------------
st.divider()
st.subheader("📋 Vehicle Records")

search_text = st.text_input(
    "Search by Vehicle ID, Vehicle Number, or Driver ID",
    placeholder="Example: UP14BT4521",
)

records = filtered_df.copy()
if search_text.strip():
    query = search_text.strip().lower()
    mask = (
        records["Vehicle_ID"].str.lower().str.contains(query, na=False)
        | records["Vehicle_No"].str.lower().str.contains(query, na=False)
        | records["Driver_ID"].str.lower().str.contains(query, na=False)
    )
    records = records[mask]

sort_column = st.selectbox(
    "Sort records by",
    ["Current_Km", "Capacity_Kg", "Vehicle_No", "Type", "Status"],
    index=0,
)
sort_order = st.radio("Sort order", ["Descending", "Ascending"], horizontal=True)
records = records.sort_values(
    sort_column,
    ascending=(sort_order == "Ascending"),
)

st.caption(f"Showing {len(records):,} of {len(filtered_df):,} filtered records")
st.dataframe(records[vehicle_columns], use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# SUMMARY TABLES
# ---------------------------------------------------------
st.divider()
st.subheader("📑 Fleet Summary")

summary_by_type = (
    filtered_df.groupby("Type", as_index=False)
    .agg(
        Total_Vehicles=("Vehicle_ID", "nunique"),
        Avg_Capacity_Kg=("Capacity_Kg", "mean"),
        Avg_Current_Km=("Current_Km", "mean"),
    )
)
summary_by_type[["Avg_Capacity_Kg", "Avg_Current_Km"]] = (
    summary_by_type[["Avg_Capacity_Kg", "Avg_Current_Km"]].round(2)
)

st.dataframe(summary_by_type, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# DOWNLOADS
# ---------------------------------------------------------
st.divider()
st.subheader("⬇️ Download Reports")

csv_data = filtered_df[vehicle_columns].to_csv(index=False).encode("utf-8")
st.download_button(
    "Download filtered fleet data (CSV)",
    data=csv_data,
    file_name="fleet_management_final.csv",
    mime="text/csv",
)

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    filtered_df[vehicle_columns].to_excel(writer, sheet_name="Fleet Data", index=False)
    summary_by_type.to_excel(writer, sheet_name="Fleet Summary", index=False)

st.download_button(
    "Download fleet report (Excel)",
    data=excel_buffer.getvalue(),
    file_name="fleet_management_report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.markdown(
    '<p class="small-note">Logistics & Fleet Management Platform | '
    'Built with Streamlit, Pandas and Plotly</p>',
    unsafe_allow_html=True,
)
