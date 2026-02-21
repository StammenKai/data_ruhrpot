"""
KI-gestützter SEO Content Generator & WordPress Publisher
===========================================================
Workflow:
1. Liest Trend-Daten aus trends_affiliate.py
2. Fragt Claude API für SEO-Artikel an
3. Veröffentlicht automatisch in WordPress
4. Protokolliert alles

Voraussetzungen:
    pip install requests pandas python-dotenv anthropic

Konfiguration:
    .env Datei anlegen (siehe unten)
"""

import os
import json
import time
import requests
import pandas as pd
import anthropic
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # Lädt .env Datei

# ── Konfiguration (in .env Datei eintragen!) ──────────────────────────────────
#
#   ANTHROPIC_API_KEY=sk-ant-...          ← von console.anthropic.com
#   WP_URL=https://deine-domain.de        ← deine WordPress URL
#   WP_USER=admin                         ← WordPress Benutzername
#   WP_PASSWORD=dein-app-passwort         ← WordPress App-Passwort (nicht Login-PW!)
#
# WordPress App-Passwort erstellen:
#   WordPress Admin → Benutzer → Profil → Anwendungspasswörter → Neu erstellen

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
WP_URL = os.getenv("WP_URL", "https://deine-domain.de")
WP_USER = os.getenv("WP_USER", "admin")
WP_PASSWORD = os.getenv("WP_PASSWORD", "")

OUTPUT_DIR = "output"
REPORT_DIR = "reports"
LOG_FILE = "content_log.json"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

today = date.today().isoformat()
REGION = "Ruhrgebiet / Castrop-Rauxel"


# ── Affiliate-Links Datenbank ─────────────────────────────────────────────────
#
# Trage hier deine echten Affiliate-Links ein sobald du angemeldet bist.
# Format: "Partnername": "dein-affiliate-link"

AFFILIATE_LINKS = {
    "Fahrrad & Outdoor": {
        "Decathlon": "https://www.decathlon.de/?ref=DEIN-CODE",
        "Amazon Fahrrad": "https://amzn.to/DEIN-CODE",
        "Fahrrad.de": "https://www.fahrrad.de/?ref=DEIN-CODE",
        "Bergfreunde": "https://www.bergfreunde.de/?ref=DEIN-CODE",
    },
    "Heimwerken & Garten": {
        "OBI": "https://www.obi.de/?ref=DEIN-CODE",
        "Hornbach": "https://www.hornbach.de/?ref=DEIN-CODE",
        "Amazon Heimwerken": "https://amzn.to/DEIN-CODE",
    },
    "Elektronik & Technik": {
        "Amazon Elektronik": "https://amzn.to/DEIN-CODE",
        "MediaMarkt": "https://www.mediamarkt.de/?ref=DEIN-CODE",
        "Alternate": "https://www.alternate.de/?ref=DEIN-CODE",
    },
    "Gesundheit & Fitness": {
        "Myprotein": "https://www.myprotein.com/?ref=DEIN-CODE",
        "Amazon Sport": "https://amzn.to/DEIN-CODE",
        "SportScheck": "https://www.sportscheck.com/?ref=DEIN-CODE",
    },
    "Familie & Kinder": {
        "Amazon Familie": "https://amzn.to/DEIN-CODE",
        "myToys": "https://www.mytoys.de/?ref=DEIN-CODE",
    },
    "Mode & Lifestyle": {
        "Zalando": "https://www.zalando.de/?ref=DEIN-CODE",
        "AboutYou": "https://www.aboutyou.de/?ref=DEIN-CODE",
    },
}


# ── Schritt 1: Top-Thema aus Trend-Daten laden ───────────────────────────────

def load_top_opportunity() -> dict:
    """
    Liest die beste Affiliate-Chance – kombiniert aus:
    1. Google Trends Analyse (trends_affiliate.py)
    2. Ads Intelligence Keywords (ads_intelligence.py)
    → Zusammen ergibt das die präzisesten SEO-Keywords
    """
    import glob

    ads_keywords  = ""
    artikel_titel = ""
    primary_kw    = ""
    secondary_kws = ""

    # Ads Intelligence Keywords (höchste Priorität)
    ads_kw_files = sorted(glob.glob(f"{OUTPUT_DIR}/seo_keywords_*.csv"))
    if ads_kw_files:
        df_kw = pd.read_csv(ads_kw_files[-1])
        top_kws = df_kw.sort_values("prioritaet", ascending=False).head(5)
        ads_keywords = ", ".join(top_kws["keyword"].tolist())
        print(f"✓ Ads-Keywords geladen: {ads_keywords[:80]}...")

    # KI-generierte Artikel-Ideen
    ideen_files = sorted(glob.glob(f"{OUTPUT_DIR}/artikel_ideen_*.csv"))
    if ideen_files:
        df_art = pd.read_csv(ideen_files[-1])
        if not df_art.empty:
            best         = df_art.iloc[0]
            artikel_titel = best.get("titel", "")
            primary_kw    = best.get("primary_keyword", "")
            secondary_kws = best.get("secondary_keywords", "")
            print(f"✓ Artikel-Idee: {artikel_titel[:60]}")

    # Trend-Daten als Ergänzung
    trend_gruppe = "Fahrrad & Outdoor"
    trend_score  = 75.0
    trend_files  = sorted(glob.glob(f"{OUTPUT_DIR}/affiliate_chancen_*.csv"))
    if trend_files:
        df_t = pd.read_csv(trend_files[-1])
        top  = df_t.sort_values("affiliate_score", ascending=False).iloc[0]
        trend_gruppe = top["gruppe"]
        trend_score  = float(top["affiliate_score"])

    return {
        "gruppe":                trend_gruppe,
        "affiliate_score":       trend_score,
        "trend":                 "steigend ↑",
        "ads_keywords":          ads_keywords,
        "vorgeschlagener_titel": artikel_titel,
        "primary_keyword":       primary_kw,
        "secondary_keywords":    secondary_kws,
        "keywords":              ads_keywords or "Fahrrad kaufen, E-Bike, Camping",
    }


# ── Schritt 2: KI-Artikel generieren ─────────────────────────────────────────

def build_seo_prompt(opportunity: dict) -> str:
    """Baut den Prompt für Claude – jetzt mit Ads-Intelligence Keywords."""
    gruppe        = opportunity["gruppe"]
    primary_kw    = opportunity.get("primary_keyword") or opportunity.get("keywords", "")
    secondary_kws = opportunity.get("secondary_keywords", "")
    ads_keywords  = opportunity.get("ads_keywords", "")
    vorschlag     = opportunity.get("vorgeschlagener_titel", "")
    affiliate_links = AFFILIATE_LINKS.get(gruppe, {})
    links_text = "\n".join([f"- {name}: {url}" for name, url in affiliate_links.items()])

    return f"""Du bist ein erfahrener SEO-Texter für den Affiliate-Blog "RuhrFinds" (ruhrfinds.de).
Zielgruppe: Menschen im {REGION} die online kaufen möchten.

THEMA / NISCHE: {gruppe}

PRIMARY KEYWORD (muss im Titel, in H1 und 3-4x im Text vorkommen):
{primary_kw}

SECONDARY KEYWORDS (natürlich verteilt, je 1-2x):
{secondary_kws}

KEYWORDS AUS ADS-ANALYSE (das zahlen Konkurrenten gerade bei Google – bewiesene Nachfrage!):
{ads_keywords}

{'VORGESCHLAGENER TITEL: ' + vorschlag if vorschlag else ''}

AFFILIATE-PARTNER (Links natürlich einbauen):
{links_text}

ARTIKEL-ANFORDERUNGEN:
- Länge: 1.500–2.000 Wörter
- Ton: ehrlich, hilfreich, Pott-typisch direkt – kein Marketing-Sprech
- Lokaler Bezug: Ruhrgebiet / NRW wo sinnvoll
- Struktur: H1 mit Primary Keyword, H2 Abschnitte, kurze Absätze
- Affiliate-Links: 3–5 Links, nur wo sie echten Mehrwert bieten
- Format: HTML für WordPress
- rel="nofollow sponsored" auf alle Affiliate-Links

SEO-TECHNISCH:
- Primary Keyword in: Titel (H1), ersten 100 Wörtern, mind. 1 H2, letztem Absatz
- Secondary Keywords natürlich verteilt – KEIN Keyword Stuffing
- Ads-Keywords aus der Analyse als natürliche Phrasen einbauen
- Meta-Description am Ende: <!-- META: max. 155 Zeichen mit Primary Keyword -->
- SEO-Titel: <!-- TITLE: max. 60 Zeichen -->

Schreibe jetzt den vollständigen Artikel:"""


def generate_article(opportunity: dict) -> dict:
    """Ruft Claude API auf und generiert den SEO-Artikel."""
    if not ANTHROPIC_API_KEY:
        print("⚠ Kein ANTHROPIC_API_KEY – generiere Platzhalter-Artikel")
        return _placeholder_article(opportunity)

    print(f"🤖 Generiere Artikel für: {opportunity['gruppe']}...")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = build_seo_prompt(opportunity)

    try:
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        content = message.content[0].text

        # Meta-Daten aus HTML-Kommentaren extrahieren
        meta = _extract_meta(content)

        article = {
            "datum": today,
            "gruppe": opportunity["gruppe"],
            "titel": meta.get("title", f"{opportunity['gruppe']} – Tipps für das Ruhrgebiet"),
            "meta_description": meta.get("meta", ""),
            "content_html": content,
            "wortanzahl": len(content.split()),
            "tokens_verbraucht": message.usage.output_tokens,
            "status": "generiert",
        }

        print(f"✓ Artikel generiert: {article['wortanzahl']} Wörter")
        return article

    except Exception as e:
        print(f"✗ Claude API Fehler: {e}")
        return _placeholder_article(opportunity)


def _extract_meta(html_content: str) -> dict:
    """Extrahiert Titel und Meta-Description aus HTML-Kommentaren."""
    import re
    meta = {}
    title_match = re.search(r'<!--\s*TITLE:\s*(.+?)\s*-->', html_content)
    meta_match = re.search(r'<!--\s*META:\s*(.+?)\s*-->', html_content)
    if title_match:
        meta["title"] = title_match.group(1).strip()
    if meta_match:
        meta["meta"] = meta_match.group(1).strip()
    return meta


def _placeholder_article(opportunity: dict) -> dict:
    """Platzhalter wenn kein API-Key vorhanden."""
    gruppe = opportunity["gruppe"]
    return {
        "datum": today,
        "gruppe": gruppe,
        "titel": f"{gruppe} – Tipps & Empfehlungen für das Ruhrgebiet",
        "meta_description": f"Die besten Tipps zu {gruppe} für Menschen im Ruhrgebiet. Jetzt informieren!",
        "content_html": f"""<h1>{gruppe} im Ruhrgebiet – Dein Guide</h1>
<p>Dieser Artikel wurde automatisch vorbereitet. 
Füge deinen ANTHROPIC_API_KEY in die .env Datei ein um echte KI-Artikel zu generieren.</p>
<p>Thema: <strong>{gruppe}</strong><br>
Keywords: {opportunity.get('keywords', '')}<br>
Trend: {opportunity.get('trend', '')}</p>""",
        "wortanzahl": 0,
        "tokens_verbraucht": 0,
        "status": "platzhalter",
    }


# ── Schritt 3: In WordPress veröffentlichen ───────────────────────────────────

def publish_to_wordpress(article: dict, als_entwurf: bool = True) -> dict:
    """
    Veröffentlicht den Artikel in WordPress via REST API.

    als_entwurf=True  → Artikel landet als Entwurf (empfohlen zum Start!)
    als_entwurf=False → Artikel wird sofort veröffentlicht
    """
    if not WP_PASSWORD or WP_URL == "https://deine-domain.de":
        print("⚠ WordPress nicht konfiguriert – speichere lokal als HTML")
        return _save_locally(article)

    api_url = f"{WP_URL}/wp-json/wp/v2/posts"
    status = "draft" if als_entwurf else "publish"

    payload = {
        "title": article["titel"],
        "content": article["content_html"],
        "status": status,
        "excerpt": article["meta_description"],
        "meta": {
            "_yoast_wpseo_metadesc": article["meta_description"],  # Yoast SEO Plugin
            "_yoast_wpseo_title": article["titel"],
        },
        "categories": [],   # Optional: WordPress Kategorie-ID eintragen
        "tags": [],         # Optional: Tag-IDs eintragen
    }

    try:
        resp = requests.post(
            api_url,
            json=payload,
            auth=(WP_USER, WP_PASSWORD),
            timeout=30,
        )
        resp.raise_for_status()
        wp_data = resp.json()

        result = {
            "wp_id": wp_data.get("id"),
            "wp_url": wp_data.get("link"),
            "wp_status": wp_data.get("status"),
            "datum": today,
        }
        print(f"✓ WordPress: Artikel veröffentlicht als '{status}'")
        print(f"  URL: {result['wp_url']}")
        return result

    except requests.exceptions.ConnectionError:
        print("✗ WordPress nicht erreichbar – speichere lokal")
        return _save_locally(article)
    except Exception as e:
        print(f"✗ WordPress Fehler: {e}")
        return _save_locally(article)


def _save_locally(article: dict) -> dict:
    """Fallback: Speichert Artikel als HTML-Datei."""
    filename = f"{REPORT_DIR}/artikel_{today}_{article['gruppe'].replace(' ', '_')}.html"

    full_html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="description" content="{article['meta_description']}">
<title>{article['titel']}</title>
<style>
  body {{ max-width: 800px; margin: 2rem auto; font-family: Georgia, serif;
          line-height: 1.7; color: #1e293b; padding: 0 1rem; }}
  h1 {{ color: #1e3a5f; }}
  h2 {{ color: #2563EB; margin-top: 2rem; }}
  a {{ color: #2563EB; }}
  .meta {{ background: #f1f5f9; padding: 1rem; border-radius: 8px;
           font-size: 0.85rem; color: #64748b; margin-bottom: 2rem; }}
</style>
</head>
<body>
<div class="meta">
  Generiert: {today} | Thema: {article['gruppe']} | 
  Status: {article['status']} | Wörter: {article['wortanzahl']}
</div>
{article['content_html']}
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_html)

    print(f"✓ Lokal gespeichert: {filename}")
    return {"lokal": filename, "wp_status": "lokal_gespeichert"}


# ── Schritt 4: Protokoll führen ───────────────────────────────────────────────

def log_article(article: dict, wp_result: dict):
    """Führt Buch über alle veröffentlichten Artikel."""
    log = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)

    eintrag = {
        "datum": today,
        "titel": article["titel"],
        "gruppe": article["gruppe"],
        "wortanzahl": article["wortanzahl"],
        "tokens": article["tokens_verbraucht"],
        "wp_id": wp_result.get("wp_id"),
        "wp_url": wp_result.get("wp_url"),
        "wp_status": wp_result.get("wp_status"),
        "lokal": wp_result.get("lokal"),
    }
    log.append(eintrag)

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"✓ Protokoll aktualisiert: {LOG_FILE} ({len(log)} Artikel gesamt)")
    return log


def print_log_summary(log: list):
    """Zeigt eine Übersicht aller bisherigen Artikel."""
    if not log:
        return
    print(f"\n{'='*55}")
    print(f"  📚 ARTIKEL-PROTOKOLL ({len(log)} gesamt)")
    print(f"{'='*55}")
    for e in log[-5:]:  # Letzte 5 anzeigen
        status = e.get('wp_status', '?')
        print(f"  {e['datum']}  {e['titel'][:40]:<40}  [{status}]")
    print(f"{'='*55}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  🤖 KI Content Generator – {today}")
    print(f"  Region: {REGION}")
    print(f"{'='*55}\n")

    # 1. Bestes Thema laden
    opportunity = load_top_opportunity()

    # 2. KI-Artikel generieren
    article = generate_article(opportunity)

    # 3. In WordPress veröffentlichen (als Entwurf – sicher!)
    #    Ändere als_entwurf=False wenn du automatisch veröffentlichen willst
    wp_result = publish_to_wordpress(article, als_entwurf=True)

    # 4. Protokollieren
    log = log_article(article, wp_result)
    print_log_summary(log)

    print(f"✅ Fertig! Artikel: '{article['titel']}'")
    if wp_result.get("wp_url"):
        print(f"   → WordPress: {wp_result['wp_url']}")
    if wp_result.get("lokal"):
        print(f"   → Lokale Datei: {wp_result['lokal']}")


if __name__ == "__main__":
    main()
