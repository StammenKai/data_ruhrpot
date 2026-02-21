"""
Castrop-Rauxel Datensammler
============================
Sammelt täglich:
- OSM Einzelhandelsdaten (Läden, Restaurants etc.)
- Veranstaltungen von der Stadtwebsite
- Schreibt alles in Google Sheets (oder CSV als Fallback)

Voraussetzungen:
    pip install requests beautifulsoup4 gspread google-auth pandas

Google Sheets Setup (optional):
    1. Google Cloud Console → Service Account erstellen
    2. JSON-Key herunterladen → als GOOGLE_CREDENTIALS_PATH hinterlegen
    3. Google Sheet erstellen und Service Account teilen
"""

import requests
import json
import csv
import os
import logging
from datetime import datetime, date
from bs4 import BeautifulSoup
import pandas as pd

# ── Konfiguration ────────────────────────────────────────────────────────────

CITY = "Castrop-Rauxel"
POSTCODES = ["44575", "44577", "44579", "44581"]
OSM_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
EVENTS_URL = "https://www.castrop-rauxel.de/veranstaltungen"
OUTPUT_DIR = "output"
LOG_FILE = "collector.log"

# Google Sheets (optional) – leer lassen wenn nicht genutzt
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

os.makedirs(OUTPUT_DIR, exist_ok=True)
today = date.today().isoformat()


# ── 1. OSM Einzelhandelsdaten ────────────────────────────────────────────────

OSM_TAGS = {
    "shop": "Laden/Geschäft",
    "amenity": "Gastronomie/Service",
    "leisure": "Freizeit",
    "tourism": "Tourismus",
}


def fetch_osm_data(tag: str) -> list[dict]:
    """Holt alle Nodes/Ways mit einem bestimmten Tag aus Castrop-Rauxel."""
    query = f"""
    [out:json][timeout:30];
    area[name="{CITY}"]->.a;
    (
      node(area.a)[{tag}];
      way(area.a)[{tag}];
    );
    out center tags;
    """
    try:
        response = requests.post(OSM_OVERPASS_URL, data={"data": query}, timeout=40)
        response.raise_for_status()
        elements = response.json().get("elements", [])
        log.info(f"OSM [{tag}]: {len(elements)} Einträge gefunden")
        return elements
    except Exception as e:
        log.error(f"OSM Fehler bei Tag '{tag}': {e}")
        return []


def parse_osm_elements(elements: list, category: str) -> list[dict]:
    rows = []
    for el in elements:
        tags = el.get("tags", {})
        # Koordinaten (Node direkt, Way über center)
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        rows.append({
            "datum": today,
            "kategorie": category,
            "name": tags.get("name", "–"),
            "typ": tags.get(category.split("/")[0].lower(), tags.get("amenity", "–")),
            "strasse": tags.get("addr:street", ""),
            "hausnummer": tags.get("addr:housenumber", ""),
            "plz": tags.get("addr:postcode", ""),
            "ort": tags.get("addr:city", CITY),
            "lat": lat,
            "lon": lon,
            "oeffnungszeiten": tags.get("opening_hours", ""),
            "website": tags.get("website", tags.get("contact:website", "")),
            "osm_id": el.get("id"),
            "osm_typ": el.get("type"),
        })
    return rows


def collect_osm() -> pd.DataFrame:
    all_rows = []
    for tag, label in OSM_TAGS.items():
        elements = fetch_osm_data(tag)
        all_rows.extend(parse_osm_elements(elements, label))
    df = pd.DataFrame(all_rows)
    path = f"{OUTPUT_DIR}/osm_{today}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    log.info(f"OSM Daten gespeichert: {path} ({len(df)} Einträge)")
    return df


# ── 2. Veranstaltungs-Scraper ────────────────────────────────────────────────

def scrape_events() -> list[dict]:
    """Scrapt Veranstaltungen von der offiziellen Stadtwebsite."""
    events = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (research bot; contact@example.com)"}
        resp = requests.get(EVENTS_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Generischer Ansatz – passt sich an gängige CMS-Strukturen an
        # Versuche mehrere typische Selektoren
        candidates = (
            soup.select("article.event")
            or soup.select(".event-item")
            or soup.select(".veranstaltung")
            or soup.select("li.event")
            or soup.select(".tx-cal-event")  # TYPO3 Kalender
        )

        if not candidates:
            log.warning("Kein bekanntes Event-Markup gefunden – rohe Links werden extrahiert")
            # Fallback: alle Links mit Datum-ähnlichen Texten
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                if len(text) > 10:
                    events.append({
                        "datum_abruf": today,
                        "titel": text[:200],
                        "datum_event": "",
                        "ort": "",
                        "beschreibung": "",
                        "link": a["href"],
                        "quelle": EVENTS_URL,
                    })
        else:
            for item in candidates:
                title_el = item.find(["h2", "h3", "h4", ".title", ".event-title"])
                date_el = item.find(["time", ".date", ".event-date"])
                loc_el = item.find([".location", ".ort", ".venue"])
                desc_el = item.find(["p", ".description", ".teaser"])
                link_el = item.find("a", href=True)

                events.append({
                    "datum_abruf": today,
                    "titel": title_el.get_text(strip=True) if title_el else "–",
                    "datum_event": date_el.get("datetime", date_el.get_text(strip=True) if date_el else ""),
                    "ort": loc_el.get_text(strip=True) if loc_el else "",
                    "beschreibung": desc_el.get_text(strip=True)[:300] if desc_el else "",
                    "link": link_el["href"] if link_el else "",
                    "quelle": EVENTS_URL,
                })

        log.info(f"Events: {len(events)} Einträge gescrapt")
    except Exception as e:
        log.error(f"Event-Scraping Fehler: {e}")

    return events


def collect_events() -> pd.DataFrame:
    events = scrape_events()
    df = pd.DataFrame(events)
    path = f"{OUTPUT_DIR}/events_{today}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    log.info(f"Events gespeichert: {path}")
    return df


# ── 3. Bevölkerungs-Snapshot (statisch + Trend-Marker) ──────────────────────

POPULATION_DATA = [
    # Quelle: IT.NRW / Wegweiser Kommune (manuell gepflegt oder per API ergänzt)
    {"jahr": 2010, "bevoelkerung": 77700},
    {"jahr": 2015, "bevoelkerung": 74800},
    {"jahr": 2020, "bevoelkerung": 72500},
    {"jahr": 2022, "bevoelkerung": 71900},
    {"jahr": 2023, "bevoelkerung": 71500},
    # Prognose Bertelsmann Stiftung
    {"jahr": 2030, "bevoelkerung": 69000, "prognose": True},
    {"jahr": 2035, "bevoelkerung": 67000, "prognose": True},
]


def collect_population() -> pd.DataFrame:
    df = pd.DataFrame(POPULATION_DATA)
    df["datum_abruf"] = today
    path = f"{OUTPUT_DIR}/bevoelkerung.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    log.info(f"Bevölkerungsdaten gespeichert: {path}")
    return df


# ── 4. Google Sheets Upload ──────────────────────────────────────────────────

def upload_to_sheets(df: pd.DataFrame, sheet_name: str):
    """Lädt einen DataFrame in ein Google Sheet hoch."""
    if not GOOGLE_SHEET_ID:
        log.info(f"Kein GOOGLE_SHEET_ID gesetzt – überspringe Upload für '{sheet_name}'")
        return

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)

        try:
            ws = sh.worksheet(sheet_name)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=sheet_name, rows=5000, cols=30)

        # Header + Daten
        data = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
        ws.update(data)
        log.info(f"Google Sheets Upload erfolgreich: '{sheet_name}' ({len(df)} Zeilen)")
    except ImportError:
        log.warning("gspread nicht installiert – pip install gspread google-auth")
    except Exception as e:
        log.error(f"Google Sheets Fehler: {e}")


# ── 5. Zusammenfassung & Statistiken ────────────────────────────────────────

def generate_summary(df_osm: pd.DataFrame, df_events: pd.DataFrame, df_pop: pd.DataFrame):
    summary = {
        "datum": today,
        "osm_gesamt": len(df_osm),
        "osm_laeden": len(df_osm[df_osm["kategorie"] == "Laden/Geschäft"]),
        "osm_gastronomie": len(df_osm[df_osm["kategorie"] == "Gastronomie/Service"]),
        "osm_freizeit": len(df_osm[df_osm["kategorie"] == "Freizeit"]),
        "events_gesamt": len(df_events),
        "bevoelkerung_aktuell": df_pop[df_pop["jahr"] == 2023]["bevoelkerung"].values[0] if not df_pop.empty else "–",
    }

    path = f"{OUTPUT_DIR}/summary_{today}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log.info(f"\n{'='*50}")
    log.info(f"ZUSAMMENFASSUNG {today}")
    log.info(f"{'='*50}")
    for k, v in summary.items():
        log.info(f"  {k:<30} {v}")
    log.info(f"{'='*50}\n")
    return summary


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    log.info(f"Starte Datensammlung für {CITY} – {today}")

    df_osm = collect_osm()
    df_events = collect_events()
    df_pop = collect_population()

    # Google Sheets Upload (wenn konfiguriert)
    upload_to_sheets(df_osm, f"OSM_{today}")
    upload_to_sheets(df_events, f"Events_{today}")
    upload_to_sheets(df_pop, "Bevoelkerung")

    generate_summary(df_osm, df_events, df_pop)
    log.info("Fertig!")


if __name__ == "__main__":
    main()
