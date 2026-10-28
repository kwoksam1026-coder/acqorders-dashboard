import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Orders Dashboard", layout="wide")


# -----------------------------
# Helpers
# -----------------------------
@st.cache_data
def load_excel(file):
    return pd.read_excel(file)


@st.cache_data
def load_excel_sheet(file, sheet_name):
    return pd.read_excel(file, sheet_name=sheet_name)


def normalize_cols(df):
    df.columns = [str(c).strip() for c in df.columns]
    return df


def find_sheet(xls, candidates):
    """Find sheet by exact (case-insensitive) or partial match."""
    sheets = xls.sheet_names
    lower_map = {s.lower().strip(): s for s in sheets}

    # exact match
    for c in candidates:
        key = c.lower().strip()
        if key in lower_map:
            return lower_map[key]

    # partial match
    for c in candidates:
        key = c.lower().strip()
        for s in sheets:
            if key in s.lower():
                return s

    return None


def validate_columns(df, needed, df_name):
    missing = [c for c in needed if c not in df.columns]
    if missing:
        st.error(f"Missing columns in {df_name}: {missing}")
        st.stop()


def calc_monthly_daily_avg(data, group_col, use_calendar_days=False):
    d = data.copy()
    d["Month"] = d["Date"].dt.to_period("M").dt.to_timestamp()

    grouped = (
        d.groupby(["Month", group_col], dropna=False)
        .agg(
            Total_Orders=("Number of Order", "sum"),
            Active_Days=("Date", "nunique"),
        )
        .reset_index()
    )

    if use_calendar_days:
        grouped["Days"] = grouped["Month"].dt.days_in_month
    else:
        grouped["Days"] = grouped["Active_Days"]

    grouped["Daily Avg Orders"] = grouped["Total_Orders"] / grouped["Days"].replace(0, pd.NA)
    return grouped


def plot_monthly_chart(monthly_df, group_col, title):
    fig = px.bar(
        monthly_df,
        x="Month",
        y="Daily Avg Orders",
        color=group_col,
        barmode="group",
        title=title,
    )
    fig.update_layout(
        xaxis_title="Month",
        yaxis_title="Daily Avg Orders",
        legend_title=group_col,
        height=450
    )
    st.plotly_chart(fig, use_container_width=True)


# -----------------------------
# App UI
# -----------------------------
st.title("📊 Monthly Daily Average Orders Dashboard")
st.caption("Upload Orders file + Mapping file. Then filter using 5 multi-select dropdowns.")

with st.sidebar:
    st.header("Upload Files")
    orders_file = st.file_uploader("Orders Excel (.xlsx)", type=["xlsx"])
    mapping_file = st.file_uploader("Mapping Excel (.xlsx)", type=["xlsx"])
    use_calendar_days = st.toggle("Use calendar days (instead of active days)", value=False)

if not orders_file or not mapping_file:
    st.info("Please upload both files to continue.")
    st.stop()

# -----------------------------
# Load Orders
# -----------------------------
orders = load_excel(orders_file)
orders = normalize_cols(orders)

required_orders_cols = [
    "1. Channel",
    "2. Sub Channel",
    "3. Program Desc (New)",
    "4. Bandwidth After Order",
    "5. Technology After Order",
    "6. Offer Description",
    "Date",
    "Number of Order",
]
validate_columns(orders, required_orders_cols, "Orders file")

orders["Date"] = pd.to_datetime(orders["Date"], errors="coerce")
orders["Number of Order"] = pd.to_numeric(orders["Number of Order"], errors="coerce")

orders = orders.dropna(subset=["Date", "Number of Order"]).copy()

# -----------------------------
# Load Mapping sheets
# -----------------------------
xls = pd.ExcelFile(mapping_file)

channel_sheet = find_sheet(xls, ["Channel Mapping", "Channel"])
program_sheet = find_sheet(xls, ["Program Mapping", "Program"])
bandwidth_sheet = find_sheet(xls, ["Bandwidth Mapping", "Bandwidth"])
technology_sheet = find_sheet(xls, ["Technology Mapping", "Technology"])
housing_sheet = find_sheet(xls, ["Housing Type Mapping", "Housing", "Offer"])

needed_sheets = {
    "Channel Mapping": channel_sheet,
    "Program Mapping": program_sheet,
    "Bandwidth Mapping": bandwidth_sheet,
    "Technology Mapping": technology_sheet,
    "Housing Type Mapping": housing_sheet,
}

missing_sheets = [k for k, v in needed_sheets.items() if v is None]
if missing_sheets:
    st.error(f"Could not find required mapping sheet(s): {missing_sheets}")
    st.write("Sheets found in your mapping file:", xls.sheet_names)
    st.stop()

channel_map = normalize_cols(load_excel_sheet(mapping_file, channel_sheet))
program_map = normalize_cols(load_excel_sheet(mapping_file, program_sheet))
bandwidth_map = normalize_cols(load_excel_sheet(mapping_file, bandwidth_sheet))
technology_map = normalize_cols(load_excel_sheet(mapping_file, technology_sheet))
housing_map = normalize_cols(load_excel_sheet(mapping_file, housing_sheet))

validate_columns(channel_map, ["1. Channel", "2. Sub Channel", "Channel Group"], channel_sheet)
validate_columns(program_map, ["3. Program Desc (New)", "Program Group"], program_sheet)
validate_columns(bandwidth_map, ["4. Bandwidth After Order", "Bandwidth Group"], bandwidth_sheet)
validate_columns(technology_map, ["5. Technology After Order", "Technology Group"], technology_sheet)
validate_columns(housing_map, ["6. Offer Description", "Housing Type"], housing_sheet)

# -----------------------------
# Merge mappings
# -----------------------------
df = orders.merge(
    channel_map[["1. Channel", "2. Sub Channel", "Channel Group"]],
    on=["1. Channel", "2. Sub Channel"],
    how="left",
)

df = df.merge(
    program_map[["3. Program Desc (New)", "Program Group"]],
    on=["3. Program Desc (New)"],
    how="left",
)

df = df.merge(
    bandwidth_map[["4. Bandwidth After Order", "Bandwidth Group"]],
    on=["4. Bandwidth After Order"],
    how="left",
)

df = df.merge(
    technology_map[["5. Technology After Order", "Technology Group"]],
    on=["5. Technology After Order"],
    how="left",
)

df = df.merge(
    housing_map[["6. Offer Description", "Housing Type"]],
    on=["6. Offer Description"],
    how="left",
)

# Fill unmapped
for c in ["Channel Group", "Program Group", "Bandwidth Group", "Technology Group", "Housing Type"]:
    df[c] = df[c].fillna("Unmapped")

# -----------------------------
# Filters (5 multi-select dropdowns)
# -----------------------------
st.sidebar.header("Filters")

channel_opts = sorted(df["Channel Group"].dropna().unique().tolist())
program_opts = sorted(df["Program Group"].dropna().unique().tolist())
bandwidth_opts = sorted(df["Bandwidth Group"].dropna().unique().tolist())
technology_opts = sorted(df["Technology Group"].dropna().unique().tolist())
housing_opts = sorted(df["Housing Type"].dropna().unique().tolist())

selected_channels = st.sidebar.multiselect("Channel", channel_opts, default=channel_opts)
selected_programs = st.sidebar.multiselect("Program", program_opts, default=program_opts)
selected_bandwidths = st.sidebar.multiselect("Bandwidth", bandwidth_opts, default=bandwidth_opts)
selected_technologies = st.sidebar.multiselect("Technology", technology_opts, default=technology_opts)
selected_housing = st.sidebar.multiselect("Housing Type", housing_opts, default=housing_opts)

filtered_df = df[
    df["Channel Group"].isin(selected_channels)
    & df["Program Group"].isin(selected_programs)
    & df["Bandwidth Group"].isin(selected_bandwidths)
    & df["Technology Group"].isin(selected_technologies)
    & df["Housing Type"].isin(selected_housing)
].copy()

st.write(f"Filtered rows: **{len(filtered_df):,}**")

if filtered_df.empty:
    st.warning("No data for selected filters. Please adjust your selections.")
    st.stop()

# -----------------------------
# Charts
# -----------------------------
st.subheader("Monthly Daily Average Orders")

c1, c2 = st.columns(2)
with c1:
    channel_monthly = calc_monthly_daily_avg(filtered_df, "Channel Group", use_calendar_days)
    plot_monthly_chart(channel_monthly, "Channel Group", "By Channel")

with c2:
    program_monthly = calc_monthly_daily_avg(filtered_df, "Program Group", use_calendar_days)
    plot_monthly_chart(program_monthly, "Program Group", "By Program")

c3, c4 = st.columns(2)
with c3:
    bandwidth_monthly = calc_monthly_daily_avg(filtered_df, "Bandwidth Group", use_calendar_days)
    plot_monthly_chart(bandwidth_monthly, "Bandwidth Group", "By Bandwidth")

with c4:
    technology_monthly = calc_monthly_daily_avg(filtered_df, "Technology Group", use_calendar_days)
    plot_monthly_chart(technology_monthly, "Technology Group", "By Technology")

housing_monthly = calc_monthly_daily_avg(filtered_df, "Housing Type", use_calendar_days)
plot_monthly_chart(housing_monthly, "Housing Type", "By Housing Type")