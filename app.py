import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
import io

try:
    import lseg.data as ld
    LSEG_AVAILABLE = True
except ImportError:
    LSEG_AVAILABLE = False

st.set_page_config(
    page_title="Market Benchmark Indices",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
/* ── Metric cards ─────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 6px;
    padding: 14px 18px;
}
[data-testid="metric-container"] label {
    font-size: 0.68rem !important;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    opacity: 0.55;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 1.2rem;
    font-weight: 600;
}

/* ── Sidebar ──────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    border-right: 1px solid rgba(255, 255, 255, 0.07);
}
[data-testid="stSidebar"] section {
    padding-top: 1.2rem;
}

/* ── Section subheaders ───────────────────────────────────────────── */
h3 {
    font-size: 0.78rem !important;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    opacity: 0.6;
}

/* ── Expander header ──────────────────────────────────────────────── */
details summary p {
    font-weight: 600;
    letter-spacing: 0.01em;
}

/* ── Page title area ──────────────────────────────────────────────── */
.page-header {
    padding-bottom: 0.75rem;
    margin-bottom: 0.25rem;
    border-bottom: 1px solid rgba(255,255,255,0.08);
}
.page-header h1 {
    font-size: 1.55rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin: 0 0 2px 0;
}
.page-header .subtitle {
    font-size: 0.78rem;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    opacity: 0.45;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Index catalogue
# ─────────────────────────────────────────────────────────────────────────────

JPM_INDICES = {
    "JPIBHYET": {
        "label": "JPIBHYET – iBoxx EUR HY Duration Hedged",
        "full_name": "J.P. Morgan iBoxx EUR High Yield Duration Hedged Total Return Index",
        "description": (
            "Synthetic exposure to European high-yield credit via CDS/iTraxx, "
            "with interest rate risk neutralised through Interest Rate Swaps (IRS). "
            "IRS weights are calibrated to match the modified duration of the iBoxx HY Liquid "
            "index by maturity bucket. Provides a pure HY credit spread return, stripped of "
            "duration effect — useful as a credit-only benchmark for HY-sensitive portfolios."
        ),
        "color": "rgb(0, 204, 150)",
        "inception": "Jan 2016",
        "frequency": "Daily",
    },
    "JCREVCM1": {
        "label": "JCREVCM1 – iTraxx Main Credit Vol",
        "full_name": "J.P. Morgan Credit Europe Main Volatility Carry Index",
        "description": (
            "Short swaption strategy on iTraxx Main (EUR IG CDS), delta-hedged with CDS index transactions. "
            "Exposure to the implied vs. realised volatility premium in European investment-grade credit."
        ),
        "color": "rgb(239, 85, 59)",
        "inception": "Jan 2013",
        "frequency": "Daily",
    },
    "JCREVCX1": {
        "label": "JCREVCX1 – iTraxx Crossover Credit Vol",
        "full_name": "J.P. Morgan Credit Europe Crossover Volatility Carry Index",
        "description": (
            "Short swaption strategy on iTraxx Crossover (EUR HY CDS), delta-hedged with CDS index transactions. "
            "Exposure to the implied vs. realised volatility premium in European sub-investment-grade credit. "
            "Relevant sentiment indicator for portfolios exposed to CLO mezzanine, CLO equity and European ABS."
        ),
        "color": "rgb(255, 161, 90)",
        "inception": "Jan 2013",
        "frequency": "Daily",
    },
    "JCRELCGH": {
        "label": "JCRELCGH – Global HY USD",
        "full_name": "J.P. Morgan Credit Global High Yield USD Index",
        "description": (
            "Broad-market total return index tracking USD-denominated global high-yield "
            "corporate bonds. Covers sub-investment-grade issuers across developed and "
            "emerging markets, capturing coupon income plus price return. Used as a "
            "global HY credit benchmark to contextualise relative performance of "
            "credit-oriented and CLO portfolios."
        ),
        "color": "rgb(171, 99, 250)",
        "inception": "Mar 2007",
        "frequency": "Daily",
    },
}

FRED_INDICES = {
    "BAMLHE00EHYIEY": {
        "label": "BAMLHE00EHYIEY – Euro HY Effective Yield",
        "full_name": "ICE BofA Euro High Yield Index, Effective Yield",
        "description": (
            "Effective yield of the ICE BofA Euro High Yield Index, tracking EUR-denominated "
            "sub-investment-grade corporate bonds. Key indicator of credit risk premium "
            "in European high-yield markets. Sourced from FRED (Federal Reserve Bank of St. Louis)."
        ),
        "color": "rgb(0, 180, 216)",
        "inception": "Jan 1998",
        "frequency": "Daily",
    },
    "BAMLH0A0HYM2EY": {
        "label": "BAMLH0A0HYM2EY – US HY Effective Yield",
        "full_name": "ICE BofA US High Yield Master II Index, Effective Yield",
        "description": (
            "Effective yield of the ICE BofA US High Yield Master II Index, tracking "
            "USD-denominated sub-investment-grade corporate bonds. Benchmark indicator "
            "for US high-yield credit conditions. Sourced from FRED (Federal Reserve Bank of St. Louis)."
        ),
        "color": "rgb(255, 140, 0)",
        "inception": "Dec 1996",
        "frequency": "Daily",
    },
}

REFINITIV_INDICES = {
    ".FTEHYMEURT": {
        "label": ".FTEHYMEURT – FTSE Euro HY Market EUR TR",
        "full_name": "FTSE Euro High Yield Market EUR Total Return Index",
        "description": (
            "Total return index measuring performance of EUR-denominated sub-investment-grade "
            "corporate bonds across developed European markets. Used as broad HY credit benchmark."
        ),
        "color": "rgb(220, 100, 180)",
        "inception": "Jan 2000",
        "frequency": "Daily",
    },
}

# ── Static fallback – Flat Rock CLO Equity (scraped 2026-05-17) ───────────────
FLATROCK_CSV = """Date,Index Level,Quarterly Return,Yearly Return
2014-09-30,100.00,,
2014-12-31,100.21,0.21,
2015-03-31,101.02,0.80,
2015-06-30,102.37,1.34,
2015-09-30,94.71,-7.48,
2015-12-31,83.92,-11.39,-16.26
2016-03-31,83.57,-0.42,
2016-06-30,97.59,16.78,
2016-09-30,111.97,14.74,
2016-12-31,124.88,11.53,48.81
2017-03-31,125.64,0.61,
2017-06-30,130.36,3.75,
2017-09-30,128.54,-1.39,
2017-12-31,134.11,4.33,7.39
2018-03-31,138.53,3.29,
2018-06-30,139.59,0.77,
2018-09-30,142.52,2.10,
2018-12-31,121.72,-14.59,-9.24
2019-03-31,133.55,9.72,
2019-06-30,133.13,-0.31,
2019-09-30,119.74,-10.06,
2019-12-31,121.00,1.05,-0.59
2020-03-31,84.21,-30.41,
2020-06-30,90.61,7.60,
2020-09-30,102.83,13.49,
2020-12-31,133.57,29.89,10.39
2021-03-31,145.65,9.04,
2021-06-30,158.13,8.57,
2021-09-30,170.45,7.79,
2021-12-31,173.52,1.80,29.91
2022-03-31,169.92,-2.08,
2022-06-30,148.71,-12.48,
2022-09-30,153.21,3.03,
2022-12-31,153.34,0.09,-11.63
2023-03-31,157.09,2.44,
2023-06-30,160.29,2.04,
2023-09-30,177.12,10.49,
2023-12-31,187.30,5.75,22.15
2024-03-31,197.10,5.23,
2024-06-30,204.30,3.66,
2024-09-30,207.98,1.80,
2024-12-31,218.36,4.99,16.58
2025-03-31,207.55,-4.95,
2025-06-30,215.64,3.90,
2025-09-30,216.31,0.31,
2025-12-31,200.69,-7.22,-8.09"""

_JPM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Referer": "https://www.jpmorganindices.com/",
    "Accept": "application/json",
}

# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _scrape_flatrock() -> pd.DataFrame | None:
    try:
        resp = requests.get(
            "https://flatrockglobal.com/clo-equity-index/",
            headers={"User-Agent": _JPM_HEADERS["User-Agent"]},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return None
        best = max(tables, key=lambda t: len(t.find_all("tr")))
        df = pd.read_html(str(best))[0]
        df.columns = [str(c).strip() for c in df.columns]
        date_col = next((c for c in df.columns if any(k in c.lower() for k in ["date", "quarter", "period"])), df.columns[0])
        level_col = next((c for c in df.columns if any(k in c.lower() for k in ["level", "index", "value"])), df.columns[1] if len(df.columns) > 1 else None)
        qret_col = next((c for c in df.columns if "quarter" in c.lower() and "return" in c.lower()), None)
        yret_col = next((c for c in df.columns if any(k in c.lower() for k in ["annual", "yearly", "year"])), None)
        out = pd.DataFrame()
        out["Date"] = pd.to_datetime(df[date_col], errors="coerce")
        if level_col:
            out["Index Level"] = pd.to_numeric(df[level_col].astype(str).str.replace("%", "").str.replace(",", ""), errors="coerce")
        if qret_col:
            out["Quarterly Return"] = pd.to_numeric(df[qret_col].astype(str).str.replace("%", ""), errors="coerce")
        if yret_col:
            out["Yearly Return"] = pd.to_numeric(df[yret_col].astype(str).str.replace("%", ""), errors="coerce")
        out = out.dropna(subset=["Date", "Index Level"]).sort_values("Date").reset_index(drop=True)
        return out if len(out) > 5 else None
    except Exception:
        return None


def _flatrock_fallback() -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(FLATROCK_CSV), parse_dates=["Date"])
    for col in ["Index Level", "Quarterly Return", "Yearly Return"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("Date").reset_index(drop=True)


@st.cache_data(ttl=86400, show_spinner=False)
def load_flatrock() -> tuple[pd.DataFrame, str]:
    df = _scrape_flatrock()
    return (df, "live") if df is not None else (_flatrock_fallback(), "fallback")


@st.cache_data(ttl=3600, show_spinner=False)
def load_fred(series_id: str) -> tuple[pd.DataFrame, str]:
    try:
        api_key = st.secrets.get("FRED_API_KEY", "")
        if not api_key:
            return pd.DataFrame(), "no_key"
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={api_key}&file_type=json&observation_start=1990-01-01"
        )
        resp = requests.get(url, headers={"User-Agent": _JPM_HEADERS["User-Agent"]}, timeout=15)
        resp.raise_for_status()
        obs = resp.json().get("observations", [])
        if not obs:
            return pd.DataFrame(), "error"
        df = pd.DataFrame(obs)[["date", "value"]].rename(columns={"date": "Date", "value": "Value"})
        df["Date"] = pd.to_datetime(df["Date"])
        df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
        df = df.dropna().sort_values("Date").reset_index(drop=True)
        return df, "live"
    except Exception:
        return pd.DataFrame(), "error"


@st.cache_data(ttl=3600, show_spinner=False)
def load_refinitiv(ric: str) -> tuple[pd.DataFrame, str]:
    if not LSEG_AVAILABLE:
        return pd.DataFrame(), "no_lib"
    try:
        ref = st.secrets.get("refinitiv", {})
        if not ref.get("app_key"):
            return pd.DataFrame(), "no_key"
        session = ld.session.platform.Definition(
            app_key=ref["app_key"],
            grant=ld.session.platform.GrantPassword(
                username=ref["username"],
                password=ref["password"],
            ),
            signon_control=True,
        ).get_session()
        session.open()
        ld.session.set_default(session)
        try:
            df_raw = ld.get_history(
                universe=ric,
                start="1998-01-01",
                end=date.today().isoformat(),
            )
        finally:
            session.close()
        if df_raw is None or df_raw.empty:
            return pd.DataFrame(), "error"
        df_raw = df_raw.reset_index()
        date_col = df_raw.columns[0]
        num_cols = [
            c for c in df_raw.columns[1:]
            if pd.to_numeric(df_raw[c], errors="coerce").notna().any()
        ]
        if not num_cols:
            return pd.DataFrame(), "error"
        df_raw = df_raw[[date_col, num_cols[0]]].copy()
        df_raw.columns = ["Date", "Index Level"]
        dates = pd.to_datetime(df_raw["Date"])
        df_raw["Date"] = dates.dt.tz_convert(None) if dates.dt.tz is not None else dates
        df_raw["Index Level"] = pd.to_numeric(df_raw["Index Level"], errors="coerce")
        df_raw = df_raw.dropna(subset=["Index Level"]).sort_values("Date").reset_index(drop=True)
        return df_raw, "live"
    except Exception:
        return pd.DataFrame(), "error"


@st.cache_data(ttl=3600, show_spinner=False)
def load_jpmorgan(ticker: str) -> tuple[pd.DataFrame, str]:
    try:
        resp = requests.get(
            f"https://www.jpmorganindices.com/indices/timeseries/{ticker}",
            headers=_JPM_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        pts = resp.json().get("data", [])
        if not pts:
            return pd.DataFrame(), "error"
        df = pd.DataFrame(pts).rename(columns={"x": "Date", "y": "Index Level"})
        df["Date"] = pd.to_datetime(df["Date"])
        df["Index Level"] = pd.to_numeric(df["Index Level"], errors="coerce")
        df = df.dropna().sort_values("Date").reset_index(drop=True)
        return df, "live"
    except Exception:
        return pd.DataFrame(), "error"


# ─────────────────────────────────────────────────────────────────────────────
# Stat helpers
# ─────────────────────────────────────────────────────────────────────────────

def _stats_quarterly(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    s, e = df["Index Level"].iloc[0], df["Index Level"].iloc[-1]
    yrs = (df["Date"].iloc[-1] - df["Date"].iloc[0]).days / 365.25
    q_rets = df["Quarterly Return"].dropna()
    max_dd = ((df["Index Level"] - df["Index Level"].cummax()) / df["Index Level"].cummax() * 100).min()
    return {
        "Total Return": f"{(e/s - 1)*100:.1f}%",
        "Ann. Return": f"{((e/s)**(1/yrs) - 1)*100:.1f}%" if yrs > 0 else "—",
        "Ann. Volatility": f"{q_rets.std() * 2:.1f}%",
        "Max Drawdown": f"{max_dd:.1f}%",
        "Current Level": f"{e:.2f}",
        "Latest Quarter": f"{q_rets.iloc[-1]:+.2f}%" if not q_rets.empty else "—",
    }


def _stats_daily(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 2:
        return {}
    s, e = df["Index Level"].iloc[0], df["Index Level"].iloc[-1]
    yrs = (df["Date"].iloc[-1] - df["Date"].iloc[0]).days / 365.25
    vol = df["Index Level"].pct_change().dropna().std() * (252 ** 0.5) * 100
    max_dd = ((df["Index Level"] - df["Index Level"].cummax()) / df["Index Level"].cummax() * 100).min()
    return {
        "Total Return": f"{(e/s - 1)*100:.1f}%",
        "Ann. Return": f"{((e/s)**(1/yrs) - 1)*100:.1f}%" if yrs > 0 else "—",
        "Ann. Volatility": f"{vol:.1f}%",
        "Max Drawdown": f"{max_dd:.1f}%",
        "Current Level": f"{e:.2f}",
        "Last Update": df["Date"].iloc[-1].strftime("%d %b %Y"),
    }


def _stats_yield(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 2:
        return {}
    last = df["Value"].iloc[-1]
    cutoff_1y = df["Date"].iloc[-1] - pd.Timedelta(days=365)
    year_data = df[df["Date"] >= cutoff_1y]["Value"]
    ytd_start = df[df["Date"].dt.year == df["Date"].iloc[-1].year]["Value"]
    ytd_chg = (last - ytd_start.iloc[0]) * 100 if not ytd_start.empty else None
    return {
        "Current Yield": f"{last:.2f}%",
        "52W High": f"{year_data.max():.2f}%",
        "52W Low": f"{year_data.min():.2f}%",
        "YTD Change": f"{ytd_chg:+.0f} bps" if ytd_chg is not None else "—",
        "Last Update": df["Date"].iloc[-1].strftime("%d %b %Y"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Chart helpers
# ─────────────────────────────────────────────────────────────────────────────

_GRID_COLOR = "rgba(128,128,128,0.15)"
_ZERO_COLOR = "rgba(128,128,128,0.4)"


def _base_layout(title: str, y_title: str, height: int = 380) -> dict:
    return dict(
        title=title, yaxis_title=y_title, xaxis_title=None,
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=0, r=0, t=40, b=0), height=height,
    )


def _style(fig: go.Figure) -> go.Figure:
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor=_GRID_COLOR)
    return fig


def _level_chart(df: pd.DataFrame, y_col: str, y_label: str, color: str,
                 name: str, chart_type: str, date_fmt: str = "%d %b %Y") -> go.Figure:
    kwargs = dict(
        x=df["Date"], y=df[y_col],
        line=dict(color=color, width=2.5), name=name,
        hovertemplate=f"%{{x|{date_fmt}}}<br>Level: %{{y:.2f}}<extra></extra>",
    )
    if chart_type == "Area":
        r, g, b = _parse_rgb(color)
        kwargs.update(fill="tozeroy", fillcolor=f"rgba({r},{g},{b},0.12)")
    return _style(go.Figure(go.Scatter(**kwargs)))


def _parse_rgb(color_str: str) -> tuple[int, int, int]:
    import re
    nums = re.findall(r"\d+", color_str)
    return int(nums[0]), int(nums[1]), int(nums[2])




# ─────────────────────────────────────────────────────────────────────────────
# Shared JPM index renderer
# ─────────────────────────────────────────────────────────────────────────────

def render_jpm_index(ticker: str, df: pd.DataFrame, source: str,
                     date_range: tuple, chart_type: str) -> None:
    meta = JPM_INDICES[ticker]
    badge = "🟢 Live" if source == "live" else "🔴 Error"

    with st.expander(meta["label"], expanded=True):
        st.markdown(f"*{meta['description']}*")
        st.caption(f"Inception: {meta['inception']} · {meta['frequency']} · jpmorganindices.com · {badge}")

        if source == "error" or df.empty:
            st.error(f"Could not fetch {ticker} data from JP Morgan API.")
            return

        mask = (df["Date"].dt.date >= date_range[0]) & (df["Date"].dt.date <= date_range[1])
        dff = df[mask].copy()

        if dff.empty:
            st.warning("No data in selected range.")
            return

        stats = _stats_daily(dff)
        cols = st.columns(len(stats))
        for col, (lbl, val) in zip(cols, stats.items()):
            col.metric(lbl, val)

        st.divider()

        fig = _level_chart(dff, "Index Level", "Index Level", meta["color"], ticker, chart_type)
        fig.update_layout(**_base_layout(f"{ticker} Index Level", "Index Level"))
        st.plotly_chart(fig, width='stretch')


def render_fred_index(series_id: str, df: pd.DataFrame, source: str,
                      date_range: tuple, chart_type: str) -> None:
    meta = FRED_INDICES[series_id]
    badge = "🟢 Live" if source == "live" else "🔴 Error"

    with st.expander(meta["label"], expanded=True):
        st.markdown(f"*{meta['description']}*")
        st.caption(f"Inception: {meta['inception']} · {meta['frequency']} · fred.stlouisfed.org · {badge}")

        if source == "no_key":
            st.warning("FRED API key not configured. Add FRED_API_KEY to Streamlit secrets.")
            return
        if source == "error" or df.empty:
            st.error(f"Could not fetch {series_id} data from FRED.")
            return

        mask = (df["Date"].dt.date >= date_range[0]) & (df["Date"].dt.date <= date_range[1])
        dff = df[mask].copy()

        if dff.empty:
            st.warning("No data in selected range.")
            return

        stats = _stats_yield(dff)
        cols = st.columns(len(stats))
        for col, (lbl, val) in zip(cols, stats.items()):
            col.metric(lbl, val)

        st.divider()

        fig = _level_chart(dff, "Value", "Effective Yield (%)", meta["color"], series_id, chart_type)
        fig.update_layout(**_base_layout(f"{series_id} – Effective Yield", "Yield (%)"))
        st.plotly_chart(fig, width='stretch')


def render_refinitiv_index(ric: str, df: pd.DataFrame, source: str,
                           date_range: tuple, chart_type: str) -> None:
    meta = REFINITIV_INDICES[ric]
    badge = "🟢 Live" if source == "live" else "🔴 Error"

    with st.expander(meta["label"], expanded=True):
        st.markdown(f"*{meta['description']}*")
        st.caption(f"Inception: {meta['inception']} · {meta['frequency']} · Refinitiv/LSEG · {badge}")

        if source == "no_key":
            st.warning("Refinitiv credentials not configured in Streamlit secrets.")
            return
        if source == "no_lib":
            st.warning("lseg-data library not installed. Run: pip install lseg-data")
            return
        if source == "error" or df.empty:
            st.error(f"Could not fetch {ric} data from Refinitiv.")
            return

        mask = (df["Date"].dt.date >= date_range[0]) & (df["Date"].dt.date <= date_range[1])
        dff = df[mask].copy()

        if dff.empty:
            st.warning("No data in selected range.")
            return

        stats = _stats_daily(dff)
        cols = st.columns(len(stats))
        for col, (lbl, val) in zip(cols, stats.items()):
            col.metric(lbl, val)

        st.divider()

        fig = _level_chart(dff, "Index Level", "Index Level", meta["color"], ric, chart_type)
        fig.update_layout(**_base_layout(f"{ric} Index Level", "Index Level"))
        st.plotly_chart(fig, width='stretch')


# ─────────────────────────────────────────────────────────────────────────────
# Layout – sidebar
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="page-header">
    <div class="subtitle">Index Monitor</div>
    <h1>Market Benchmark Indices</h1>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("""
    <div style="padding:0.25rem 0 1.25rem; border-bottom:1px solid rgba(255,255,255,0.08); margin-bottom:0.5rem;">
        <div style="font-size:0.65rem;letter-spacing:0.12em;text-transform:uppercase;opacity:0.4;">Controls</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Refresh live data", width='stretch'):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.subheader("Indices")

    _EU_JPM  = ["JPIBHYET", "JCREVCM1", "JCREVCX1"]
    _US_JPM  = ["JCRELCGH"]
    _EU_FRED = ["BAMLHE00EHYIEY"]
    _US_FRED = ["BAMLH0A0HYM2EY"]
    _EU_REF  = [".FTEHYMEURT"]

    jpm_enabled       = {}
    fred_enabled      = {}
    refinitiv_enabled = {}

    with st.expander("🇪🇺 EU Exposure", expanded=True):
        for t in _EU_JPM:
            jpm_enabled[t] = st.checkbox(JPM_INDICES[t]["label"], value=True, key=f"idx_{t}")
        for s in _EU_FRED:
            fred_enabled[s] = st.checkbox(FRED_INDICES[s]["label"], value=True, key=f"idx_{s}")
        for r in _EU_REF:
            refinitiv_enabled[r] = st.checkbox(REFINITIV_INDICES[r]["label"], value=True, key=f"idx_{r}")

    with st.expander("🇺🇸 US Exposure", expanded=True):
        show_flatrock = st.checkbox("Flat Rock CLO Equity (quarterly)", value=True, key="idx_flatrock")
        for t in _US_JPM:
            jpm_enabled[t] = st.checkbox(JPM_INDICES[t]["label"], value=True, key=f"idx_{t}")
        for s in _US_FRED:
            fred_enabled[s] = st.checkbox(FRED_INDICES[s]["label"], value=True, key=f"idx_{s}")

    chart_type = "Line"

# ─────────────────────────────────────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────────────────────────────────────

with st.spinner("Loading data…"):
    fr_df, fr_source = load_flatrock()
    jpm_data: dict[str, tuple[pd.DataFrame, str]] = {}
    for ticker, enabled in jpm_enabled.items():
        if enabled:
            jpm_data[ticker] = load_jpmorgan(ticker)
    fred_data: dict[str, tuple[pd.DataFrame, str]] = {}
    for series_id, enabled in fred_enabled.items():
        if enabled:
            fred_data[series_id] = load_fred(series_id)
    refinitiv_data: dict[str, tuple[pd.DataFrame, str]] = {}
    for ric, enabled in refinitiv_enabled.items():
        if enabled:
            refinitiv_data[ric] = load_refinitiv(ric)

# ─────────────────────────────────────────────────────────────────────────────
# Global date range
# ─────────────────────────────────────────────────────────────────────────────

all_dates = list(fr_df["Date"].dt.date)
for df, _ in jpm_data.values():
    if not df.empty:
        all_dates += list(df["Date"].dt.date)
for df, _ in fred_data.values():
    if not df.empty:
        all_dates += list(df["Date"].dt.date)
for df, _ in refinitiv_data.values():
    if not df.empty:
        all_dates += list(df["Date"].dt.date)

min_date = min(all_dates)
max_date = max(all_dates)

st.sidebar.divider()
st.sidebar.subheader("Time range")

# Quick-select presets
_today = max_date
_presets = {
    "YTD": (date(_today.year, 1, 1), _today),
    "6M":  (_today - timedelta(days=182), _today),
    "1Y":  (_today - timedelta(days=365), _today),
    "2Y":  (_today - timedelta(days=730), _today),
    "5Y":  (_today - timedelta(days=1825), _today),
    "Max": (min_date, max_date),
}

_preset_sel = st.sidebar.radio(
    "Quick select",
    options=list(_presets.keys()),
    index=len(_presets) - 1,
    horizontal=False,
    key="preset_radio",
)

# When preset changes, push new range into session state
if "date_range" not in st.session_state:
    st.session_state.date_range = (min_date, max_date)

if st.session_state.get("_last_preset") != _preset_sel:
    _ps, _pe = _presets[_preset_sel]
    st.session_state.date_range = (max(_ps, min_date), min(_pe, max_date))
    st.session_state["_last_preset"] = _preset_sel

date_range = st.sidebar.slider(
    "Custom range",
    min_value=min_date,
    max_value=max_date,
    value=st.session_state.date_range,
    format="MMM YYYY",
)
st.session_state.date_range = date_range

# ─────────────────────────────────────────────────────────────────────────────
# Combined overview – all enabled indices
# ─────────────────────────────────────────────────────────────────────────────

def _build_combined_series(
    show_flatrock: bool,
    fr_df: pd.DataFrame,
    jpm_data: dict,
    fred_data: dict,
    refinitiv_data: dict,
    date_range: tuple,
) -> list[dict]:
    series = []

    if show_flatrock:
        mask = (fr_df["Date"].dt.date >= date_range[0]) & (fr_df["Date"].dt.date <= date_range[1])
        df_f = fr_df[mask].dropna(subset=["Index Level"])
        if not df_f.empty:
            series.append({
                "name": "Flat Rock CLO",
                "color": "rgb(99,110,250)",
                "dates": df_f["Date"],
                "levels": df_f["Index Level"],
                "is_yield": False,
            })

    for ticker, (df, source) in jpm_data.items():
        if source == "error" or df.empty:
            continue
        mask = (df["Date"].dt.date >= date_range[0]) & (df["Date"].dt.date <= date_range[1])
        dff = df[mask].dropna(subset=["Index Level"])
        if dff.empty:
            continue
        series.append({
            "name": ticker,
            "color": JPM_INDICES[ticker]["color"],
            "dates": dff["Date"],
            "levels": dff["Index Level"],
            "is_yield": False,
        })

    for series_id, (df, source) in fred_data.items():
        if source in ("error", "no_key") or df.empty:
            continue
        mask = (df["Date"].dt.date >= date_range[0]) & (df["Date"].dt.date <= date_range[1])
        dff = df[mask].dropna(subset=["Value"])
        if dff.empty:
            continue
        series.append({
            "name": series_id,
            "color": FRED_INDICES[series_id]["color"],
            "dates": dff["Date"],
            "levels": dff["Value"],
            "is_yield": True,
        })

    for ric, (df, source) in refinitiv_data.items():
        if source in ("error", "no_key", "no_lib") or df.empty:
            continue
        mask = (df["Date"].dt.date >= date_range[0]) & (df["Date"].dt.date <= date_range[1])
        dff = df[mask].dropna(subset=["Index Level"])
        if dff.empty:
            continue
        series.append({
            "name": ric,
            "color": REFINITIV_INDICES[ric]["color"],
            "dates": dff["Date"],
            "levels": dff["Index Level"],
            "is_yield": False,
        })

    return series


combined = _build_combined_series(show_flatrock, fr_df, jpm_data, fred_data, refinitiv_data, date_range)

if len(combined) >= 1:
    st.subheader("Combined Performance")

    # Cumulative return — all series (FRED: % change in yield from period start)
    fig_ret = go.Figure()
    for s in combined:
        base = s["levels"].iloc[0]
        cum_ret = ((s["levels"] / base - 1) * 100).round(2)
        suffix = " (yield Δ%)" if s["is_yield"] else ""
        fig_ret.add_trace(go.Scatter(
            x=s["dates"], y=cum_ret,
            name=s["name"] + suffix,
            line=dict(color=s["color"], width=2),
            hovertemplate="%{x|%d %b %Y}<br>" + s["name"] + ": %{y:+.2f}%<extra></extra>",
        ))
    fig_ret.add_hline(y=0, line_color=_ZERO_COLOR)
    fig_ret.update_layout(**_base_layout("Cumulative Return / Yield Change (%)", "Return (%)", 440))
    fig_ret.update_layout(
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
        margin=dict(l=0, r=0, t=40, b=60),
        yaxis_hoverformat="+.2f",
        yaxis_tickformat=".2f",
    )
    _style(fig_ret)
    st.plotly_chart(fig_ret, width='stretch')

    st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Section 1 – Flat Rock CLO Equity (quarterly)
# ─────────────────────────────────────────────────────────────────────────────

if show_flatrock:
    badge_fr = "🟢 Live" if fr_source == "live" else "🟡 Cached (2026-05-17)"
    with st.expander("Flat Rock Global CLO Equity Index", expanded=True):
        st.markdown(
            "*The Flat Rock CLO Equity Returns Index seeks to measure the unlevered, gross of fee performance "
            "of US CLO equity tranches as represented by the market-weighted performance of the underlying assets "
            "of funds that publicly disclose their holdings and fair market values to the U.S. Securities and "
            "Exchange Commission. The reporting funds satisfy certain eligibility criteria. "
            "The index inception date is September 30, 2014. The index is calculated quarterly on a 75-day lag.*"
        )
        st.caption(f"Inception: Sep 2014 · Quarterly · flatrockglobal.com · {badge_fr}")

        mask = (fr_df["Date"].dt.date >= date_range[0]) & (fr_df["Date"].dt.date <= date_range[1])
        df_f = fr_df[mask].copy()

        if df_f.empty:
            st.warning("No data in selected range.")
        else:
            stats = _stats_quarterly(df_f)
            cols = st.columns(len(stats))
            for col, (lbl, val) in zip(cols, stats.items()):
                col.metric(lbl, val)

            st.divider()

            fig_fr = _level_chart(df_f, "Index Level", "Index Level", "rgb(99,110,250)", "CLO Equity", chart_type, "%b %Y")
            fig_fr.update_layout(**_base_layout("CLO Equity Index Level", "Index Level"))
            st.plotly_chart(fig_fr, width='stretch')

            with st.expander("Raw data"):
                disp = df_f[["Date", "Index Level", "Quarterly Return", "Yearly Return"]].copy()
                disp["Date"] = disp["Date"].dt.strftime("%b %Y")
                disp["Quarterly Return"] = disp["Quarterly Return"].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "—")
                disp["Yearly Return"] = disp["Yearly Return"].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "—")
                disp["Index Level"] = disp["Index Level"].apply(lambda x: f"{x:.2f}")
                st.dataframe(disp, width='stretch', hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# Sections 2-5 – JP Morgan daily indices
# ─────────────────────────────────────────────────────────────────────────────

for ticker, (df, source) in jpm_data.items():
    render_jpm_index(
        ticker=ticker,
        df=df,
        source=source,
        date_range=date_range,
        chart_type=chart_type,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Sections – FRED yield indices
# ─────────────────────────────────────────────────────────────────────────────

for series_id, (df, source) in fred_data.items():
    render_fred_index(
        series_id=series_id,
        df=df,
        source=source,
        date_range=date_range,
        chart_type=chart_type,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Sections – Refinitiv/LSEG daily indices
# ─────────────────────────────────────────────────────────────────────────────

for ric, (df, source) in refinitiv_data.items():
    render_refinitiv_index(
        ric=ric,
        df=df,
        source=source,
        date_range=date_range,
        chart_type=chart_type,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    "Sources: Flat Rock Global (flatrockglobal.com) · J.P. Morgan Strategic Indices (jpmorganindices.com) · "
    "FRED, Federal Reserve Bank of St. Louis (fred.stlouisfed.org) · Refinitiv/LSEG. "
    "For informational purposes only. Not investment advice."
)
