"""
Google Ads Intelligence & SEO Keyword Extraktor
=================================================
Workflow:
1. Scrapt Google Ads Transparenz-Center nach Wettbewerber-Anzeigen in NRW
2. Extrahiert Keywords & Botschaften aus Anzeigentexten
3. Bewertet SEO-Potenzial (bezahlte Nachfrage = bewiesene Nachfrage)
4. Füttert Claude API mit diesen Daten für optimierten Content
5. Speichert alles im Dashboard

Voraussetzungen:
    pip install requests beautifulsoup4 pandas anthropic python-dotenv selenium

Warum Selenium?
    Das Ads Transparenz-Center lädt Daten via JavaScript – ein normaler
    requests.get() würde nur leeres HTML sehen. Selenium öffnet einen
    echten Browser im Hintergrund und wartet bis die Daten geladen sind.
"""

import os
import json
import time
import re
import pandas as pd
import anthropic
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()

# ── Konfiguration ─────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OUTPUT_DIR  = "output"
REPORT_DIR  = "reports"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)
today = date.today().isoformat()

# Suchbegriffe die wir im Ads-Center analysieren wollen
# → Passe diese an deine Nischen an!
SEARCH_QUERIES = [
    "E-Bike kaufen",
    "Fahrrad Ruhrgebiet",
    "Heimtrainer kaufen",
    "Gartengeräte günstig",
    "Laptop kaufen NRW",
    "Laufschuhe kaufen",
    "Werkzeug Set",
    "Kinderwagen kaufen",
]

# Bekannte Affiliate-Konkurrenten / Shops die wir beobachten
TARGET_ADVERTISERS = [
    "decathlon.de",
    "fahrrad.de",
    "bike-discount.de",
    "obi.de",
    "hornbach.de",
    "alternate.de",
    "mediamarkt.de",
    "amazon.de",
    "zalando.de",
    "mytoys.de",
]

REGION = "DE-NW"  # Nordrhein-Westfalen


# ── Methode 1: Ads Transparenz-Center (Selenium) ──────────────────────────────

def scrape_ads_transparency(query: str) -> list[dict]:
    """
    Öffnet das Google Ads Transparenz-Center im Hintergrund-Browser
    und extrahiert Anzeigen für einen Suchbegriff.

    Gibt zurück: Liste von Anzeigen mit Text, Advertiser, URL
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        opts = Options()
        opts.add_argument("--headless")           # Kein sichtbares Fenster
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--lang=de-DE")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")

        driver = webdriver.Chrome(options=opts)

        url = f"https://adstransparency.google.com/?region={REGION}&query={query.replace(' ', '+')}"
        driver.get(url)

        # Warten bis Anzeigen geladen sind
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "creative-preview, .advertiser-name, [class*='ad-card']"))
        )
        time.sleep(2)  # Extra Wartezeit für dynamische Inhalte

        ads = []

        # Verschiedene Selektoren versuchen (Google ändert die Klassen gelegentlich)
        ad_containers = (
            driver.find_elements(By.CSS_SELECTOR, "creative-preview") or
            driver.find_elements(By.CSS_SELECTOR, "[data-creative-id]") or
            driver.find_elements(By.CSS_SELECTOR, ".ad-creative-container")
        )

        for container in ad_containers[:20]:  # Max 20 Anzeigen pro Query
            try:
                text = container.text.strip()
                if len(text) < 10:
                    continue

                # Advertiser Name extrahieren
                advertiser = ""
                for selector in [".advertiser-name", "[class*='advertiser']", "span[class*='name']"]:
                    try:
                        el = container.find_element(By.CSS_SELECTOR, selector)
                        advertiser = el.text.strip()
                        break
                    except:
                        continue

                ads.append({
                    "datum": today,
                    "query": query,
                    "advertiser": advertiser or "unbekannt",
                    "anzeigen_text": text[:500],
                    "region": REGION,
                    "quelle": "ads_transparency",
                })
            except Exception:
                continue

        driver.quit()
        print(f"  ✓ Selenium [{query}]: {len(ads)} Anzeigen")
        return ads

    except ImportError:
        print("  ⚠ Selenium nicht installiert – nutze Fallback-Methode")
        return []
    except Exception as e:
        print(f"  ⚠ Selenium Fehler [{query}]: {e}")
        return []


# ── Methode 2: SpyFu Public Data (Fallback) ──────────────────────────────────

def fetch_spyfu_keywords(domain: str) -> list[dict]:
    """
    Holt öffentliche Keyword-Daten von SpyFu für einen Advertiser.
    SpyFu zeigt Top-Keywords kostenlos ohne Login.
    """
    import requests
    from bs4 import BeautifulSoup

    results = []
    url = f"https://www.spyfu.com/overview/domain?query={domain}"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept-Language": "de-DE,de;q=0.9",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        # SpyFu zeigt Top-Keywords in einer Tabelle
        keyword_elements = (
            soup.select(".keyword-cell") or
            soup.select("[class*='keyword']") or
            soup.select("td.kw")
        )

        for el in keyword_elements[:15]:
            kw = el.get_text(strip=True)
            if kw and len(kw) > 2:
                results.append({
                    "datum": today,
                    "domain": domain,
                    "keyword": kw,
                    "quelle": "spyfu",
                })

        print(f"  ✓ SpyFu [{domain}]: {len(results)} Keywords")
    except Exception as e:
        print(f"  ⚠ SpyFu Fehler [{domain}]: {e}")

    return results


# ── Methode 3: Google Suggest als Keyword-Goldmine ────────────────────────────

def fetch_google_suggest(seed_keyword: str) -> list[str]:
    """
    Google Suggest zeigt was Menschen WIRKLICH suchen.
    Das ist kostenlos, offiziell und sehr wertvoll.

    Beispiel: "E-Bike" → ["E-Bike kaufen NRW", "E-Bike Test 2026",
                           "E-Bike günstig Ruhrgebiet", ...]
    """
    import requests

    suggestions = []
    prefixes = ["", "kaufen ", "test ", "vergleich ", "günstig ", "beste "]

    for prefix in prefixes:
        query = f"{prefix}{seed_keyword}"
        url = "https://suggestqueries.google.com/complete/search"
        params = {
            "client": "firefox",
            "q": query,
            "hl": "de",
            "gl": "de",
        }
        try:
            resp = requests.get(url, params=params, timeout=8)
            data = resp.json()
            if isinstance(data, list) and len(data) > 1:
                suggestions.extend(data[1])
            time.sleep(0.5)
        except Exception:
            continue

    # Deduplizieren und filtern
    seen = set()
    clean = []
    for s in suggestions:
        s = str(s).strip().lower()
        if s and s not in seen and len(s) > 4:
            seen.add(s)
            clean.append(s)

    print(f"  ✓ Google Suggest [{seed_keyword}]: {len(clean)} Vorschläge")
    return clean[:30]


# ── Methode 4: SERP Analyse (organische Konkurrenz) ──────────────────────────

def analyze_serp_competition(keyword: str) -> dict:
    """
    Analysiert die organischen Suchergebnisse für ein Keyword.
    Zeigt wie schwer es ist zu ranken und wer bereits oben steht.
    """
    import requests
    from bs4 import BeautifulSoup

    url = "https://www.google.de/search"
    params = {"q": keyword, "hl": "de", "gl": "de", "num": 10}
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept-Language": "de-DE,de;q=0.9",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        results = []
        for r in soup.select("div.g")[:10]:
            title_el = r.select_one("h3")
            url_el   = r.select_one("cite")
            if title_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "url":   url_el.get_text(strip=True) if url_el else "",
                })

        # Affiliate-Seiten unter Top 10?
        affiliate_count = sum(
            1 for r in results
            if any(x in r["url"] for x in ["affiliate", "test", "vergleich", "empfehlung", "bestenliste"])
        )

        return {
            "keyword": keyword,
            "top_results": results,
            "affiliate_in_top10": affiliate_count,
            "schwierigkeit": "niedrig" if affiliate_count >= 3 else "mittel" if affiliate_count >= 1 else "hoch",
        }
    except Exception as e:
        return {"keyword": keyword, "fehler": str(e)}


# ── Daten zusammenführen & bewerten ──────────────────────────────────────────

def collect_all_ads_data() -> dict:
    """Hauptfunktion: Sammelt alle verfügbaren Wettbewerber-Daten."""

    print(f"\n{'='*55}")
    print(f"  🔍 Ads Intelligence Sammlung – {today}")
    print(f"{'='*55}\n")

    all_ads        = []
    all_keywords   = []
    all_suggestions = {}
    serp_data      = []

    # 1. Ads Transparenz-Center
    print("📺 Schritt 1: Google Ads Transparenz-Center...")
    for query in SEARCH_QUERIES[:5]:  # Erste 5 um höflich zu bleiben
        ads = scrape_ads_transparency(query)
        all_ads.extend(ads)
        time.sleep(3)

    # 2. Google Suggest für alle Queries
    print("\n💡 Schritt 2: Google Suggest...")
    for query in SEARCH_QUERIES:
        suggestions = fetch_google_suggest(query)
        all_suggestions[query] = suggestions
        time.sleep(1)

    # 3. SERP-Analyse für Top-Keywords
    print("\n🔎 Schritt 3: SERP-Konkurrenz-Analyse...")
    priority_keywords = SEARCH_QUERIES[:4]
    for kw in priority_keywords:
        serp = analyze_serp_competition(kw)
        serp_data.append(serp)
        time.sleep(2)

    # 4. SpyFu für wichtigste Konkurrenten
    print("\n🕵️  Schritt 4: SpyFu Keyword-Daten...")
    for domain in TARGET_ADVERTISERS[:4]:
        kws = fetch_spyfu_keywords(domain)
        all_keywords.extend(kws)
        time.sleep(2)

    return {
        "datum": today,
        "ads": all_ads,
        "suggestions": all_suggestions,
        "serp": serp_data,
        "competitor_keywords": all_keywords,
    }


# ── KI-Keyword-Analyse ────────────────────────────────────────────────────────

def ai_analyze_keywords(raw_data: dict) -> dict:
    """
    Claude analysiert alle gesammelten Daten und erstellt:
    - Priorisierte Keyword-Liste für RuhrFinds
    - SEO-Strategie basierend auf Lücken der Konkurrenz
    - Konkrete Artikel-Ideen mit eingebetteten Keywords
    """
    if not ANTHROPIC_API_KEY:
        print("⚠ Kein API-Key – überspringe KI-Analyse")
        return _demo_analysis()

    print("\n🤖 KI-Analyse startet...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Daten komprimieren für den Prompt
    ads_summary = "\n".join([
        f"- Advertiser: {a['advertiser']} | Query: {a['query']} | Text: {a['anzeigen_text'][:100]}"
        for a in raw_data["ads"][:20]
    ]) or "Keine Ads-Daten verfügbar"

    suggest_summary = "\n".join([
        f"- '{query}': {', '.join(sugs[:8])}"
        for query, sugs in list(raw_data["suggestions"].items())[:6]
    ])

    serp_summary = "\n".join([
        f"- '{s['keyword']}': Schwierigkeit={s.get('schwierigkeit','?')}, "
        f"Affiliate in Top10={s.get('affiliate_in_top10',0)}"
        for s in raw_data["serp"]
    ])

    prompt = f"""Du bist ein erfahrener SEO-Stratege für den Affiliate-Blog "RuhrFinds" (ruhrfinds.de).
Der Blog richtet sich an Menschen im Ruhrgebiet / NRW und monetarisiert über Affiliate-Links.

Ich habe folgende Wettbewerber-Daten gesammelt:

## Aktive Google Ads (was Konkurrenten gerade bewerben & bezahlen):
{ads_summary}

## Google Suggest (was Menschen wirklich suchen):
{suggest_summary}

## SERP-Konkurrenz-Analyse:
{serp_summary}

## Deine Aufgabe:

1. **TOP 10 KEYWORDS** für RuhrFinds identifizieren
   - Hohe Suchnachfrage (durch Ads-Ausgaben der Konkurrenz bewiesen)
   - Regionaler Bezug möglich (Ruhrgebiet, NRW, Castrop-Rauxel)
   - Affiliate-Potenzial vorhanden
   - Erreichbar für einen neuen Blog (nicht zu kompetitiv)

2. **CONTENT-LÜCKEN** finden
   - Welche Keywords werden von Konkurrenz mit Anzeigen bedient aber NICHT organisch abgedeckt?
   - Das sind die besten Rankingchancen für RuhrFinds

3. **5 ARTIKEL-IDEEN** mit:
   - Exaktem SEO-Titel (H1)
   - Primary Keyword
   - 3-5 Secondary Keywords (LSI)
   - Kurze Content-Strategie (was macht den Artikel besser als Konkurrenz?)
   - Passende Affiliate-Partner

4. **LOKALE SEO-CHANCEN**
   - Keyword-Varianten mit "Ruhrgebiet", "NRW", "Castrop-Rauxel" etc.
   - Diese ranken schneller weil kaum Konkurrenz

Antworte NUR als valides JSON in diesem Format:
{{
  "top_keywords": [
    {{"keyword": "...", "prioritaet": 1-10, "suchvolumen_schaetzung": "hoch/mittel/niedrig",
      "affiliate_potenzial": "hoch/mittel/niedrig", "begruendung": "..."}}
  ],
  "content_luecken": [
    {{"keyword": "...", "opportunity": "Warum ist das eine Lücke?"}}
  ],
  "artikel_ideen": [
    {{
      "titel": "...", "primary_keyword": "...",
      "secondary_keywords": ["...", "..."],
      "content_strategie": "...",
      "affiliate_partner": ["..."],
      "geschaetzte_wortanzahl": 1500
    }}
  ],
  "lokale_keywords": ["...", "..."],
  "meta": {{
    "analysiert_am": "{today}",
    "daten_qualitaet": "hoch/mittel/niedrig",
    "empfehlung": "..."
  }}
}}"""

    try:
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text
        # JSON aus der Antwort extrahieren
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
            print(f"  ✓ KI-Analyse: {len(analysis.get('top_keywords', []))} Keywords, "
                  f"{len(analysis.get('artikel_ideen', []))} Artikel-Ideen")
            return analysis
        else:
            print("  ⚠ JSON-Parsing fehlgeschlagen")
            return _demo_analysis()

    except Exception as e:
        print(f"  ✗ KI-Fehler: {e}")
        return _demo_analysis()


def _demo_analysis() -> dict:
    """Demo-Daten wenn kein API-Key vorhanden."""
    return {
        "top_keywords": [
            {"keyword": "E-Bike kaufen Ruhrgebiet", "prioritaet": 9,
             "suchvolumen_schaetzung": "mittel", "affiliate_potenzial": "hoch",
             "begruendung": "Konkurrenz zahlt für 'E-Bike kaufen' – lokale Variante kaum besetzt"},
            {"keyword": "Fahrrad Werkzeug Set Test", "prioritaet": 8,
             "suchvolumen_schaetzung": "mittel", "affiliate_potenzial": "hoch",
             "begruendung": "Hohe Ads-Dichte zeigt Kaufabsicht"},
            {"keyword": "Heimtrainer unter 500 Euro", "prioritaet": 7,
             "suchvolumen_schaetzung": "hoch", "affiliate_potenzial": "hoch",
             "begruendung": "Preisbasierte Keywords konvertieren sehr gut"},
        ],
        "content_luecken": [
            {"keyword": "E-Bike Ruhrgebiet Tour", "opportunity": "Ads vorhanden, kein organischer Artikel"},
            {"keyword": "Gartengeräte Test NRW", "opportunity": "Lokaler Bezug fehlt komplett im SERP"},
        ],
        "artikel_ideen": [
            {
                "titel": "Die 7 besten E-Bikes für Touren im Ruhrgebiet (2026)",
                "primary_keyword": "E-Bike kaufen Ruhrgebiet",
                "secondary_keywords": ["E-Bike Test 2026", "E-Bike günstig NRW", "Pedelec Ruhrgebiet", "bestes E-Bike Empfehlung"],
                "content_strategie": "Lokale Touren-Empfehlungen einbauen, konkrete Modelle mit Preisen",
                "affiliate_partner": ["Decathlon", "Fahrrad.de", "Amazon"],
                "geschaetzte_wortanzahl": 1800,
            },
            {
                "titel": "Heimtrainer Test: Die besten Geräte unter 500€ im Vergleich",
                "primary_keyword": "Heimtrainer unter 500 Euro",
                "secondary_keywords": ["Heimtrainer Test", "bester Heimtrainer", "Fahrradergometer kaufen"],
                "content_strategie": "Vergleichstabelle, Pro/Contra je Gerät, klarer Kaufempfehlung",
                "affiliate_partner": ["Amazon", "SportScheck"],
                "geschaetzte_wortanzahl": 2000,
            },
        ],
        "lokale_keywords": [
            "E-Bike kaufen Castrop-Rauxel", "Fahrrad Reparatur Ruhrgebiet",
            "Sportgeschäft NRW online", "Gartenmarkt Ruhrgebiet",
        ],
        "meta": {
            "analysiert_am": today,
            "daten_qualitaet": "demo",
            "empfehlung": "API-Key eintragen für echte Analyse",
        }
    }


# ── Alles speichern ───────────────────────────────────────────────────────────

def save_results(raw_data: dict, analysis: dict):
    """Speichert alle Ergebnisse für Dashboard & content generator."""

    # Rohdaten
    path_raw = f"{OUTPUT_DIR}/ads_raw_{today}.json"
    with open(path_raw, "w", encoding="utf-8") as f:
        # df_detail ist nicht JSON-serialisierbar – überspringen
        clean = {k: v for k, v in raw_data.items() if k != "df_detail"}
        json.dump(clean, f, ensure_ascii=False, indent=2, default=str)

    # KI-Analyse
    path_analysis = f"{OUTPUT_DIR}/ads_analysis_{today}.json"
    with open(path_analysis, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    # Keywords als CSV (für Dashboard-Tabelle)
    keywords = analysis.get("top_keywords", [])
    if keywords:
        df = pd.DataFrame(keywords)
        df["datum"] = today
        df.to_csv(f"{OUTPUT_DIR}/seo_keywords_{today}.csv", index=False, encoding="utf-8-sig")

    # Artikel-Ideen als CSV
    artikel = analysis.get("artikel_ideen", [])
    if artikel:
        df_a = pd.DataFrame(artikel)
        df_a["datum"] = today
        df_a["secondary_keywords"] = df_a["secondary_keywords"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else x
        )
        df_a["affiliate_partner"] = df_a["affiliate_partner"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else x
        )
        df_a.to_csv(f"{OUTPUT_DIR}/artikel_ideen_{today}.csv", index=False, encoding="utf-8-sig")

    print(f"\n✓ Gespeichert:")
    print(f"  {path_raw}")
    print(f"  {path_analysis}")
    return path_analysis


def print_summary(analysis: dict):
    """Übersicht in der Konsole."""
    print(f"\n{'='*55}")
    print(f"  🎯 SEO KEYWORD REPORT – {today}")
    print(f"{'='*55}")

    print("\n  TOP KEYWORDS (nach Priorität):")
    for kw in sorted(analysis.get("top_keywords", []), key=lambda x: -x.get("prioritaet", 0))[:5]:
        bar = "█" * kw.get("prioritaet", 0) + "░" * (10 - kw.get("prioritaet", 0))
        print(f"  {bar}  {kw['keyword']}")
        print(f"           → {kw.get('begruendung','')[:60]}")

    print("\n  CONTENT-LÜCKEN (beste Chancen):")
    for gap in analysis.get("content_luecken", [])[:3]:
        print(f"  ◆ {gap['keyword']}")
        print(f"    {gap.get('opportunity','')[:70]}")

    print("\n  NÄCHSTE ARTIKEL:")
    for i, art in enumerate(analysis.get("artikel_ideen", [])[:3], 1):
        print(f"  {i}. {art['titel']}")
        print(f"     Primary: {art['primary_keyword']}")

    empfehlung = analysis.get("meta", {}).get("empfehlung", "")
    if empfehlung:
        print(f"\n  💡 {empfehlung}")

    print(f"{'='*55}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    raw_data = collect_all_ads_data()
    analysis = ai_analyze_keywords(raw_data)
    save_results(raw_data, analysis)
    print_summary(analysis)
    print("✅ Ads Intelligence fertig!")
    print(f"   → Keywords: output/seo_keywords_{today}.csv")
    print(f"   → Artikel-Ideen: output/artikel_ideen_{today}.csv")


if __name__ == "__main__":
    main()
