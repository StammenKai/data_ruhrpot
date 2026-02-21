# 📊 Castrop-Rauxel Daten-Dashboard

Kostenloses Analyse-System für Bevölkerungstrends, Einzelhandel und Veranstaltungen in Castrop-Rauxel.

## Was wird gesammelt?

| Datenquelle | Inhalt | Kosten |
|---|---|---|
| **OpenStreetMap (Overpass API)** | Läden, Restaurants, Freizeit | Kostenlos |
| **Stadtwebsite Castrop-Rauxel** | Veranstaltungen (Scraping) | Kostenlos |
| **IT.NRW / Bertelsmann** | Bevölkerungsdaten (manuell) | Kostenlos |
| **Google Sheets** | Datenspeicherung (optional) | Kostenlos |

## Schnellstart (lokal)

```bash
# 1. Abhängigkeiten installieren
pip install requests beautifulsoup4 gspread google-auth pandas matplotlib seaborn jinja2

# 2. Daten sammeln
python collector.py

# 3. Analyse & Dashboard generieren
python analyse.py

# Dashboard öffnen:
open reports/dashboard_<heute>.html
```

## Automatisierung mit GitHub Actions (kostenlos)

1. Repository auf GitHub erstellen
2. Dateien hochladen
3. `Settings → Secrets` anlegen (optional für Google Sheets):
   - `GOOGLE_SHEET_ID` → ID deines Google Sheets
   - `GOOGLE_CREDENTIALS_JSON` → Inhalt der Service-Account JSON-Datei
4. Actions laufen täglich um 07:00 Uhr automatisch

## Google Sheets Setup (optional)

```
1. console.cloud.google.com → Projekt erstellen
2. APIs aktivieren: Google Sheets API, Google Drive API
3. IAM → Service Account erstellen → JSON-Key herunterladen
4. Google Sheet erstellen
5. Sheet mit Service-Account-E-Mail teilen (Bearbeiter)
6. Sheet-ID aus URL kopieren: 
   https://docs.google.com/spreadsheets/d/[HIER-IST-DIE-ID]/edit
```

## Outputs

```
output/
  osm_2024-01-15.csv          ← Tages-Snapshot OSM-Daten
  events_2024-01-15.csv       ← Gescrapte Events
  bevoelkerung.csv            ← Bevölkerungszeitreihe
  summary_2024-01-15.json     ← Tageszusammenfassung

reports/
  dashboard_2024-01-15.html   ← HTML Dashboard
  bevoelkerung_trend.png      ← Bevölkerungsplot
  osm_kategorien.png          ← Kategorie-Verteilung
  osm_zeitreihe.png           ← Entwicklung über Zeit
  events_trend.png            ← Events-Trend
  veraenderungen_*.json       ← Neu/Geschlossen Report
```

## Erweiterungsideen

- **Google Trends** via `pytrends` → Suchanfragen aus Castrop-Rauxel
- **Hystreet API** → Passantenfrequenz Innenstadt
- **Destatis API** → Gewerbean-/abmeldungen
- **Looker Studio** → Dashboard mit Google Sheets verbinden

## Quellen & Lizenzen

- OpenStreetMap-Daten © OpenStreetMap-Mitwirkende (ODbL-Lizenz)
- Bevölkerungsdaten: IT.NRW, Bertelsmann Stiftung (Wegweiser Kommune)
- Veranstaltungen: Stadt Castrop-Rauxel (öffentlich zugänglich)
