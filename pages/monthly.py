import streamlit as st
import pandas as pd
import urllib.parse
from datetime import datetime
import requests
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import io
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

    for col in ["common_post_impressions", "common_post_reach", "common_likes_count",
                "common_comments_count", "common_shares_count", "profile_post_saved_total",
                "common_interactions_count", "Growth", "Impression", "Engagement","Last Followers"]:
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
# DATE FILTER
# =========================================================

today = datetime.today()

# content date
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
# followers weekly date
df["Week_dt"] = pd.to_datetime(
    df["Week_code"].astype(str),
    dayfirst=True,
    errors="coerce"
)

col1, col2 = st.columns(2)

with col1:
    start_date = st.date_input(
        "Start Date",
        value=today.replace(day=1)
    )

with col2:
    end_date = st.date_input(
        "End Date",
        value=today
    )

# =========================================================
# FILTER
# =========================================================

df_filtered = df[
    (df["Date"].dt.normalize() >= pd.to_datetime(start_date)) &
    (df["Date"].dt.normalize() <= pd.to_datetime(end_date))
]


# =========================================================
def build_monthly_table(df_full, platform_name):
    platform_lower = platform_name.lower()
    df_p = df_full[df_full["Platform"].str.strip().str.lower() == platform_lower]

    df_posts     = df_p[df_p["id"].notna() & (df_p["id"].astype(str).str.strip() != "")]
    df_followers = df_p[df_p["id"].isna() | (df_p["id"].astype(str).str.strip() == "")]

    # Filter 2026 only
    df_posts     = df_posts[df_posts["Month"].astype(str).str.contains("2026", na=False)]
    df_followers = df_followers[df_followers["Month"].astype(str).str.contains("2026", na=False)]

    is_tiktok  = platform_lower == "tiktok"
    is_youtube = platform_lower == "youtube"

    # Posts groupby — hanya hitung jumlah post
    posts_grouped = df_posts.groupby("Month", sort=False).agg(
        Post_Amount = ("id", "count"),
    ).reset_index()

    # Watch Rate for TikTok/YouTube (tetap dari post level karena ini avg per post)
    if is_tiktok and "Watch Rate" in df_posts.columns:
        wr = df_posts.groupby("Month", sort=False).agg(Watch_Rate=("Watch Rate", "mean")).reset_index()
        posts_grouped = pd.merge(posts_grouped, wr, on="Month", how="left")
    elif is_youtube and "Avg View Percentage" in df_posts.columns:
        wr = df_posts.groupby("Month", sort=False).agg(Watch_Rate=("Avg View Percentage", "mean")).reset_index()
        posts_grouped = pd.merge(posts_grouped, wr, on="Month", how="left")

    # Followers groupby — account level metrics
    agg_followers = {
        "Followers":   ("Last Followers", "last"),
        "Growth":      ("Growth", "sum"),
        "Engagement":  ("account_interaction", "sum"),
        "Impression":  ("account_impression", "sum"),
    }
    if platform_lower not in ["tiktok", "youtube", "x"]:
        agg_followers["Reach"] = ("account_reach", "sum")

    followers_grouped = df_followers.groupby("Month", sort=False).agg(**agg_followers).reset_index()

    merged = pd.merge(posts_grouped, followers_grouped, on="Month", how="outer")
    merged["Month_dt"] = pd.to_datetime(merged["Month"], format="%b-%Y", errors="coerce")
    merged = merged.sort_values("Month_dt").drop(columns=["Month_dt"])

    for col in ["Post_Amount", "Impression", "Engagement"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)
    if "Reach" in merged.columns:
        merged["Reach"] = merged["Reach"].fillna(0)

    # ER
    if is_tiktok or is_youtube:
        merged["ER"] = (merged["Engagement"] / merged["Impression"].replace(0, pd.NA) * 100).round(2)
        merged["ER"] = merged["ER"].fillna(0).apply(lambda x: f"{x:.2f}%")
    else:
        if "Reach" in merged.columns and merged["Reach"].replace(0, pd.NA).notna().any():
            merged["ER"] = (merged["Engagement"] / merged["Reach"].replace(0, pd.NA) * 100).round(2)
        else:
            merged["ER"] = (merged["Engagement"] / merged["Impression"].replace(0, pd.NA) * 100).round(2)
        merged["ER"] = merged["ER"].fillna(0).apply(lambda x: f"{x:.2f}%")

    # Format numbers
    for col in ["Post_Amount", "Followers", "Growth", "Reach", "Impression", "Engagement"]:
        if col in merged.columns:
            merged[col] = merged[col].apply(lambda x: f"{int(float(str(x).replace(',', ''))):,}" if pd.notna(x) else "0")
    # Rename
    merged = merged.rename(columns={
        "Post_Amount": "Total Post",
        "Followers":   "Followers",
        "Growth":      "Followers Growth",
        "Reach":       "Total Reach",
        "Impression":  "Views" if (is_tiktok or is_youtube) else "Total Impression",
        "Engagement":  "Total Engagement",
    })

    # Column order
    if is_tiktok or is_youtube:
        col_order = ["Followers", "Followers Growth", "Total Post", "Total Engagement", "Views", "ER"]
    else:
        col_order = ["Followers", "Followers Growth", "Total Post", "Total Engagement", "Total Reach", "Total Impression", "ER"]

    col_order = [c for c in col_order if c in merged.columns]
    merged = merged[["Month"] + col_order]

    return merged.set_index("Month")


def build_content_breakdown(df_full, platform_name):

    df_p = df_full[
        df_full["Platform"]
        .str.strip()
        .str.lower()
        == platform_name.lower()
    ]

    df_posts = df_p[
        df_p["id"].notna() &
        (df_p["id"].astype(str).str.strip() != "")
    ]

    df_posts = df_posts.copy()

    is_tiktok  = platform_name.lower() == "tiktok"
    is_youtube = platform_name.lower() == "youtube"

    # =====================================================
    # ER
    # =====================================================
    df_posts["ER_raw"] = (
        df_posts["Engagement"] /
        df_posts["Impression"] * 100
    ).round(2)

    df_posts["ER"] = df_posts["ER_raw"].apply(
        lambda x: f"{x:.2f}%"
        if pd.notna(x)
        else "0.00%"
    )

    # =====================================================
    # BASE COLUMNS
    # =====================================================
    cols = [
        "Date",
        "link",
        "type",
        "Boosted",
        "message",
        "Impression",
        "Reach",
        "Likes",
        "Comments",
        "Share",
        "Save",
        "Engagement",
        "ER",
        "ER_raw"
    ]

    # =====================================================
    # EXCLUDE PER PLATFORM
    # =====================================================
    exclude_map = {
        "tiktok":   ["Reach", "Save"],
        "facebook": ["Save"],
        "youtube":  ["Reach", "Share", "Save"],
        "linkedin": ["Save"],
        "x":        ["Reach", "Save"],
    }

    exclude_cols = exclude_map.get(platform_name.lower(), [])
    cols = [c for c in cols if c not in exclude_cols]
    cols = [c for c in cols if c in df_posts.columns]

    # =====================================================
    # FINAL DF
    # =====================================================
    df_posts = df_posts[cols]
    df_posts = (
        df_posts
        .sort_values("ER_raw", ascending=False)
        .drop(columns=["ER_raw"])
    )

    # =====================================================
    # RENAME
    # =====================================================
    df_posts = df_posts.rename(columns={
        "link":       "Link",
        "type":       "Type",
        "message":    "Message",
        "Engagement": "Total Engagement",
        "Impression": "Views" if is_tiktok or is_youtube else "Impression",
    })

    df = df_posts.reset_index(drop=True)

    # =====================================================
    # COLUMN CONFIG
    # =====================================================
    impression_label = "Views" if is_tiktok or is_youtube else "Impression"

    column_config = {
        "Link":             st.column_config.LinkColumn("Link", display_text="Link", width="small"),
        "Message":          st.column_config.TextColumn("Message", width="medium"),
        "Date":             st.column_config.DateColumn("Date", width="small"),
        "Type":             st.column_config.TextColumn("Type", width="small"),
        "Boosted":          st.column_config.TextColumn("Boosted", width="small"),
        impression_label:   st.column_config.NumberColumn(impression_label, width="small", format="%d"),
        "Reach":            st.column_config.NumberColumn("Reach", width="small", format="%d"),
        "Likes":            st.column_config.NumberColumn("Likes", width="small", format="%d"),
        "Comments":         st.column_config.NumberColumn("Comments", width="small", format="%d"),
        "Share":            st.column_config.NumberColumn("Share", width="small", format="%d"),
        "Save":             st.column_config.NumberColumn("Save", width="small", format="%d"),
        "Total Engagement": st.column_config.NumberColumn("Total Engagement", width="small", format="%d"),
        "ER":               st.column_config.TextColumn("ER", width="small"),
    }

    # =====================================================
    # REMOVE UNUSED CONFIG
    # =====================================================
    column_config = {
        k: v for k, v in column_config.items()
        if k in df.columns
    }

    # =====================================================
    # DISPLAY
    # =====================================================
    st.dataframe(
        df,
        use_container_width=True,
        column_config=column_config,
        hide_index=True
    )
def render_post_embed(post_url):
    try:
        shortcode = [x for x in post_url.split("/") if x][-1]
        st.components.v1.html(
            f'<iframe src="https://www.instagram.com/p/{shortcode}/embed/" '
            f'width="100%" height="460" frameborder="0" scrolling="no" style="border:none;"></iframe>',
            height=480, scrolling=False)
    except:
        st.markdown(f'<a href="{post_url}" target="_blank">📸 Lihat Post</a>', unsafe_allow_html=True)


            
def render_post_metrics(post_type, reach, impression, engagement, er):
    st.markdown(f"""
        <div style="background:#f8f9fa;border-radius:8px;padding:10px 12px;font-size:12px;line-height:2;">
        📌 <b>Post Type</b> &nbsp;&nbsp;&nbsp; {post_type}<br>
        👥 <b>Reach</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {reach:,}<br>
        👀 <b>Impression</b> &nbsp; {impression:,}<br>
        💬 <b>Engagement</b> &nbsp; {engagement:,}<br>
        ⚡ <b>ER</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {er:.2f}%
        </div>
    """, unsafe_allow_html=True)
    
def ai_summary_platform(platform_name, df_filtered, df_full, key_suffix):
    """AI Summary: performance comparison vs previous month per platform."""
    if st.button("🤖 Generate AI Summary", key=f"ai_summary_{key_suffix}"):
        with st.spinner("Generating AI Summary..."):

            current_start = pd.to_datetime(start_date)
            current_end   = pd.to_datetime(end_date)
            prev_end      = current_start - pd.Timedelta(days=1)
            prev_start    = prev_end.replace(day=1)

            def get_platform(source_df):
                return source_df[source_df["Platform"].str.strip().str.lower() == platform_name.lower()]

            def split(source_df):
                posts = source_df[~source_df["image"].fillna("").astype(str).str.strip().str.lower().isin(["", "nan", "none", "null"])]
                flw   = source_df[source_df["image"].fillna("").astype(str).str.strip().str.lower().isin(["", "nan", "none", "null"])]
                return posts, flw

            # Current
            df_curr              = get_platform(df_filtered)
            df_curr_posts, df_curr_flw = split(df_curr)

            # Previous
            df_prev_all          = get_platform(df_full)
            df_prev_all          = df_prev_all[
                (df_prev_all["Date"].dt.normalize() >= prev_start.normalize()) &
                (df_prev_all["Date"].dt.normalize() <= prev_end.normalize())
            ]
            df_prev_posts, df_prev_flw = split(df_prev_all)

            def safe_sum(df, col):
                if df.empty or col not in df.columns: return 0
                return int(df[col].sum()) if pd.notna(df[col].sum()) else 0

            def get_top(df, col):
                if df.empty or col not in df.columns: return {}
                row = df.nlargest(1, col).iloc[0]
                return {
                    "message": str(row.get("message", "-"))[:200],
                    "type":    str(row.get("type", "-")),
                    "boosted": str(row.get("Boosted", "-")),
                    col:       int(float(str(row[col]).replace(",", ""))) if pd.notna(row[col]) else 0
                }

            def delta(curr_val, prev_val):
                if prev_val == 0: return "N/A"
                pct  = (curr_val - prev_val) / prev_val * 100
                sign = "+" if pct >= 0 else ""
                return f"{sign}{pct:.1f}%"

            curr = {
                "reach":      safe_sum(df_curr_posts, "Reach"),
                "impression": safe_sum(df_curr_posts, "Impression"),
                "engagement": safe_sum(df_curr_posts, "Engagement"),
                "growth":     safe_sum(df_curr_flw,   "Growth"),
                "post_count": int(df_curr_posts["id"].count()) if not df_curr_posts.empty else 0,
            }
            prev = {
                "reach":      safe_sum(df_prev_posts, "Reach"),
                "impression": safe_sum(df_prev_posts, "Impression"),
                "engagement": safe_sum(df_prev_posts, "Engagement"),
                "growth":     safe_sum(df_prev_flw,   "Growth"),
                "post_count": int(df_prev_posts["id"].count()) if not df_prev_posts.empty else 0,
            }

            summary_data = {
                "platform": platform_name,
                "period": {
                    "current":  f"{current_start.strftime('%b %d')} – {current_end.strftime('%b %d, %Y')}",
                    "previous": f"{prev_start.strftime('%b %d')} – {prev_end.strftime('%b %d, %Y')}",
                },
                "current":  curr,
                "previous": prev,
                "change": {
                    "reach":      delta(curr["reach"],      prev["reach"]),
                    "impression": delta(curr["impression"], prev["impression"]),
                    "engagement": delta(curr["engagement"], prev["engagement"]),
                    "growth":     delta(curr["growth"],     prev["growth"]),
                    "post_count": delta(curr["post_count"], prev["post_count"]),
                },
                "top_content": {
                    "highest_reach":      get_top(df_curr_posts, "Reach"),
                    "highest_impression": get_top(df_curr_posts, "Impression"),
                    "highest_engagement": get_top(df_curr_posts, "Engagement"),
                    "highest_flw_growth": get_top(df_curr_flw,   "Growth"),
                }
            }
            
            prompt = f"""
You are a social media analyst. Below is the {platform_name} performance data for the current period vs previous month:

{json.dumps(summary_data, indent=2, default=str)}

Please write a concise summary in English covering:
1. 📊 Overall performance vs previous month — reach, impression, engagement, followers growth (up/down and by how much)
2. 📸 Highest Reach — which content drove it (type, organic/boosted, topic from message)
3. 👀 Highest Impression — which content drove it (type, organic/boosted, topic from message)
4. 💬 Highest Engagement — which content drove it (type, organic/boosted, topic from message)
5. 👥 Highest Followers Growth — which content or activity drove it
6. 💡 Brief insights and recommendations

Format: use bullet points per category, use relevant emojis, keep it concise and to the point.
"""

            try:
                openai_api_key = st.secrets["OPENAI_API_KEY"]
                response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type":  "application/json",
                        "Authorization": f"Bearer {openai_api_key}"
                    },
                    json={
                        "model":      "gpt-4.1-mini",
                        "max_tokens": 1000,
                        "messages":   [{"role": "user", "content": prompt}]
                    }
                )
                result  = response.json()
                ai_text = result["choices"][0]["message"]["content"]

                st.markdown("### 🤖 AI Summary")
                st.markdown(f"""
                    <div style="background:#f0f4ff;border-left:4px solid #4A90D9;
                                border-radius:8px;padding:16px;font-size:13px;line-height:1.8;">
                        {ai_text.replace(chr(10), '<br>')}
                    </div>
                """, unsafe_allow_html=True)

            except KeyError:
                st.error("API key not found. Make sure OPENAI_API_KEY is set in .streamlit/secrets.toml")
            except Exception as e:
                st.error(f"Failed to generate summary: {e}")


def ai_summary_top_views(df_top, content_type, platform_name, key_suffix):
    """AI Summary for Top 3 content based on Views."""
    if st.button("🤖 Generate AI Summary", key=f"ai_summary_views_{key_suffix}"):
        with st.spinner("Generating AI Summary..."):

            top_data = df_top[["message", "type", "Boosted", "Engagement", "Impression", "Reach"]].copy()
            top_data["message"] = top_data["message"].astype(str).str[:200]
            top_data["ER"]      = (top_data["Engagement"] / top_data["Impression"] * 100).round(2)

            prompt = f"""
You are a social media analyst. Below is the Top 3 {platform_name} {content_type} content with the highest Views:

{json.dumps(top_data.to_dict(orient="records"), indent=2, default=str)}

Please write a concise summary in English covering:
1. What is the highest-views content about (based on message/caption)
2. Are there consistent patterns across the top 3 (theme, style, topic)
3. Brief insight: why did this content attract many views
4. Recommendations for the next {content_type} content based on these patterns

Format: use bullet points, use relevant emojis, keep it concise and to the point.
"""

            try:
                openai_api_key = st.secrets["OPENAI_API_KEY"]
                response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type":  "application/json",
                        "Authorization": f"Bearer {openai_api_key}"
                    },
                    json={
                        "model":      "gpt-4.1-mini",
                        "max_tokens": 1000,
                        "messages":   [{"role": "user", "content": prompt}]
                    }
                )
                result  = response.json()
                ai_text = result["choices"][0]["message"]["content"]

                st.markdown("### 🤖 AI Summary")
                st.markdown(f"""
                    <div style="background:#f0f4ff;border-left:4px solid #4A90D9;
                                border-radius:8px;padding:16px;font-size:13px;line-height:1.8;">
                        {ai_text.replace(chr(10), '<br>')}
                    </div>
                """, unsafe_allow_html=True)

            except KeyError:
                st.error("API key not found. Make sure OPENAI_API_KEY is set in .streamlit/secrets.toml")
            except Exception as e:
                st.error(f"Failed to generate summary: {e}")


def ai_summary_top_engagement(df_top, content_type, platform_name, key_suffix):
    """AI Summary for Top 3 content based on Engagement."""
    if st.button("🤖 Generate AI Summary", key=f"ai_summary_engagement_{key_suffix}"):
        with st.spinner("Generating AI Summary..."):

            top_data = df_top[["message", "type", "Boosted", "Engagement", "Impression", "Reach"]].copy()
            top_data["message"] = top_data["message"].astype(str).str[:200]
            top_data["ER"]      = (top_data["Engagement"] / top_data["Impression"] * 100).round(2)

            prompt = f"""
You are a social media analyst. Below is the Top 3 {platform_name} {content_type} content with the highest Engagement:

{json.dumps(top_data.to_dict(orient="records"), indent=2, default=str)}

Please write a concise summary in English covering:
1. What is the highest-engagement content about (based on message/caption)
2. Are there consistent patterns across the top 3 (theme, style, topic)
3. Brief insight: why did this content engage the audience well
4. Recommendations for the next {content_type} content based on these patterns

Format: use bullet points, use relevant emojis, keep it concise and to the point.
"""

            try:
                openai_api_key = st.secrets["OPENAI_API_KEY"]
                response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type":  "application/json",
                        "Authorization": f"Bearer {openai_api_key}"
                    },
                    json={
                        "model":      "gpt-4.1-mini",
                        "max_tokens": 1000,
                        "messages":   [{"role": "user", "content": prompt}]
                    }
                )
                result  = response.json()
                ai_text = result["choices"][0]["message"]["content"]

                st.markdown("### 🤖 AI Summary")
                st.markdown(f"""
                    <div style="background:#f0f4ff;border-left:4px solid #4A90D9;
                                border-radius:8px;padding:16px;font-size:13px;line-height:1.8;">
                        {ai_text.replace(chr(10), '<br>')}
                    </div>
                """, unsafe_allow_html=True)

            except KeyError:
                st.error("API key not found. Make sure OPENAI_API_KEY is set in .streamlit/secrets.toml")
            except Exception as e:
                st.error(f"Failed to generate summary: {e}")

def render_followers_chart(df_filtered, platform_name):

    platform_name = str(platform_name)

    st.subheader(f"📈 {platform_name.title()} Followers Growth")

    # Filter platform
    df_platform = df_filtered[
        df_filtered["Platform"]
        .astype(str)
        .str.strip()
        .str.lower()
        == platform_name.lower()
    ].copy()

    # Account level = image kosong
    df_followers = df_platform[
        df_platform["image"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["", "nan", "none", "null"])
    ].copy()

    if df_followers.empty:
        st.warning(f"Tidak ada data followers untuk {platform_name}")
        return

    # Convert growth ke numeric
    df_followers["Growth"] = pd.to_numeric(
        df_followers["Growth"]
        .astype(str)
        .str.replace(",", "", regex=False),
        errors="coerce"
    )

    # Convert week ke datetime (sama seperti render_reach_chart)
    df_followers["Week_dt"] = pd.to_datetime(
        df_followers["Week_code"],
        dayfirst=True,
        errors="coerce"
    )

    # Group per week
    df_weekly = (
        df_followers.groupby("Week_dt", sort=True)
        .agg(Growth=("Growth", "sum"))
        .reset_index()
    )

    if df_weekly.empty:
        st.warning(f"Tidak ada data weekly growth untuk {platform_name}")
        return

    # Ambil semua week dari dataset
    all_weeks = pd.to_datetime(
        df_filtered["Week_code"].dropna().unique(),
        dayfirst=True,
        errors="coerce"
    )

    all_weeks = sorted([w for w in all_weeks if pd.notna(w)])

    df_all_weeks = pd.DataFrame({"Week_dt": all_weeks})

    # Fill missing week dengan 0
    df_weekly = pd.merge(
        df_all_weeks,
        df_weekly,
        on="Week_dt",
        how="left"
    )

    df_weekly["Growth"] = df_weekly["Growth"].fillna(0).astype(int)

    week_labels = [f"Week {i+1}" for i in range(len(df_weekly))]
    growth = df_weekly["Growth"].tolist()

    if not growth:
        st.warning(f"Tidak ada nilai growth untuk {platform_name}")
        return

    # Plot
    fig, ax = plt.subplots(figsize=(9, 4))

    bars = ax.bar(
        week_labels,
        growth,
        color="#5A8CB0",
        width=0.5
    )

    max_growth = max(abs(x) for x in growth) if growth else 1

    ax.axhline(0, color="gray", linewidth=0.8)

    # Label di atas bar
    for bar, val in zip(bars, growth):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max_growth * 0.02,
            f"{val:,}",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#333"
        )

    ax.set_xticks(range(len(week_labels)))
    ax.set_xticklabels(week_labels, fontsize=9)

    ax.set_ylabel("Followers Growth", fontsize=9)
    ax.set_title(
        f"{platform_name.title()} Followers Growth",
        fontsize=11,
        fontweight="bold",
        pad=10
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f"{int(v):,}")
    )

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(
        buf,
        format="png",
        dpi=150,
        bbox_inches="tight",
        facecolor="white"
    )
    plt.close()

    buf.seek(0)
    st.image(buf, use_container_width=True)


def render_engagement_chart(df_full, platform_name):

    platform_name = str(platform_name)

    st.subheader(f"📈 {platform_name.title()} Engagement Growth")

    df_platform = df_full[
        df_full["Platform"]
        .astype(str)
        .str.strip()
        .str.lower()
        == platform_name.lower()
    ].copy()

    # Followers row only (image kosong = account level)
    df_engagement = df_platform[
        df_platform["image"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["", "nan", "none", "null"])
    ].copy()

    if df_engagement.empty:
        st.warning(f"Tidak ada data engagement untuk {platform_name}")
        return

    # Gunakan account_interaction sebagai engagement
    df_engagement["account_interaction"] = (
        df_engagement["account_interaction"]
        .astype(str)
        .str.replace(",", "", regex=False)
    )

    df_engagement["account_interaction"] = pd.to_numeric(
        df_engagement["account_interaction"],
        errors="coerce"
    )

    df_engagement["Week_dt"] = pd.to_datetime(
        df_engagement["Week_code"]
        .astype(str)
        .str.strip(),
        dayfirst=True,
        errors="coerce"
    )

    df_engagement = df_engagement.dropna(subset=["Week_dt"])

    if df_engagement.empty:
        st.warning(f"Tidak ada Week_code valid untuk {platform_name}")
        return

    df_engagement = df_engagement.sort_values("Week_dt")

    df_weekly = (
        df_engagement.groupby("Week_dt", sort=True)
        .agg(
            Engagement=("account_interaction", "sum")
        )
        .reset_index()
        .sort_values("Week_dt")
    )

    if df_weekly.empty:
        st.warning(f"Tidak ada data weekly engagement untuk {platform_name}")
        return

    week_labels = [f"Week {i+1}" for i in range(len(df_weekly))]

    engagement = (
        df_weekly["Engagement"]
        .fillna(0)
        .astype(int)
        .tolist()
    )

    if len(engagement) == 0:
        st.warning(f"Tidak ada nilai engagement untuk {platform_name}")
        return

    fig, ax = plt.subplots(figsize=(9, 3.5))

    bars = ax.bar(
        week_labels,
        engagement,
        color="#5A8CB0",
        width=0.5
    )

    ax.axhline(0, color="gray", linewidth=0.8)

    max_eng = max([abs(x) for x in engagement]) if engagement else 1

    for bar, val in zip(bars, engagement):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + (max_eng * 0.02),
            f"{val:,}",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#333"
        )

    ax.set_title(
        f"{platform_name.title()} Engagement Growth",
        fontsize=11,
        fontweight="bold",
        pad=10
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f"{int(v):,}")
    )

    plt.tight_layout()

    buf = io.BytesIO()

    plt.savefig(
        buf,
        format="png",
        dpi=150,
        bbox_inches="tight",
        facecolor="white"
    )

    plt.close()

    buf.seek(0)

    st.image(buf, use_container_width=True)

def render_reach_chart(df_filtered, platform_name, metric="account_reach", label=None):

    label_map    = {
        "account_reach":       "Reach",
        "account_impression":  "Impression",
        "account_interaction": "Engagement",
    }
    metric_label = label if label else label_map.get(metric, metric)

    st.subheader(f"📈 {platform_name} {metric_label}")

    df_platform = df_filtered[
        df_filtered["Platform"].astype(str).str.strip().str.lower() == platform_name.lower()
    ].copy()

    # Account level = image kosong
    df_account = df_platform[
        df_platform["image"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["", "nan", "none", "null"])
    ].copy()

    if df_account.empty:
        st.warning(f"Tidak ada data {metric_label} untuk {platform_name}")
        return

    df_account["Week_dt"] = pd.to_datetime(
        df_account["Week_code"], dayfirst=True, errors="coerce"
    )

    df_account[metric] = pd.to_numeric(
        df_account[metric].astype(str).str.replace(",", "", regex=False),
        errors="coerce"
    )

    df_weekly = (
        df_account.groupby("Week_dt", sort=True)
        .agg(Value=(metric, "sum"))
        .reset_index()
    )

    if df_weekly.empty:
        st.warning(f"Tidak ada data weekly {metric_label} untuk {platform_name}")
        return

    # Fill missing weeks
    all_weeks = pd.to_datetime(
        df_filtered["Week_code"].dropna().unique(),
        dayfirst=True, errors="coerce"
    )
    all_weeks    = sorted([w for w in all_weeks if pd.notna(w)])
    df_all_weeks = pd.DataFrame({"Week_dt": all_weeks})

    df_weekly = pd.merge(df_all_weeks, df_weekly, on="Week_dt", how="left")
    df_weekly["Value"] = df_weekly["Value"].fillna(0).astype(int)

    week_labels = [f"Week {i+1}" for i in range(len(df_weekly))]
    vals        = df_weekly["Value"].tolist()

    # Chart
    fig, ax = plt.subplots(figsize=(9, 4))

    ax.plot(week_labels, vals, color="#4A90D9", linewidth=2.5, marker="o",
            markersize=6, markerfacecolor="#4A90D9")

    for i, val in enumerate(vals):
        ax.annotate(f"{val:,}", xy=(i, val),
                    xytext=(0, 10), textcoords="offset points",
                    ha="center", fontsize=8, color="#333")

    ax.fill_between(range(len(week_labels)), vals, alpha=0.1, color="#4A90D9")

    ax.set_xticks(range(len(week_labels)))
    ax.set_xticklabels(week_labels, fontsize=9)
    ax.set_ylabel(f"{platform_name} {metric_label}", fontsize=9)
    ax.set_title(metric_label, fontsize=11, fontweight="bold", pad=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    buf.seek(0)
    st.image(buf, use_container_width=True)
# =========================================================
# INSTAGRAM
# =========================================================
st.header("📸 Instagram")

st.subheader("📋 Monthly Breakdown")
st.dataframe(build_monthly_table(df, "instagram"), use_container_width=True)
render_followers_chart(df_filtered, "Instagram")
render_engagement_chart(df_filtered, "instagram")

render_reach_chart(df_filtered, "Instagram")

ai_summary_platform("Instagram", df_filtered, df, key_suffix="ig_monthly")

# --- Top 3 Posts by Engagement ---
st.subheader("🏆 Top 3 Posts by Engagement")

df_ig       = df_filtered[df_filtered["Platform"].str.strip().str.lower() == "instagram"]
df_ig_posts = df_ig[df_ig["id"].notna() & (df_ig["id"].astype(str).str.strip() != "")].copy()

df_ig_posts["ER_raw"] = (df_ig_posts["Engagement"] / df_ig_posts["Impression"] * 100).round(2)
df_top_er             = df_ig_posts.sort_values("Engagement", ascending=False).head(3)

if not df_top_er.empty:
    cols = st.columns(3)
    for idx, (_, row) in enumerate(df_top_er.iterrows()):
        post_url   = str(row["link"]).rstrip("/")
        post_type  = str(row.get("type", "-")).strip()
        reach      = int(float(str(row["Reach"]).replace(",", "")))      if pd.notna(row.get("Reach"))      else 0
        impression = int(float(str(row["Impression"]).replace(",", ""))) if pd.notna(row.get("Impression")) else 0
        engagement = int(float(str(row["Engagement"]).replace(",", ""))) if pd.notna(row.get("Engagement")) else 0
        with cols[idx]:
            render_post_embed(post_url)
            render_post_metrics(post_type, reach, impression, engagement, row["ER_raw"])
else:
    st.info("Tidak ada data Instagram di periode ini.")
ai_summary_top_engagement(df_top_er, content_type="Post", platform_name="Instagram", key_suffix="ig_engagement")


st.subheader("📋 Content Breakdown")
build_content_breakdown(df_filtered, "instagram")
st.markdown("---")


# =========================================================
# TIKTOK
# =========================================================
st.header("🎵 TikTok")

st.subheader("📋 Monthly Breakdown")
st.dataframe(build_monthly_table(df, "Tiktok"), use_container_width=True)

# TikTok

render_followers_chart(df_filtered, "Tiktok")
render_reach_chart(df_filtered, "Tiktok", metric="account_impression", label="Views")
ai_summary_platform("Tiktok", df_filtered, df, key_suffix="tt_monthly")

# =========================================================
# TOP 3 POSTS BY ENGAGEMENT
# =========================================================
st.subheader("🏆 Top 3 Posts by Engagement")

# =========================================================
# FILTER PLATFORM
# =========================================================
df_tt = df_filtered[
    df_filtered["Platform"]
    .astype(str)
    .str.strip()
    .str.lower()
    == "tiktok"
].copy()

# =========================================================
# POSTS ONLY
# =========================================================
df_tt_posts = df_tt[
    df_tt["id"].notna() &
    (df_tt["id"].astype(str).str.strip() != "")
].copy()

# =========================================================
# CLEAN METRICS
# =========================================================
df_tt_posts["Engagement"] = pd.to_numeric(
    df_tt_posts["Engagement"],
    errors="coerce"
)

df_tt_posts["Impression"] = pd.to_numeric(
    df_tt_posts["Impression"],
    errors="coerce"
)

df_tt_posts["Share"] = pd.to_numeric(
    df_tt_posts["Share"],
    errors="coerce"
)

# =========================================================
# TOP ENGAGEMENT (ALL POSTS)
# =========================================================
df_top_engagement = (
    df_tt_posts
    .sort_values("Engagement", ascending=False)
    .head(3)
)

# =========================================================
# DISPLAY
# =========================================================
if not df_top_engagement.empty:

    cols = st.columns(3)

    for idx, (_, row) in enumerate(df_top_engagement.iterrows()):

        post_url = str(row["link"]).rstrip("/")

        impression = (
            int(row["Impression"])
            if pd.notna(row.get("Impression"))
            else 0
        )

        engagement = (
            int(row["Engagement"])
            if pd.notna(row.get("Engagement"))
            else 0
        )

        share = (
            int(row["Share"])
            if pd.notna(row.get("Share"))
            else 0
        )

        with cols[idx]:

            # =================================================
            # TIKTOK EMBED
            # =================================================
            try:

                video_id = post_url.rstrip("/").split("/")[-1]

                st.components.v1.html(
                    f"""
                    <div style="
                        width:100%;
                        overflow:hidden;
                        border-radius:8px;
                        background:#000;
                    ">
                        <iframe
                            src="https://www.tiktok.com/embed/v2/{video_id}"
                            width="100%"
                            height="420"
                            frameborder="0"
                            scrolling="no"
                            allow="encrypted-media"
                            style="border:none;display:block;">
                        </iframe>
                    </div>
                    """,
                    height=425,
                    scrolling=False
                )

            except:

                st.markdown(
                    f'<a href="{post_url}" target="_blank">🎵 Lihat Post</a>',
                    unsafe_allow_html=True
                )

            # =================================================
            # METRICS
            # =================================================
            st.markdown(
                f"""
                <div style="
                    background:#f8f9fa;
                    border-radius:8px;
                    padding:10px 12px;
                    font-size:12px;
                    line-height:2;
                    margin-top:6px;
                ">

                👀 <b>Views</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {impression:,}<br>
                💬 <b>Engagement</b> &nbsp; {engagement:,}<br>
                🔁 <b>Share</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {share:,}

                </div>
                """,
                unsafe_allow_html=True
            )

else:

    st.info("Tidak ada data TikTok di periode ini.")
ai_summary_top_engagement(df_top_engagement, content_type="Post",                  platform_name="Tiktok",  key_suffix="tt_engagement")

st.subheader("📋 Content Breakdown")
build_content_breakdown(df_filtered, "tiktok")

st.markdown("---")


# =========================================================
# FACEBOOK
# =========================================================
st.header("👥 Facebook")

st.subheader("📋 Monthly Breakdown")
st.dataframe(build_monthly_table(df, "facebook"), use_container_width=True)
render_followers_chart(df_filtered, "Facebook")
render_reach_chart(df_filtered, "Facebook")
ai_summary_platform("Facebook", df_filtered, df, key_suffix="fb_monthly")

# --- Top 3 Posts by Total Engagement ---
st.subheader("🏆 Top 3 Posts by Total Engagement")

df_fb       = df_filtered[df_filtered["Platform"].str.strip().str.lower() == "facebook"]
df_fb_posts = df_fb[df_fb["id"].notna() & (df_fb["id"].astype(str).str.strip() != "")]

df_fb_posts = df_fb_posts.copy()
df_fb_posts["ER_raw"] = (df_fb_posts["Engagement"] / df_fb_posts["Impression"] * 100).round(2)
df_top_engagement     = df_fb_posts.sort_values("Engagement", ascending=False).head(3)

if not df_top_engagement.empty:
    cols = st.columns(3)
    for idx, (_, row) in enumerate(df_top_engagement.iterrows()):
        post_url   = str(row["link"]).rstrip("/")
        post_type  = str(row.get("type", "-")).strip()
        reach      = int(float(str(row["Reach"]).replace(",", "")))      if pd.notna(row.get("Reach"))      else 0
        impression = int(float(str(row["Impression"]).replace(",", ""))) if pd.notna(row.get("Impression")) else 0
        engagement = int(float(str(row["Engagement"]).replace(",", ""))) if pd.notna(row.get("Engagement")) else 0
        er         = row["ER_raw"]
        with cols[idx]:
            st.components.v1.html(
                f"""
                <iframe
                    src="https://www.facebook.com/plugins/post.php?href={urllib.parse.quote(post_url)}&show_text=true&width=500"
                    width="100%"
                    height="500"
                    style="border:none;overflow:hidden;"
                    scrolling="no"
                    frameborder="0"
                    allowfullscreen="true"
                    allow="autoplay; clipboard-write; encrypted-media; picture-in-picture; web-share">
                </iframe>
                """,
                height=520, scrolling=False)
            render_post_metrics(post_type, reach, impression, engagement, er)
else:
    st.info("Tidak ada data Facebook di periode ini.")
ai_summary_top_engagement(df_top_engagement, content_type="Post",                  platform_name="Facebook",  key_suffix="fb_engagement")
    
st.subheader("📋 Content Breakdown")
build_content_breakdown(df_filtered, "facebook")

st.markdown("---")

# =========================================================
# YOUTUBE
# =========================================================
st.header("▶️ YouTube")

st.subheader("📋 Monthly Breakdown")
st.dataframe(build_monthly_table(df, "youtube"), use_container_width=True)
render_followers_chart(df_filtered, "YouTube")
render_reach_chart(df_filtered, "Youtube", metric="account_impression", label="Views")
ai_summary_platform("YouTube", df_filtered, df, key_suffix="yt_monthly")

# =========================================================
# TOP 3 YOUTUBE POSTS BY ENGAGEMENT
# =========================================================
st.subheader("🏆 Top 3 YouTube Posts by Engagement")

# =========================================================
# EXTRACT YOUTUBE ID
# =========================================================
def extract_yt_id(url):

    url = str(url).strip()

    # youtu.be
    if "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]

    # shorts
    if "/shorts/" in url:
        return url.split("/shorts/")[-1].split("?")[0]

    # watch
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]

    return None

# =========================================================
# FILTER PLATFORM
# =========================================================
df_yt = df_filtered[
    df_filtered["Platform"]
    .astype(str)
    .str.strip()
    .str.lower()
    == "youtube"
].copy()

# =========================================================
# POSTS ONLY
# =========================================================
df_yt_posts = df_yt[
    df_yt["id"].notna() &
    (df_yt["id"].astype(str).str.strip() != "")
].copy()

# =========================================================
# CLEAN METRICS
# =========================================================
df_yt_posts["Engagement"] = pd.to_numeric(
    df_yt_posts["Engagement"],
    errors="coerce"
)

df_yt_posts["Impression"] = pd.to_numeric(
    df_yt_posts["Impression"],
    errors="coerce"
)

# =========================================================
# TOP ENGAGEMENT
# =========================================================
df_top_post = (
    df_yt_posts
    .sort_values("Engagement", ascending=False)
    .head(3)
)

# =========================================================
# DISPLAY
# =========================================================
if not df_top_post.empty:

    cols = st.columns(3)

    for idx, (_, row) in enumerate(df_top_post.iterrows()):

        post_url = str(row["link"]).rstrip("/")

        video_id = extract_yt_id(post_url)

        views = (
            int(row["Impression"])
            if pd.notna(row.get("Impression"))
            else 0
        )

        engagement = (
            int(row["Engagement"])
            if pd.notna(row.get("Engagement"))
            else 0
        )

        with cols[idx]:

            # =================================================
            # YOUTUBE EMBED
            # =================================================
            if video_id:

                st.components.v1.html(
                    f"""
                    <iframe
                        src="https://www.youtube.com/embed/{video_id}"
                        width="100%"
                        height="500"
                        style="border:none;border-radius:12px;"
                        frameborder="0"
                        allowfullscreen
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture">
                    </iframe>
                    """,
                    height=520,
                    scrolling=False
                )

            else:

                st.warning("URL tidak valid.")

            # =================================================
            # METRICS
            # =================================================
            st.markdown(
                f"""
                <div style="
                    background:#f8f9fa;
                    border-radius:8px;
                    padding:10px 12px;
                    font-size:12px;
                    line-height:2;
                    margin-top:6px;
                ">

                👀 <b>Views</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {views:,}<br>
                💬 <b>Engagement</b> &nbsp; {engagement:,}

                </div>
                """,
                unsafe_allow_html=True
            )

else:

    st.info("Tidak ada data YouTube di periode ini.")
ai_summary_top_engagement(df_top_engagement, content_type="Post",                  platform_name="Youtube",  key_suffix="yt_engagement")

    
st.subheader("📋 Content Breakdown")
build_content_breakdown(df_filtered, "youtube")

# =========================================================
# LINKEDIN
# =========================================================
st.header("📸 Linkedin")

st.subheader("📋 Monthly Breakdown")
st.dataframe(build_monthly_table(df, "Linkedin"), use_container_width=True)

render_followers_chart(df_filtered, "Linkedin")
render_reach_chart(df_filtered, "LinkedIn", metric="account_impression", label="Impression")
ai_summary_platform("LinkedIn", df_filtered, df, key_suffix="LinkedIn_monthly")

# =========================================================
# TOP 3 LINKEDIN POSTS BY ENGAGEMENT
# =========================================================
st.subheader("🏆 Top 3 LinkedIn Content by Total Engagement")

# =========================================================
# FILTER PLATFORM
# =========================================================
df_li = df_filtered[
    df_filtered["Platform"]
    .astype(str)
    .str.strip()
    .str.lower()
    == "linkedin"
].copy()

# =========================================================
# POSTS ONLY
# =========================================================
df_li_posts = df_li[
    df_li["id"].notna() &
    (df_li["id"].astype(str).str.strip() != "")
].copy()

# =========================================================
# CLEAN METRICS
# =========================================================
df_li_posts["Engagement"] = pd.to_numeric(
    df_li_posts["Engagement"],
    errors="coerce"
)

df_li_posts["Impression"] = pd.to_numeric(
    df_li_posts["Impression"],
    errors="coerce"
)

# =========================================================
# TOP ENGAGEMENT
# =========================================================
df_top_linkedin = (
    df_li_posts
    .sort_values("Engagement", ascending=False)
    .head(3)
)

# =========================================================
# DISPLAY
# =========================================================
if not df_top_linkedin.empty:

    cols = st.columns(3)

    for idx, (_, row) in enumerate(df_top_linkedin.iterrows()):

        post_url = str(row.get("link", "")).strip()

        impression = (
            int(row["Impression"])
            if pd.notna(row.get("Impression"))
            else 0
        )

        engagement = (
            int(row["Engagement"])
            if pd.notna(row.get("Engagement"))
            else 0
        )

        image_url = str(row.get("image", "")).strip()

        with cols[idx]:

            # =================================================
            # IMAGE
            # =================================================
            if image_url and image_url.lower() != "nan":

                st.image(
                    image_url,
                    use_container_width=True
                )

            # =================================================
            # OPEN POST BUTTON
            # =================================================
            if post_url:

                st.markdown(
                    f"""
                    <a href="{post_url}" target="_blank">
                        🔗 View Post
                    </a>
                    """,
                    unsafe_allow_html=True
                )

            # =================================================
            # METRICS
            # =================================================
            st.markdown(
                f"""
                <div style="
                    background:#f8f9fa;
                    border-radius:8px;
                    padding:10px 12px;
                    font-size:12px;
                    line-height:2;
                    margin-top:6px;
                ">

                👀 <b>Impression</b> &nbsp;&nbsp; {impression:,}<br>
                💬 <b>Engagement</b> &nbsp; {engagement:,}

                </div>
                """,
                unsafe_allow_html=True
            )

else:

    st.info("Tidak ada data LinkedIn di periode ini.")
ai_summary_top_engagement(df_top_engagement, content_type="Post",                  platform_name="Linkedin",  key_suffix="Linkedin_engagement")
    

st.subheader("📋 Content Breakdown")
build_content_breakdown(df_filtered, "Linkedin")
st.markdown("---")

# =========================================================
# X
# =========================================================
st.header("📸 X")

st.subheader("📋 Monthly Breakdown")
st.dataframe(build_monthly_table(df, "X"), use_container_width=True)

render_followers_chart(df_filtered, "X")
render_reach_chart(df_filtered, "X",metric="account_impression",label="Impression")
# =========================================================
# TOP 3 X POSTS BY ENGAGEMENT
# =========================================================
st.subheader("🏆 Top 3 X Content by Total Engagement")

# =========================================================
# FILTER PLATFORM
# =========================================================
df_x = df_filtered[
    df_filtered["Platform"]
    .astype(str)
    .str.strip()
    .str.lower()
    == "x"
].copy()

# =========================================================
# POSTS ONLY
# =========================================================
df_x_posts = df_x[
    df_x["id"].notna() &
    (df_x["id"].astype(str).str.strip() != "")
].copy()

# =========================================================
# CLEAN METRICS
# =========================================================
df_x_posts["Engagement"] = pd.to_numeric(
    df_x_posts["Engagement"],
    errors="coerce"
)

df_x_posts["Impression"] = pd.to_numeric(
    df_x_posts["Impression"],
    errors="coerce"
)

# =========================================================
# TOP ENGAGEMENT
# =========================================================
df_top_x = (
    df_x_posts
    .sort_values("Engagement", ascending=False)
    .head(3)
)

# =========================================================
# DISPLAY
# =========================================================
if not df_top_x.empty:

    cols = st.columns(3)

    for idx, (_, row) in enumerate(df_top_x.iterrows()):

        post_url = str(row.get("link", "")).strip()

        impression = (
            int(row["Impression"])
            if pd.notna(row.get("Impression"))
            else 0
        )

        engagement = (
            int(row["Engagement"])
            if pd.notna(row.get("Engagement"))
            else 0
        )

        image_url = str(row.get("image", "")).strip()

        with cols[idx]:

            # =================================================
            # IMAGE / FALLBACK TEXT
            # =================================================
            tweet_text = str(row.get("text", "")).strip()

            valid_image = (
                pd.notna(image_url)
                and str(image_url).strip() != ""
                and str(image_url).lower() not in [
                    "nan", "none", "null", "0", "[]", "{}"
                ]
            )

            if valid_image:

                try:

                    st.image(
                        image_url,
                        use_container_width=True
                    )

                except:

                    st.markdown(
                        f"""
                        <div style="
                            border:1px solid #e1e8ed;
                            border-radius:12px;
                            padding:14px;
                            background:white;
                            min-height:300px;
                            font-size:14px;
                            line-height:1.6;
                            color:#111;
                            overflow:hidden;
                        ">
                            {tweet_text[:500]}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

            else:

                st.markdown(
                    f"""
                    <div style="
                        border:1px solid #e1e8ed;
                        border-radius:12px;
                        padding:14px;
                        background:white;
                        min-height:300px;
                        font-size:14px;
                        line-height:1.6;
                        color:#111;
                        overflow:hidden;
                    ">
                        {tweet_text[:500]}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            # =================================================
            # OPEN POST BUTTON
            # =================================================
            if post_url:

                st.markdown(
                    f"""
                    <a href="{post_url}" target="_blank">
                        🔗 View Post
                    </a>
                    """,
                    unsafe_allow_html=True
                )

            # =================================================
            # METRICS
            # =================================================
            st.markdown(
                f"""
                <div style="
                    background:#f8f9fa;
                    border-radius:8px;
                    padding:10px 12px;
                    font-size:12px;
                    line-height:2;
                    margin-top:6px;
                ">

                👀 <b>Impression</b> &nbsp;&nbsp; {impression:,}<br>
                💬 <b>Engagement</b> &nbsp; {engagement:,}

                </div>
                """,
                unsafe_allow_html=True
            )

else:

    st.info("Tidak ada data X di periode ini.")

# =========================================================
# AI SUMMARY
# =========================================================
ai_summary_top_engagement(
    df_top_x,
    content_type="Post",
    platform_name="X",
    key_suffix="X_engagement"
)
st.subheader("📋 Content Breakdown")
build_content_breakdown(df_filtered, "X")
st.markdown("---")