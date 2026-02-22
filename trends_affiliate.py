"""
Google Trends Modul für Castrop-Rauxel
========================================
Ergänzt den collector.py um:
- Regionale Suchtrends aus dem Ruhrgebiet
- Saisonale Muster erkennen
- Affiliate-Chancen automatisch bewerten & ranken

Voraussetzungen:
    pip install pytrends pandas matplotlib

Wie es funktioniert (für Laien):
    pytrends ist ein inoffizielles Python-Werkzeug das Google Trends
    im Hintergrund abfragt – so als würdest du selbst auf
    trends.google.de nachschauen, nur automatisch und täglich.
"""

import time
import json
import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from datetime import date, datetime
from pytrends.request import TrendReq

# ── Konfiguration ─────────────────────────────────────────────────────────────

OUTPUT_DIR = "output"
REPORT_DIR = "reports"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)
today = date.today().isoformat()

# Region: Ruhrgebiet / NRW
# Google Trends nutzt ISO-Codes: DE-NW = Nordrhein-Westfalen
GEO_REGION = "DE-NW"

# ── Keyword-Gruppen mit Affiliate-Kontext ─────────────────────────────────────
#
# Hier definierst du, welche Themen dich interessieren.
# Für jede Gruppe kannst du passende Affiliate-Programme hinterlegen.
#
# Aufbau:
#   "Gruppenname": {
#       "keywords": ["Suchwort 1", "Suchwort 2", ...],  # max. 5 pro Gruppe!
#       "affiliate": ["Partner 1", "Partner 2"],         # passende Programme
#       "kategorie": "Themenbereich",
#   }

KEYWORD_GROUPS = {
    "Fahrrad & Outdoor": {
        "keywords": ["Fahrrad kaufen", "E-Bike", "Fahrradreparatur", "Camping", "Wanderschuhe"],
        "affiliate": ["Decathlon", "Amazon", "Fahrrad.de", "Bergfreunde"],
        "kategorie": "Sport & Outdoor",
    },
    "Heimwerken & Garten": {
        "keywords": ["Rasenmäher", "Werkzeug kaufen", "Gartenmöbel", "Bohrmaschine", "Gartenhaus"],
        "affiliate": ["OBI", "Hornbach", "Amazon", "Bauhaus"],
        "kategorie": "Heim & Garten",
    },
    "Elektronik & Technik": {
        "keywords": ["Smartphone kaufen", "Laptop günstig", "Fernseher", "Kopfhörer", "Tablet"],
        "affiliate": ["MediaMarkt", "Amazon", "Alternate", "Notebooksbilliger"],
        "kategorie": "Elektronik",
    },
    "Gesundheit & Fitness": {
        "keywords": ["Fitnessstudio", "Protein kaufen", "Laufschuhe", "Yoga", "Heimtrainer"],
        "affiliate": ["Myprotein", "Amazon", "SportScheck", "Gymondo"],
        "kategorie": "Gesundheit",
    },
    "Familie & Kinder": {
        "keywords": ["Kinderfahrrad", "Spielzeug kaufen", "Kinderwagen", "Schulranzen", "Babyausstattung"],
        "affiliate": ["Amazon", "myToys", "baby-walz", "Jako-o"],
        "kategorie": "Familie",
    },
    "Mode & Lifestyle": {
        "keywords": ["Winterjacke kaufen", "Sneaker", "Kleidung online", "Handtasche", "Schmuck"],
        "affiliate": ["Zalando", "AboutYou", "Amazon", "Otto"],
        "kategorie": "Mode",
    },
}

# ── Google Trends Abfrage ─────────────────────────────────────────────────────

def init_pytrends() -> TrendReq:
    """
    Verbindet sich mit Google Trends.
    Hinweis: retries & backoff_factor werden weggelassen –
    diese nutzen intern urllib3's Retry() mit 'method_whitelist'
    das in neueren Versionen umbenannt wurde und einen Fehler wirft.
    """
    return TrendReq(
        hl="de-DE",
        tz=60,
        timeout=(10, 25),
    )


def fetch_trend_for_group(pytrends: TrendReq, group_name: str, config: dict) -> dict:
    """
    Holt Trenddaten für eine Keyword-Gruppe.
    
    Gibt zurück:
    - Zeitreihe der letzten 12 Monate (Wochenwerte)
    - Aktuelle Beliebtheit (0-100)
    - Ob der Trend gerade steigt oder fällt
    """
    keywords = config["keywords"][:5]  # Google erlaubt max. 5 gleichzeitig
    
    try:
        # Daten der letzten 12 Monate für NRW abrufen
        pytrends.build_payload(
            kw_list=keywords,
            cat=0,
            timeframe="today 12-m",   # letzte 12 Monate
            geo=GEO_REGION,
        )
        
        df_interest = pytrends.interest_over_time()
        
        # Kurze Pause – Google mag es nicht wenn man zu schnell fragt
        time.sleep(2)
        
        if df_interest.empty:
            return {"fehler": "Keine Daten von Google Trends erhalten"}
        
        # isPartial-Spalte entfernen (unvollständige aktuelle Woche)
        if "isPartial" in df_interest.columns:
            df_interest = df_interest.drop(columns=["isPartial"])
        
        # Durchschnittswert über alle Keywords der Gruppe
        df_interest["gesamt"] = df_interest.mean(axis=1)
        
        # Trend berechnen: Vergleich letzte 4 Wochen vs. 4 Wochen davor
        recent = df_interest["gesamt"].tail(4).mean()
        previous = df_interest["gesamt"].iloc[-8:-4].mean()
        trend_richtung = "steigend ↑" if recent > previous * 1.05 else \
                         "fallend ↓" if recent < previous * 0.95 else "stabil →"
        veraenderung = round(((recent - previous) / previous) * 100, 1) if previous > 0 else 0
        
        return {
            "gruppe": group_name,
            "keywords": keywords,
            "affiliate": config["affiliate"],
            "kategorie": config["kategorie"],
            "zeitreihe": df_interest["gesamt"].round(1).to_dict(),
            "aktueller_wert": round(recent, 1),
            "vorheriger_wert": round(previous, 1),
            "veraenderung_prozent": veraenderung,
            "trend_richtung": trend_richtung,
            "df_detail": df_interest,  # für Plots
        }
        
    except Exception as e:
        print(f"  ⚠ Fehler bei '{group_name}': {e}")
        return {"gruppe": group_name, "fehler": str(e)}


def collect_all_trends() -> list[dict]:
    """Holt Trends für alle Keyword-Gruppen nacheinander."""
    print(f"\n🔍 Starte Google Trends Abfrage für {GEO_REGION}...")
    pytrends = init_pytrends()
    results = []
    
    for group_name, config in KEYWORD_GROUPS.items():
        print(f"  → Abfrage: {group_name}...")
        result = fetch_trend_for_group(pytrends, group_name, config)
        results.append(result)
        time.sleep(3)  # Höfliche Pause zwischen Anfragen
    
    return results


# ── Affiliate-Chancen bewerten ────────────────────────────────────────────────

def score_affiliate_opportunities(results: list[dict]) -> pd.DataFrame:
    """
    Bewertet jede Keyword-Gruppe nach Affiliate-Potenzial.
    
    Scoring-Logik (für Laien erklärt):
    - Hoher aktueller Wert = viele Leute suchen das gerade → gut
    - Steigender Trend = Nachfrage wächst → sehr gut
    - Stabile Nachfrage = zuverlässig, nicht nur einmalig → gut
    """
    rows = []
    for r in results:
        if "fehler" in r:
            continue
        
        # Punkte-System (max. 100)
        score = 0
        score += min(r["aktueller_wert"], 40)           # Bis 40 Punkte für aktuellen Wert
        score += 20 if "steigend" in r["trend_richtung"] else \
                 10 if "stabil" in r["trend_richtung"] else 0  # Trend-Bonus
        score += min(max(r["veraenderung_prozent"], 0), 20)    # Wachstums-Bonus
        score += 10 if r["aktueller_wert"] > 30 else 0        # Mindest-Relevanz Bonus
        
        rows.append({
            "datum": today,
            "gruppe": r["gruppe"],
            "kategorie": r["kategorie"],
            "trend": r["trend_richtung"],
            "aktueller_wert": r["aktueller_wert"],
            "veraenderung_%": r["veraenderung_prozent"],
            "affiliate_score": round(score, 1),
            "empfohlene_partner": ", ".join(r["affiliate"]),
            "keywords": ", ".join(r["keywords"]),
        })
    
    if not rows:
        print("  ⚠ Keine Trend-Daten verfügbar – erstelle leere Fallback-Datei")
        df = pd.DataFrame(columns=[
            "datum","gruppe","kategorie","trend","aktueller_wert",
            "veraenderung_%","affiliate_score","empfohlene_partner","keywords"
        ])
        path = f"{OUTPUT_DIR}/affiliate_chancen_{today}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return df

    df = pd.DataFrame(rows).sort_values("affiliate_score", ascending=False)
    
    # Als CSV speichern
    path = f"{OUTPUT_DIR}/affiliate_chancen_{today}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n✓ Affiliate-Chancen gespeichert: {path}")
    return df


# ── Plots ─────────────────────────────────────────────────────────────────────

def plot_affiliate_scores(df: pd.DataFrame):
    """Balkendiagramm: Welche Kategorie hat das höchste Potenzial?"""
    if df.empty:
        return None

    fig, ax = plt.subplots(figsize=(11, 6))
    
    # Farben nach Score
    colors = ["#10B981" if s >= 60 else "#F59E0B" if s >= 40 else "#EF4444"
              for s in df["affiliate_score"]]
    
    bars = ax.barh(df["gruppe"], df["affiliate_score"], color=colors, edgecolor="white")
    
    # Wert-Labels rechts
    for bar, val in zip(bars, df["affiliate_score"]):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                f"{val:.0f}/100", va="center", fontsize=9, color="#1e293b")
    
    # Trend-Pfeile als Text
    for i, (_, row) in enumerate(df.iterrows()):
        ax.text(2, i, row["trend"], va="center", fontsize=9, color="white", fontweight="bold")
    
    ax.set_xlim(0, 110)
    ax.set_xlabel("Affiliate-Score (0–100)")
    ax.set_title(f"🏆 Affiliate-Potenzial nach Kategorie\nRegion: NRW | Stand: {today}",
                 fontsize=13, fontweight="bold")
    
    # Legende
    from matplotlib.patches import Patch
    legend = [Patch(color="#10B981", label="Hohes Potenzial (≥60)"),
              Patch(color="#F59E0B", label="Mittleres Potenzial (40–59)"),
              Patch(color="#EF4444", label="Geringes Potenzial (<40)")]
    ax.legend(handles=legend, loc="lower right", fontsize=9)
    
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()
    plt.tight_layout()
    
    path = f"{REPORT_DIR}/affiliate_scores.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ Plot gespeichert: {path}")
    return path


def plot_trend_zeitreihen(results: list[dict]):
    """Zeitreihen der letzten 12 Monate für alle Gruppen."""
    valid = [r for r in results if "df_detail" in r]
    if not valid:
        return None
    
    cols = 2
    rows = -(-len(valid) // cols)  # Aufrunden
    fig, axes = plt.subplots(rows, cols, figsize=(14, rows * 3.5))
    axes = axes.flatten()
    
    colors = ["#2563EB", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#F97316"]
    
    for i, result in enumerate(valid):
        ax = axes[i]
        df = result["df_detail"]
        
        for j, kw in enumerate(result["keywords"]):
            if kw in df.columns:
                ax.plot(df.index, df[kw], linewidth=1.5,
                        color=colors[j % len(colors)], alpha=0.7, label=kw)
        
        # Gesamt-Linie
        if "gesamt" in df.columns:
            ax.plot(df.index, df["gesamt"], linewidth=2.5,
                    color="#1e293b", linestyle="--", label="Ø Gesamt")
        
        ax.set_title(f"{result['gruppe']}\n{result['trend_richtung']}", 
                     fontsize=10, fontweight="bold")
        ax.set_ylabel("Interesse (0–100)")
        ax.legend(fontsize=7, loc="upper left")
        ax.grid(alpha=0.25)
        ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%b %y"))
        ax.tick_params(axis="x", rotation=30, labelsize=8)
    
    # Leere Subplots ausblenden
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)
    
    plt.suptitle(f"Google Trends – NRW – letzte 12 Monate | {today}",
                 fontsize=13, fontweight="bold", y=1.01)
    plt.tight_layout()
    
    path = f"{REPORT_DIR}/trends_zeitreihen.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ Plot gespeichert: {path}")
    return path


# ── Handlungsempfehlungen generieren ─────────────────────────────────────────

def generate_action_report(df_scores: pd.DataFrame, results: list[dict]) -> str:
    """
    Erstellt einen lesbaren Bericht mit konkreten Empfehlungen.
    Kein Python-Wissen nötig um ihn zu lesen!
    """
    lines = []
    lines.append(f"# 📊 Affiliate-Chancen Report – {today}")
    lines.append(f"Region: Nordrhein-Westfalen (Fokus: Castrop-Rauxel)\n")
    lines.append("=" * 60)
    
    lines.append("\n## 🏆 TOP CHANCEN DIESE WOCHE\n")
    
    top3 = df_scores.head(3)
    for rank, (_, row) in enumerate(top3.iterrows(), 1):
        emoji = ["🥇", "🥈", "🥉"][rank - 1]
        lines.append(f"{emoji} **{row['gruppe']}** (Score: {row['affiliate_score']:.0f}/100)")
        lines.append(f"   Trend: {row['trend']} | Veränderung: {row['veraenderung_%']:+.1f}%")
        lines.append(f"   Keywords: {row['keywords']}")
        lines.append(f"   Empfohlene Partner: {row['empfohlene_partner']}")
        lines.append("")
    
    lines.append("\n## 💡 KONKRETE ARTIKEL-IDEEN\n")
    
    # Saisonale Tipps basierend auf aktuellem Monat
    monat = datetime.now().month
    if monat in [3, 4, 5]:
        saison = "Frühling"
        tipps = ["Fahrrad fit machen für die Saison", "Garten anlegen – was du brauchst",
                 "Frühjahrsputz: Die besten Reinigungsmittel"]
    elif monat in [6, 7, 8]:
        saison = "Sommer"
        tipps = ["Die besten E-Bikes für Ruhrgebiet-Touren", "Camping im Ruhrgebiet",
                 "Heimtrainer für heiße Tage"]
    elif monat in [9, 10, 11]:
        saison = "Herbst"
        tipps = ["Herbst-Outdoor-Ausrüstung", "Heimwerken: Vorbereitung auf den Winter",
                 "Die besten Laufschuhe für schlechtes Wetter"]
    else:
        saison = "Winter"
        tipps = ["Weihnachtsgeschenke mit Mehrwert", "Heimtrainer-Vergleich",
                 "Winterjacken-Guide für NRW-Wetter"]
    
    lines.append(f"Saison: **{saison}** – passende Artikel:\n")
    for tipp in tipps:
        lines.append(f"  → {tipp}")
    
    lines.append("\n\n## 📋 ALLE KATEGORIEN IM ÜBERBLICK\n")
    lines.append(df_scores[["gruppe", "trend", "affiliate_score", "empfohlene_partner"]]
                 .to_string(index=False))
    
    lines.append("\n\n## 🛠 NÄCHSTE SCHRITTE\n")
    lines.append("1. Bei AWIN oder Amazon PartnerNet anmelden (kostenlos)")
    lines.append("2. Artikel zur Top-Kategorie schreiben")
    lines.append("3. Affiliate-Links einbauen")
    lines.append("4. Artikel für lokale Suchen optimieren (z.B. 'Fahrrad Castrop-Rauxel')")
    lines.append("5. Diesen Report nächste Woche wiederholen & Trends vergleichen")
    
    report_text = "\n".join(lines)
    
    path = f"{REPORT_DIR}/affiliate_report_{today}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"✓ Report gespeichert: {path}")
    return path


# ── HTML Erweiterung für bestehendes Dashboard ───────────────────────────────

def generate_trends_html(df_scores: pd.DataFrame) -> str:
    """Gibt HTML-Snippet zurück das ins Haupt-Dashboard eingebaut werden kann."""
    rows_html = ""
    for _, row in df_scores.iterrows():
        score = row["affiliate_score"]
        color = "#10B981" if score >= 60 else "#F59E0B" if score >= 40 else "#EF4444"
        rows_html += f"""
        <tr>
          <td><strong>{row['gruppe']}</strong></td>
          <td>{row['trend']}</td>
          <td>{row['veraenderung_%']:+.1f}%</td>
          <td>
            <div style="background:#f1f5f9;border-radius:4px;height:12px;width:100%">
              <div style="background:{color};width:{min(score,100)}%;height:12px;
                          border-radius:4px"></div>
            </div>
            <span style="font-size:0.8rem;color:#64748b">{score:.0f}/100</span>
          </td>
          <td style="font-size:0.8rem;color:#64748b">{row['empfohlene_partner']}</td>
        </tr>"""
    
    return f"""
    <div class="section">
      <h2>📈 Affiliate-Chancen (Google Trends NRW)</h2>
      <table>
        <thead>
          <tr><th>Kategorie</th><th>Trend</th><th>Veränderung</th>
              <th>Score</th><th>Partner</th></tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
      <p style="font-size:0.8rem;color:#94a3b8;margin-top:0.5rem">
        Quelle: Google Trends (NRW) · Stand: {today}
      </p>
    </div>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  Google Trends & Affiliate-Analyse – {today}")
    print(f"  Region: Nordrhein-Westfalen")
    print(f"{'='*55}")
    
    # 1. Trends abrufen
    results = collect_all_trends()
    
    # 2. Affiliate-Score berechnen
    df_scores = score_affiliate_opportunities(results)
    
    # 3. Plots erstellen
    plot_affiliate_scores(df_scores)
    plot_trend_zeitreihen(results)
    
    # 4. Lesbaren Report generieren
    generate_action_report(df_scores, results)
    
    # 5. Übersicht in der Konsole
    print(f"\n{'='*55}")
    print("  🏆 TOP AFFILIATE-CHANCEN HEUTE")
    print(f"{'='*55}")
    for _, row in df_scores.head(3).iterrows():
        print(f"  {row['gruppe']:<25} Score: {row['affiliate_score']:>5.1f}  {row['trend']}")
    print(f"\n  → Vollständiger Report: reports/affiliate_report_{today}.md")
    print(f"  → Plots: reports/affiliate_scores.png")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
