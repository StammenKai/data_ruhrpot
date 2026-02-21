"""
Castrop-Rauxel Trend-Analyse
==============================
Liest gesammelte CSV-Daten und erstellt:
- Zeitreihen-Plots (Läden, Events)
- Kategorie-Verteilungen
- Veränderungsberichte (neu / geschlossen)
- HTML-Dashboard Export

Voraussetzungen:
    pip install pandas matplotlib seaborn jinja2
"""

import os
import glob
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = "output"
REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

# Stil
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams["figure.dpi"] = 120
plt.rcParams["font.family"] = "DejaVu Sans"
today = datetime.today().strftime("%Y-%m-%d")


# ── Daten laden ──────────────────────────────────────────────────────────────

def load_all_osm() -> pd.DataFrame:
    """Lädt alle historischen OSM-CSVs und kombiniert sie."""
    files = sorted(glob.glob(f"{OUTPUT_DIR}/osm_*.csv"))
    if not files:
        print("Keine OSM-Daten gefunden. Zuerst collector.py ausführen.")
        return pd.DataFrame()
    frames = []
    for f in files:
        df = pd.read_csv(f, dtype=str)
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined["datum"] = pd.to_datetime(combined["datum"])
    return combined


def load_all_events() -> pd.DataFrame:
    files = sorted(glob.glob(f"{OUTPUT_DIR}/events_*.csv"))
    if not files:
        return pd.DataFrame()
    frames = [pd.read_csv(f, dtype=str) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df["datum_abruf"] = pd.to_datetime(df["datum_abruf"])
    return df


def load_population() -> pd.DataFrame:
    path = f"{OUTPUT_DIR}/bevoelkerung.csv"
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


# ── Plot 1: Bevölkerungstrend ────────────────────────────────────────────────

def plot_population(df: pd.DataFrame):
    if df.empty:
        return None

    fig, ax = plt.subplots(figsize=(10, 5))
    df_real = df[df.get("prognose", pd.Series(False)).fillna(False) == False]
    df_prog = df[df.get("prognose", pd.Series(False)).fillna(False) == True]

    ax.plot(df_real["jahr"], df_real["bevoelkerung"], "o-", color="#2563EB",
            linewidth=2.5, markersize=7, label="Tatsächlich")
    if not df_prog.empty:
        ax.plot(df_prog["jahr"], df_prog["bevoelkerung"], "s--", color="#F59E0B",
                linewidth=2, markersize=6, label="Prognose (Bertelsmann)")
        # Verbindung real → prognose
        last_real = df_real.iloc[-1]
        first_prog = df_prog.iloc[0]
        ax.plot([last_real["jahr"], first_prog["jahr"]],
                [last_real["bevoelkerung"], first_prog["bevoelkerung"]],
                "--", color="#F59E0B", linewidth=1.5)

    ax.set_title(f"Bevölkerungsentwicklung Castrop-Rauxel", fontsize=14, fontweight="bold")
    ax.set_xlabel("Jahr")
    ax.set_ylabel("Einwohner")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x):,}".replace(",", ".")))
    ax.legend()
    ax.grid(axis="y", alpha=0.4)
    plt.tight_layout()

    path = f"{REPORT_DIR}/bevoelkerung_trend.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ Plot gespeichert: {path}")
    return path


# ── Plot 2: OSM Kategorie-Verteilung ────────────────────────────────────────

def plot_osm_categories(df: pd.DataFrame):
    if df.empty:
        return None

    # Neueste Snapshot
    latest = df[df["datum"] == df["datum"].max()]
    counts = latest["kategorie"].value_counts()

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Balkendiagramm
    colors = ["#2563EB", "#10B981", "#F59E0B", "#EF4444"]
    counts.plot(kind="bar", ax=axes[0], color=colors[:len(counts)], edgecolor="white")
    axes[0].set_title("Einrichtungen nach Kategorie\n(aktuell)", fontweight="bold")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("Anzahl")
    axes[0].tick_params(axis="x", rotation=25)
    for bar in axes[0].patches:
        axes[0].text(bar.get_x() + bar.get_width() / 2,
                     bar.get_height() + 1, str(int(bar.get_height())),
                     ha="center", va="bottom", fontsize=10)

    # Donut-Chart
    wedges, texts, autotexts = axes[1].pie(
        counts.values, labels=counts.index, autopct="%1.0f%%",
        colors=colors[:len(counts)], startangle=140,
        wedgeprops=dict(width=0.5, edgecolor="white")
    )
    axes[1].set_title("Anteil der Kategorien", fontweight="bold")

    plt.suptitle(f"OSM Einzelhandels- & Infrastrukturanalyse – {latest['datum'].max().date()}",
                 fontsize=13, fontweight="bold", y=1.01)
    plt.tight_layout()

    path = f"{REPORT_DIR}/osm_kategorien.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ Plot gespeichert: {path}")
    return path


# ── Plot 3: OSM Zeitreihe (Veränderung über Zeit) ────────────────────────────

def plot_osm_timeseries(df: pd.DataFrame):
    if df.empty or df["datum"].nunique() < 2:
        print("⚠ Zeitreihe braucht mind. 2 Messzeitpunkte")
        return None

    ts = df.groupby(["datum", "kategorie"]).size().unstack(fill_value=0)

    fig, ax = plt.subplots(figsize=(12, 5))
    colors = ["#2563EB", "#10B981", "#F59E0B", "#EF4444"]
    for i, col in enumerate(ts.columns):
        ax.plot(ts.index, ts[col], "o-", label=col,
                color=colors[i % len(colors)], linewidth=2)

    ax.set_title("Entwicklung Einrichtungen über Zeit\n(tägliche OSM-Snapshots)",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Datum")
    ax.set_ylabel("Anzahl")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m.%y"))
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    plt.tight_layout()

    path = f"{REPORT_DIR}/osm_zeitreihe.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ Plot gespeichert: {path}")
    return path


# ── Plot 4: Events Trend ─────────────────────────────────────────────────────

def plot_events_trend(df: pd.DataFrame):
    if df.empty:
        return None

    ts = df.groupby("datum_abruf").size().reset_index(name="anzahl_events")

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.fill_between(ts["datum_abruf"], ts["anzahl_events"], alpha=0.2, color="#8B5CF6")
    ax.plot(ts["datum_abruf"], ts["anzahl_events"], "o-", color="#8B5CF6", linewidth=2)
    ax.set_title("Veranstaltungen gescrapt (pro Tag)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Datum")
    ax.set_ylabel("Anzahl Events")
    ax.grid(alpha=0.3)
    plt.tight_layout()

    path = f"{REPORT_DIR}/events_trend.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ Plot gespeichert: {path}")
    return path


# ── Veränderungsreport: Neu / Geschlossen ────────────────────────────────────

def detect_changes(df: pd.DataFrame) -> dict:
    """Vergleicht letzten Snapshot mit vorherigem – findet neue/geschlossene Läden."""
    if df.empty or df["datum"].nunique() < 2:
        return {}

    dates = sorted(df["datum"].unique())
    prev_date, curr_date = dates[-2], dates[-1]

    prev_ids = set(df[df["datum"] == prev_date]["osm_id"].dropna())
    curr_ids = set(df[df["datum"] == curr_date]["osm_id"].dropna())

    neu = df[(df["datum"] == curr_date) & (df["osm_id"].isin(curr_ids - prev_ids))]
    geschlossen = df[(df["datum"] == prev_date) & (df["osm_id"].isin(prev_ids - curr_ids))]

    changes = {
        "zeitraum": f"{prev_date.date()} → {curr_date.date()}",
        "neu_anzahl": len(neu),
        "geschlossen_anzahl": len(geschlossen),
        "neu": neu[["name", "kategorie", "strasse", "hausnummer"]].to_dict("records"),
        "geschlossen": geschlossen[["name", "kategorie", "strasse", "hausnummer"]].to_dict("records"),
    }

    path = f"{REPORT_DIR}/veraenderungen_{today}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(changes, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n📊 Veränderungen ({changes['zeitraum']}):")
    print(f"   Neu:          {changes['neu_anzahl']} Einrichtungen")
    print(f"   Geschlossen:  {changes['geschlossen_anzahl']} Einrichtungen")
    return changes


# ── HTML Dashboard ───────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Castrop-Rauxel Dashboard – {today}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f1f5f9; color: #1e293b; }}
  header {{ background: #1e3a5f; color: white; padding: 1.5rem 2rem;
            display: flex; align-items: center; gap: 1rem; }}
  header h1 {{ font-size: 1.6rem; }}
  header p {{ font-size: 0.9rem; opacity: 0.7; margin-top: 0.2rem; }}
  .badge {{ background: #3b82f6; padding: 0.3rem 0.8rem; border-radius: 20px;
            font-size: 0.8rem; font-weight: 600; }}
  main {{ max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
               gap: 1rem; margin-bottom: 2rem; }}
  .kpi {{ background: white; border-radius: 12px; padding: 1.5rem;
          box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
  .kpi .label {{ font-size: 0.8rem; color: #64748b; text-transform: uppercase;
                 letter-spacing: 0.05em; margin-bottom: 0.5rem; }}
  .kpi .value {{ font-size: 2rem; font-weight: 700; color: #1e3a5f; }}
  .kpi .sub {{ font-size: 0.85rem; color: #64748b; margin-top: 0.2rem; }}
  .section {{ background: white; border-radius: 12px; padding: 1.5rem;
              box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 1.5rem; }}
  .section h2 {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem;
                 color: #1e3a5f; border-bottom: 2px solid #e2e8f0;
                 padding-bottom: 0.5rem; }}
  .plots {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
            gap: 1rem; margin-bottom: 1.5rem; }}
  .plot-card {{ background: white; border-radius: 12px; padding: 1rem;
                box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
  .plot-card img {{ width: 100%; border-radius: 6px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  th {{ background: #f8fafc; padding: 0.6rem 0.8rem; text-align: left;
        font-weight: 600; color: #475569; border-bottom: 2px solid #e2e8f0; }}
  td {{ padding: 0.55rem 0.8rem; border-bottom: 1px solid #f1f5f9; }}
  tr:hover td {{ background: #f8fafc; }}
  .tag {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px;
          font-size: 0.75rem; font-weight: 600; }}
  .tag-shop {{ background: #dbeafe; color: #1d4ed8; }}
  .tag-food {{ background: #d1fae5; color: #065f46; }}
  .tag-lei {{ background: #fef3c7; color: #92400e; }}
  footer {{ text-align: center; padding: 2rem; font-size: 0.8rem; color: #94a3b8; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>📊 Castrop-Rauxel Daten-Dashboard</h1>
    <p>Automatisch generiert am {today} · Quellen: OSM, IT.NRW, Stadtwebsite</p>
  </div>
  <span class="badge">Kostenlos</span>
</header>
<main>

  <div class="kpi-grid">
    <div class="kpi">
      <div class="label">Einwohner (2023)</div>
      <div class="value">71.500</div>
      <div class="sub">↓ -0,6% ggü. Vorjahr</div>
    </div>
    <div class="kpi">
      <div class="label">Einrichtungen (OSM)</div>
      <div class="value">{osm_total}</div>
      <div class="sub">Läden, Gastronomie, Freizeit</div>
    </div>
    <div class="kpi">
      <div class="label">Events gescrapt</div>
      <div class="value">{events_total}</div>
      <div class="sub">Stadtwebsite heute</div>
    </div>
    <div class="kpi">
      <div class="label">Neu (letzte Änderung)</div>
      <div class="value" style="color:#10b981">{neu_count}</div>
      <div class="sub">Neue Einrichtungen in OSM</div>
    </div>
    <div class="kpi">
      <div class="label">Geschlossen</div>
      <div class="value" style="color:#ef4444">{closed_count}</div>
      <div class="sub">Aus OSM entfernt</div>
    </div>
  </div>

  <div class="plots">
    <div class="plot-card">
      <h3 style="margin-bottom:0.5rem;font-size:0.95rem;color:#1e3a5f">Bevölkerungstrend</h3>
      <img src="../reports/bevoelkerung_trend.png" alt="Bevölkerung">
    </div>
    <div class="plot-card">
      <h3 style="margin-bottom:0.5rem;font-size:0.95rem;color:#1e3a5f">Einrichtungen nach Kategorie</h3>
      <img src="../reports/osm_kategorien.png" alt="OSM Kategorien">
    </div>
  </div>

  <div class="section">
    <h2>🏪 Aktuelle Einrichtungen (Top 50)</h2>
    <table>
      <thead>
        <tr><th>Name</th><th>Kategorie</th><th>Typ</th><th>Adresse</th><th>Öffnungszeiten</th></tr>
      </thead>
      <tbody>
        {osm_rows}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>📅 Aktuelle Veranstaltungen</h2>
    <table>
      <thead>
        <tr><th>Titel</th><th>Datum</th><th>Ort</th><th>Link</th></tr>
      </thead>
      <tbody>
        {event_rows}
      </tbody>
    </table>
  </div>

</main>
<footer>Daten: OpenStreetMap (ODbL), IT.NRW, Bertelsmann Stiftung, Stadt Castrop-Rauxel · 
Generiert mit Python · Für Forschungs- und Analysezwecke</footer>
</body>
</html>"""


def generate_html_dashboard(df_osm: pd.DataFrame, df_events: pd.DataFrame, changes: dict):
    # OSM Zeilen
    osm_rows = ""
    if not df_osm.empty:
        latest = df_osm[df_osm["datum"] == df_osm["datum"].max()].head(50)
        for _, r in latest.iterrows():
            tag_class = "tag-shop" if "Laden" in str(r["kategorie"]) else \
                        "tag-food" if "Gastro" in str(r["kategorie"]) else "tag-lei"
            osm_rows += f"""<tr>
              <td><strong>{r.get('name','–')}</strong></td>
              <td><span class="tag {tag_class}">{r.get('kategorie','')}</span></td>
              <td>{r.get('typ','')}</td>
              <td>{r.get('strasse','')} {r.get('hausnummer','')}, {r.get('plz','')}</td>
              <td style="font-size:0.75rem;color:#64748b">{r.get('oeffnungszeiten','')}</td>
            </tr>"""

    # Event Zeilen
    event_rows = ""
    if not df_events.empty:
        latest_events = df_events[df_events["datum_abruf"] == df_events["datum_abruf"].max()].head(30)
        for _, r in latest_events.iterrows():
            link = r.get("link", "")
            link_html = f'<a href="{link}" target="_blank" style="color:#3b82f6">→ Link</a>' if link else "–"
            event_rows += f"""<tr>
              <td><strong>{r.get('titel','–')[:80]}</strong></td>
              <td>{r.get('datum_event','')}</td>
              <td>{r.get('ort','')}</td>
              <td>{link_html}</td>
            </tr>"""

    html = HTML_TEMPLATE.format(
        today=today,
        osm_total=len(df_osm[df_osm["datum"] == df_osm["datum"].max()]) if not df_osm.empty else 0,
        events_total=len(df_events[df_events["datum_abruf"] == df_events["datum_abruf"].max()]) if not df_events.empty else 0,
        neu_count=changes.get("neu_anzahl", 0),
        closed_count=changes.get("geschlossen_anzahl", 0),
        osm_rows=osm_rows or "<tr><td colspan='5'>Keine Daten</td></tr>",
        event_rows=event_rows or "<tr><td colspan='4'>Keine Daten</td></tr>",
    )

    path = f"{REPORT_DIR}/dashboard_{today}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ HTML Dashboard: {path}")
    return path


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n🔍 Trend-Analyse Castrop-Rauxel – {today}\n{'='*50}")

    df_osm = load_all_osm()
    df_events = load_all_events()
    df_pop = load_population()

    plot_population(df_pop)
    plot_osm_categories(df_osm)
    plot_osm_timeseries(df_osm)
    plot_events_trend(df_events)

    changes = detect_changes(df_osm)
    generate_html_dashboard(df_osm, df_events, changes)

    print(f"\n✅ Alle Reports in: ./{REPORT_DIR}/")


if __name__ == "__main__":
    main()
