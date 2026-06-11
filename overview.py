import streamlit as st
import pandas as pd
import urllib.parse
from openai import OpenAI

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
# =========================================================
# LOAD GOOGLE SHEET
# =========================================================
SPREADSHEET_ID = "13q8avPIV2RjBg1tIUeJsd6U23wfOAann30S-d6moQ84"
SHEET_NAME = "All Content"

encoded_sheet = urllib.parse.quote(SHEET_NAME)
url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet={encoded_sheet}"

try:
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip()

    for col in ["Engagement", "Reach", "Impression", "Last Followers", "Growth", "Save"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", "")
                .str.extract(r"(-?\d+)", expand=False) 
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

except Exception as e:
    st.error(f"Gagal load spreadsheet: {e}")
    st.stop()


# =========================================================
# 8 MINGGU TERAKHIR
# =========================================================
week_order = (
    df[["Week_code", "Date_Week"]]
    .dropna(subset=["Week_code"])
    .drop_duplicates(subset=["Week_code"])
    .copy()
)

week_order["Week_dt"] = pd.to_datetime(week_order["Week_code"], dayfirst=True, errors="coerce")
week_order = week_order.dropna(subset=["Week_dt"]).sort_values("Week_dt")

# =========================================================
# SIDEBAR FILTER (DATE PICKER VERSION)
# =========================================================
st.sidebar.header("📅 Week Filter")

use_filter = st.sidebar.toggle("Use Custom Date Range", value=False)

# pastikan Week_dt sudah datetime
week_order = week_order.sort_values("Week_dt")

# default = last 8 weeks
default_weeks = week_order.tail(8)
default_start = default_weeks["Week_dt"].min()
default_end   = default_weeks["Week_dt"].max()

# ===============================
# DEFAULT MODE
# ===============================
if not use_filter:
    selected_weeks = default_weeks

# ===============================
# DATE PICKER MODE
# ===============================
else:
    st.markdown("## 📅 Date Range")

    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input("Start Date", value=default_start)

    with col2:
        end_date = st.date_input("End Date", value=default_end)

    selected_weeks = week_order[
        (week_order["Week_dt"] >= pd.to_datetime(start_date)) &
        (week_order["Week_dt"] <= pd.to_datetime(end_date))
    ]


# ===============================
# APPLY FILTER
# ===============================
last_8_codes = selected_weeks["Week_code"].tolist()
week_label_map = dict(zip(selected_weeks["Week_code"], selected_weeks["Date_Week"]))

df_8w = df[df["Week_code"].isin(last_8_codes)].copy()

# =========================================================
# HELPER
# =========================================================
def filter_platform(dataframe, name):
    return dataframe[dataframe["Platform"].str.strip().str.lower() == name.lower()]


# =========================================================
# BUILD FUNCTIONS PER PLATFORM
# =========================================================

def build_instagram_table(df_8w, df_full, week_codes, week_label_map):
    posts_8w      = df_8w[df_8w["image"].notna()]
    followers_8w  = df_8w[df_8w["image"].isna()]
    followers_all = df_full[df_full["image"].isna()]
    posts_full    = df_full[df_full["image"].notna()]

    rows = []
    for wk in week_codes:
        p = posts_8w[posts_8w["Week_code"] == wk]
        f = followers_8w[followers_8w["Week_code"] == wk]
        rows.append({
            "Week":                week_label_map.get(wk, wk),
            "Followers":           f["Last Followers"].dropna().iloc[-1] if not f["Last Followers"].dropna().empty else None,
            "Followers Growth":    f["Growth"].dropna().sum() if not f["Growth"].dropna().empty else 0,
            "Total Post":          len(p),
            "Engagement":          f["account_interaction"].dropna().sum() if not f.empty else 0,
            "Reach":               f["account_reach"].dropna().sum() if not f.empty else 0,
            "Impressions / Views": f["account_impression"].dropna().sum() if not f.empty else 0,
        })

    rows.append({
        "Week":                "YTD",
        "Followers":           followers_all["Last Followers"].dropna().iloc[-1] if not followers_all["Last Followers"].dropna().empty else None,
        "Followers Growth":    followers_all["Growth"].dropna().sum(),
        "Total Post":          len(posts_full),
        "Engagement":          followers_all["account_interaction"].dropna().sum(),
        "Reach":               followers_all["account_reach"].dropna().sum(),
        "Impressions / Views": followers_all["account_impression"].dropna().sum(),
    })

    return pd.DataFrame(rows).set_index("Week")


def build_facebook_table(df_8w, df_full, week_codes, week_label_map):
    posts_8w      = df_8w[df_8w["image"].notna()]
    followers_8w  = df_8w[df_8w["image"].isna()]
    followers_all = df_full[df_full["image"].isna()]
    posts_full    = df_full[df_full["image"].notna()]

    rows = []
    for wk in week_codes:
        p = posts_8w[posts_8w["Week_code"] == wk]
        f = followers_8w[followers_8w["Week_code"] == wk]
        rows.append({
            "Week":                week_label_map.get(wk, wk),
            "Followers":           f["Last Followers"].dropna().iloc[-1] if not f["Last Followers"].dropna().empty else None,
            "Followers Growth":    f["Growth"].dropna().sum() if not f["Growth"].dropna().empty else 0,
            "Total Post":          len(p),
            "Engagement":          f["account_interaction"].dropna().sum() if not f.empty else 0,
            "Reach":               f["account_reach"].dropna().sum() if not f.empty else 0,
            "Impressions / Views": f["account_impression"].dropna().sum() if not f.empty else 0,
        })

    rows.append({
        "Week":                "YTD",
        "Followers":           followers_all["Last Followers"].dropna().iloc[-1] if not followers_all["Last Followers"].dropna().empty else None,
        "Followers Growth":    followers_all["Growth"].dropna().sum(),
        "Total Post":          len(posts_full),
        "Engagement":          followers_all["account_interaction"].dropna().sum(),
        "Reach":               followers_all["account_reach"].dropna().sum(),
        "Impressions / Views": followers_all["account_impression"].dropna().sum(),
    })

    return pd.DataFrame(rows).set_index("Week")


def build_tiktok_table(df_8w, df_full, week_codes, week_label_map):
    posts_8w      = df_8w[df_8w["image"].notna()]
    followers_8w  = df_8w[df_8w["image"].isna()]
    followers_all = df_full[df_full["image"].isna()]
    posts_full    = df_full[df_full["image"].notna()]

    rows = []
    for wk in week_codes:
        p = posts_8w[posts_8w["Week_code"] == wk]
        f = followers_8w[followers_8w["Week_code"] == wk]
        rows.append({
            "Week":             week_label_map.get(wk, wk),
            "Followers":        f["Last Followers"].dropna().iloc[-1] if not f["Last Followers"].dropna().empty else None,
            "Followers Growth": f["Growth"].dropna().sum() if not f["Growth"].dropna().empty else 0,
            "Total Post":       len(p),
            "Engagement":       f["account_interaction"].dropna().sum() if not f.empty else 0,
            "Views":            f["account_impression"].dropna().sum() if not f.empty else 0,
        })

    rows.append({
        "Week":             "YTD",
        "Followers":        followers_all["Last Followers"].dropna().iloc[-1] if not followers_all["Last Followers"].dropna().empty else None,
        "Followers Growth": followers_all["Growth"].dropna().sum(),
        "Total Post":       len(posts_full),
        "Engagement":       followers_all["account_interaction"].dropna().sum(),
        "Views":            followers_all["account_impression"].dropna().sum(),
    })

    return pd.DataFrame(rows).set_index("Week")

def build_linkedin_table(df_8w, df_full, week_codes, week_label_map):
    posts_8w      = df_8w[df_8w["image"].notna()]
    followers_8w  = df_8w[df_8w["image"].isna()]
    followers_all = df_full[df_full["image"].isna()]
    posts_full    = df_full[df_full["image"].notna()]

    rows = []
    for wk in week_codes:
        p = posts_8w[posts_8w["Week_code"] == wk]
        f = followers_8w[followers_8w["Week_code"] == wk]
        rows.append({
            "Week":             week_label_map.get(wk, wk),
            "Followers":        f["Last Followers"].dropna().iloc[-1] if not f["Last Followers"].dropna().empty else None,
            "Followers Growth": f["Growth"].dropna().sum() if not f["Growth"].dropna().empty else 0,
            "Total Post":       len(p),
            "Engagement":       f["account_interaction"].dropna().sum() if not f.empty else 0,
            "Impression":       f["account_impression"].dropna().sum() if not f.empty else 0,
            "Views":            f["account_reach"].dropna().sum() if not f.empty else 0,
            "Clicks":           f["page_views"].dropna().sum() if not f.empty else 0,
        })

    rows.append({
        "Week":             "YTD",
        "Followers":        followers_all["Last Followers"].dropna().iloc[-1] if not followers_all["Last Followers"].dropna().empty else None,
        "Followers Growth": followers_all["Growth"].dropna().sum(),
        "Total Post":       len(posts_full),
        "Engagement":       followers_all["account_interaction"].dropna().sum(),
        "Impression":       followers_all["account_impression"].dropna().sum(),
        "Views":            followers_all["account_reach"].dropna().sum(),
        "Clicks":           followers_all["page_views"].dropna().sum(),
    })

    return pd.DataFrame(rows).set_index("Week")


def build_youtube_table(df_8w, df_full, week_codes, week_label_map):
    posts_8w      = df_8w[df_8w["image"].notna()]
    followers_8w  = df_8w[df_8w["image"].isna()]
    followers_all = df_full[df_full["image"].isna()]
    posts_full    = df_full[df_full["image"].notna()]

    rows = []
    for wk in week_codes:
        p = posts_8w[posts_8w["Week_code"] == wk]
        f = followers_8w[followers_8w["Week_code"] == wk]
        rows.append({
            "Week":              week_label_map.get(wk, wk),
            "Subscribers":       f["Last Followers"].dropna().iloc[-1] if not f["Last Followers"].dropna().empty else None,
            "Subscriber Growth": f["Growth"].dropna().sum() if not f["Growth"].dropna().empty else 0,
            "Total Post":        len(p),
            "Engagement":        f["account_interaction"].dropna().sum() if not f.empty else 0,
            "Views":             f["account_impression"].dropna().sum() if not f.empty else 0,
        })

    rows.append({
        "Week":              "YTD",
        "Subscribers":       followers_all["Last Followers"].dropna().iloc[-1] if not followers_all["Last Followers"].dropna().empty else None,
        "Subscriber Growth": followers_all["Growth"].dropna().sum(),
        "Total Post":        len(posts_full),
        "Engagement":        followers_all["account_interaction"].dropna().sum(),
        "Views":             followers_all["account_impression"].dropna().sum(),
    })

    return pd.DataFrame(rows).set_index("Week")


def build_meta_table(df_meta_8w, df_meta_full, week_codes, week_label_map):
    posts_8w      = df_meta_8w[df_meta_8w["image"].notna()]
    followers_8w  = df_meta_8w[df_meta_8w["image"].isna()]
    posts_full    = df_meta_full[df_meta_full["image"].notna()]
    followers_all = df_meta_full[df_meta_full["image"].isna()]

    rows = []
    for wk in week_codes:
        p = posts_8w[posts_8w["Week_code"] == wk]
        f = followers_8w[followers_8w["Week_code"] == wk]
        rows.append({
            "Week":             week_label_map.get(wk, wk),
            "Total Post":       len(p),
            "Total Engagement": f["account_interaction"].dropna().sum() if not f.empty else 0,
            "Total Reach":      f["account_reach"].dropna().sum() if not f.empty else 0,
            "Total Views":      f["account_impression"].dropna().sum() if not f.empty else 0,
        })

    rows.append({
        "Week":             "YTD",
        "Total Post":       len(posts_full),
        "Total Engagement": followers_all["account_interaction"].dropna().sum(),
        "Total Reach":      followers_all["account_reach"].dropna().sum(),
        "Total Views":      followers_all["account_impression"].dropna().sum(),
    })

    return pd.DataFrame(rows).set_index("Week")

def build_twitter_table(df_8w, df_full, week_codes, week_label_map):
    posts_8w      = df_8w[df_8w["image"].notna()]
    followers_8w  = df_8w[df_8w["image"].isna()]
    followers_all = df_full[df_full["image"].isna()]
    posts_full    = df_full[df_full["image"].notna()]

    rows = []
    for wk in week_codes:
        p = posts_8w[posts_8w["Week_code"] == wk]
        f = followers_8w[followers_8w["Week_code"] == wk]
        rows.append({
            "Week":                week_label_map.get(wk, wk),
            "Followers":           f["Last Followers"].dropna().iloc[-1] if not f["Last Followers"].dropna().empty else None,
            "Followers Growth":    f["Growth"].dropna().sum() if not f["Growth"].dropna().empty else 0,
            "Total Post":          len(p),
            "Engagement":          f["account_interaction"].dropna().sum() if not f.empty else 0,
            "Reach":               f["account_reach"].dropna().sum() if not f.empty else 0,
            "Impressions / Views": f["account_impression"].dropna().sum() if not f.empty else 0,
        })

    rows.append({
        "Week":                "YTD",
        "Followers":           followers_all["Last Followers"].dropna().iloc[-1] if not followers_all["Last Followers"].dropna().empty else None,
        "Followers Growth":    followers_all["Growth"].dropna().sum(),
        "Total Post":          len(posts_full),
        "Engagement":          followers_all["account_interaction"].dropna().sum(),
        "Reach":               followers_all["account_reach"].dropna().sum(),
        "Impressions / Views": followers_all["account_impression"].dropna().sum(),
    })

    return pd.DataFrame(rows).set_index("Week")
# =========================================================
# FILTER PER PLATFORM
# =========================================================
df_ig_8w       = filter_platform(df_8w, "instagram")
df_fb_8w       = filter_platform(df_8w, "facebook")
df_meta_8w     = df_8w[df_8w["Platform"].str.strip().str.lower().isin(["instagram", "facebook"])]
df_tiktok_8w   = filter_platform(df_8w, "tiktok")
df_linkedin_8w = filter_platform(df_8w, "linkedin")
df_youtube_8w  = filter_platform(df_8w, "youtube")
df_twitter_8w  = filter_platform(df_8w, "X")

df_ig_full       = filter_platform(df, "instagram")
df_fb_full       = filter_platform(df, "facebook")
df_meta_full     = df[df["Platform"].str.strip().str.lower().isin(["instagram", "facebook"])]
df_tiktok_full   = filter_platform(df, "tiktok")
df_linkedin_full = filter_platform(df, "linkedin")
df_youtube_full  = filter_platform(df, "youtube")
df_twitter_full  = filter_platform(df, "X")

# =========================================================
# BUILD TABLES
# =========================================================
tbl_ig       = build_instagram_table(df_ig_8w,       df_ig_full,       last_8_codes, week_label_map)
tbl_fb       = build_facebook_table(df_fb_8w,        df_fb_full,       last_8_codes, week_label_map)
tbl_meta     = build_meta_table(df_meta_8w,          df_meta_full,     last_8_codes, week_label_map)
tbl_tiktok   = build_tiktok_table(df_tiktok_8w,      df_tiktok_full,   last_8_codes, week_label_map)
tbl_linkedin = build_linkedin_table(df_linkedin_8w,  df_linkedin_full, last_8_codes, week_label_map)
tbl_youtube  = build_youtube_table(df_youtube_8w,    df_youtube_full,  last_8_codes, week_label_map)
tbl_twitter  = build_twitter_table(df_twitter_8w,    df_twitter_full,  last_8_codes, week_label_map)

# =========================================================
# DISPLAY
# =========================================================
def fmt(df):
    return df.map(lambda x: f"{int(x):,}" if pd.notna(x) and x != 0 else (x if pd.isna(x) else "0"))

st.subheader("📸 INSTAGRAM")
st.dataframe(fmt(tbl_ig), use_container_width=True)

st.subheader("👥 FACEBOOK")
st.dataframe(fmt(tbl_fb), use_container_width=True)

st.subheader("🔵 META (Instagram + Facebook)")
st.dataframe(fmt(tbl_meta), use_container_width=True)

st.subheader("🎵 TIKTOK")
st.dataframe(fmt(tbl_tiktok), use_container_width=True)

st.subheader("💼 LINKEDIN")
st.dataframe(fmt(tbl_linkedin), use_container_width=True)

st.subheader("▶️ YOUTUBE")
st.dataframe(fmt(tbl_youtube), use_container_width=True)

st.subheader("👥 X")
st.dataframe(fmt(tbl_twitter), use_container_width=True)
## ===============================
# AI SUMMARY
# ===============================
st.markdown("---")
st.header("🧠 AI Generated Summary")

last_week_label = list(tbl_ig.index)[-2]

# ===============================
# NORMALIZE YOUTUBE (IMPORTANT)
# ===============================
tbl_youtube_ai = tbl_youtube.copy()

tbl_youtube_ai = tbl_youtube_ai.rename(columns={
    "Subscribers": "Followers",
    "Subscriber Growth": "Followers Growth"
})

# ===============================
# PREPARE FULL TABLE DATA
# ===============================
data_ai = {
    "Instagram": tbl_ig.reset_index().to_dict(orient="records"),
    "Facebook": tbl_fb.reset_index().to_dict(orient="records"),
    "TikTok": tbl_tiktok.reset_index().to_dict(orient="records"),
    "LinkedIn": tbl_linkedin.reset_index().to_dict(orient="records"),
    "YouTube": tbl_youtube_ai.reset_index().to_dict(orient="records"),
    "Twitter": tbl_twitter.reset_index().to_dict(orient="records"),

}

# ===============================
# GENERATE AI SUMMARY
# ===============================
def generate_ai_summary(data_list, week_label):

    prompt = f"""
You are a senior social media analyst.

You are given full weekly performance tables for each platform.

Analyze ALL available metrics (followers, engagement, reach, Impression, impressions, clicks, total posts).

Week: {week_label}

FORMAT:
Remarks {week_label}

Instagram
<1 sentence insight>

Facebook
<1 sentence insight>

TikTok
<1 sentence insight>

LinkedIn
<1 sentence insight>

YouTube
<1 sentence insight>

Twitter
<1 sentence insight>

RULES:
- ALWAYS write per platform (no paragraph)
- 1–2 sentences max per platform
- Compare latest week vs previous week
- MUST include percentage numbers when relevant
- Use ALL relevant metrics (including Total Post, Clicks, Impression, Views)
- Highlight main driver (e.g. higher posting activity, spike in views, drop in reach)
- Avoid generic statements
- Use connectors: "despite", "although", "while", "driven by"
- Be analytical like an agency report
- Do NOT mention missing data
- If metric is 0, ignore it and focus on meaningful metrics

DATA:
{data_list}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6
    )

    return response.choices[0].message.content


# ===============================
# BUTTON TRIGGER
# ===============================
if st.button("✨ Generate AI Summary"):

    with st.spinner("Generating summary..."):

        summary = generate_ai_summary(data_ai, last_week_label)

        st.session_state["ai_summary"] = summary


# ===============================
# DISPLAY RESULT
# ===============================
if "ai_summary" in st.session_state:
    st.markdown(st.session_state["ai_summary"])
