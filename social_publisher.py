"""
StammenMedia – Social Publisher
=================================
Veröffentlicht automatisch auf:
- Instagram (RuhrFinds)
- Facebook Seite (RuhrFinds)

Workflow:
1. Liest fertigen Blog-Artikel aus ki_content.py
2. KI schreibt passende Captions für jede Plattform
3. Generiert relevante Hashtags aus Trend-Keywords
4. Plant Posts zur optimalen Uhrzeit
5. Veröffentlicht via Meta Graph API

Voraussetzungen:
    pip install requests anthropic python-dotenv pillow

Meta Setup (einmalig):
    Siehe README_SOCIAL.md für Schritt-für-Schritt Anleitung
"""

import os
import json
import time
import requests
import anthropic
import pandas as pd
from datetime import date, datetime, timedelta
from dotenv import load_dotenv
from pathlib import Path
from image_generator import create_social_images

load_dotenv()

# ── Konfiguration (.env Datei) ────────────────────────────────────────────────
#
#   META_ACCESS_TOKEN=EAAxxxxxxx       ← Langzeit-Token aus Meta Developer
#   META_IG_ACCOUNT_ID=17841xxxxxxx    ← Instagram Business Account ID
#   META_FB_PAGE_ID=1234567890         ← Facebook Seiten ID
#   META_FB_PAGE_TOKEN=EAAxxxxxxx      ← Facebook Page Access Token

ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
META_ACCESS_TOKEN    = os.getenv("META_ACCESS_TOKEN", "")
META_IG_ACCOUNT_ID   = os.getenv("META_IG_ACCOUNT_ID", "")
META_FB_PAGE_ID      = os.getenv("META_FB_PAGE_ID", "")
META_FB_PAGE_TOKEN   = os.getenv("META_FB_PAGE_TOKEN", "")

GRAPH_API_URL = "https://graph.facebook.com/v19.0"
OUTPUT_DIR    = "output"
REPORT_DIR    = "reports"
LOG_FILE      = "social_log.json"
os.makedirs(OUTPUT_DIR, exist_ok=True)
today = date.today().isoformat()

# ── Optimale Posting-Zeiten (NRW Zielgruppe) ─────────────────────────────────

BEST_TIMES = {
    "instagram": {
        0: "18:00",  # Montag
        1: "18:30",  # Dienstag  ← beste Tage
        2: "18:00",  # Mittwoch  ← beste Tage
        3: "18:30",  # Donnerstag
        4: "17:00",  # Freitag
        5: "11:00",  # Samstag
        6: "11:00",  # Sonntag
    },
    "facebook": {
        0: "12:00",  # Montag    ← beste Tage
        1: "12:30",  # Dienstag  ← beste Tage
        2: "12:00",  # Mittwoch  ← beste Tage
        3: "12:30",  # Donnerstag
        4: "11:00",  # Freitag
        5: "10:00",  # Samstag
        6: "10:00",  # Sonntag
    },
}

# ── Hashtag Datenbank (nach Kategorie) ───────────────────────────────────────

HASHTAGS = {
    "Fahrrad & Outdoor": [
        "#ebike", "#fahrrad", "#ruhrgebiet", "#ruhrpott", "#nrw",
        "#fahrradfahren", "#ebikes", "#cycling", "#outdoor", "#pedelec",
        "#fahrradtour", "#ruhrgebietliebe", "#castroprauxel", "#ruhrfinds",
        "#fahrradkaufen", "#ebikegermany", "#outdoornrw", "#radfahren",
    ],
    "Heimwerken & Garten": [
        "#heimwerken", "#garten", "#ruhrgebiet", "#nrw", "#diy",
        "#gartenliebe", "#handwerk", "#werkzeug", "#gartengestaltung",
        "#ruhrpott", "#ruhrfinds", "#diyprojekte", "#gartenideen",
        "#heimwerkertipps", "#bauen", "#renovieren", "#gartenarbeit",
    ],
    "Elektronik & Technik": [
        "#technik", "#elektronik", "#gadgets", "#smartphone", "#laptop",
        "#ruhrgebiet", "#nrw", "#technikliebe", "#ruhrfinds",
        "#newtechnology", "#kauftipp", "#techtest", "#gadgetreview",
    ],
    "Gesundheit & Fitness": [
        "#fitness", "#gesundheit", "#sport", "#ruhrgebiet", "#nrw",
        "#fitnessmotivation", "#training", "#workout", "#gesundleben",
        "#ruhrpott", "#ruhrfinds", "#heimtraining", "#sportliebe",
    ],
    "Familie & Kinder": [
        "#familie", "#kinder", "#ruhrgebiet", "#nrw", "#familienleben",
        "#eltern", "#kindheit", "#familienzeit", "#ruhrpott",
        "#ruhrfinds", "#mamablog", "#papablog", "#familientipps",
    ],
    "Mode & Lifestyle": [
        "#mode", "#lifestyle", "#fashion", "#ruhrgebiet", "#nrw",
        "#ootd", "#style", "#outfit", "#fashionblogger", "#ruhrpott",
        "#ruhrfinds", "#modeblog", "#fashiontips",
    ],
}

DEFAULT_HASHTAGS = [
    "#ruhrfinds", "#ruhrgebiet", "#ruhrpott", "#nrw",
    "#castroprauxel", "#kauftipp", "#empfehlung",
]


# ── Schritt 1: Artikel-Daten laden ────────────────────────────────────────────

def load_latest_article() -> dict:
    """Liest den zuletzt generierten Artikel aus dem Content-Log."""
    if not os.path.exists(LOG_FILE):
        print("⚠ Kein Artikel-Log gefunden – nutze Demo-Daten")
        return _demo_article()

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        log = json.load(f)

    if not log:
        return _demo_article()

    latest = log[-1]
    print(f"✓ Artikel geladen: {latest.get('titel', '?')[:60]}")
    return latest


def _demo_article() -> dict:
    return {
        "titel": "Die 7 besten E-Bikes für Touren im Ruhrgebiet (2026)",
        "gruppe": "Fahrrad & Outdoor",
        "wp_url": "https://ruhrfinds.de/beste-e-bikes-ruhrgebiet",
        "datum": today,
        "meta_description": "Die besten E-Bikes für das Ruhrgebiet im großen Vergleich.",
    }


# ── Schritt 2: KI schreibt Social Media Captions ─────────────────────────────

def generate_captions(article: dict) -> dict:
    """
    Claude schreibt plattformgerechte Captions.

    Instagram: emotional, visuell, Hashtags am Ende
    Facebook:  informativer, mit Link, etwas länger
    """
    if not ANTHROPIC_API_KEY:
        print("⚠ Kein API-Key – nutze Demo-Captions")
        return _demo_captions(article)

    try:
        import httpx
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, http_client=httpx.Client())
    except Exception:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    gruppe = article.get("gruppe", "Fahrrad & Outdoor")
    hashtags = _select_hashtags(gruppe)

    prompt = f"""Du schreibst Social Media Posts für den Blog "RuhrFinds" – Das Beste aus dem Pott.
Zielgruppe: Menschen im Ruhrgebiet, 25–55 Jahre, kaufinteressiert, regional verbunden.
Ton: direkt, herzlich, Ruhrpott-typisch – kein Marketing-Sprech.

ARTIKEL:
Titel: {article.get('titel', '')}
Thema: {gruppe}
URL: {article.get('wp_url', 'https://ruhrfinds.de')}
Beschreibung: {article.get('meta_description', '')}

Schreibe ZWEI Posts als JSON:

1. INSTAGRAM POST:
   - 3-5 Zeilen, emotional & neugierig machend
   - Erste Zeile muss zum Weiterlesen animieren (Hook)
   - Lokaler Ruhrgebiet-Bezug
   - "Link in Bio" am Ende
   - KEINE Hashtags im Text (kommen separat)
   - Max. 150 Wörter

2. FACEBOOK POST:
   - 4-6 Zeilen, etwas informativer
   - Direkte Frage an die Community einbauen
   - Artikel-URL am Ende einbauen
   - Max. 200 Wörter

Antworte NUR als JSON:
{{
  "instagram": "...",
  "facebook": "...",
  "story_text": "Kurzer Story-Text (max. 3 Zeilen, sehr direkt)"
}}"""

    try:
        msg = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text
        # JSON extrahieren
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            captions = json.loads(match.group())
            print("✓ Captions generiert")
            return captions
    except Exception as e:
        print(f"⚠ Caption-Fehler: {e}")

    return _demo_captions(article)


def _demo_captions(article: dict) -> dict:
    titel = article.get("titel", "Neuer Artikel")
    url   = article.get("wp_url", "https://ruhrfinds.de")
    return {
        "instagram": f"Pott-Menschen aufgepasst! 🚴\n\n{titel}\n\nWir haben alles getestet damit du es nicht musst. Ehrlich. Direkt. Aus dem Ruhrgebiet.\n\n→ Link in Bio",
        "facebook":  f"📖 Neuer Artikel auf RuhrFinds:\n\n{titel}\n\nWas meint ihr – habt ihr damit schon Erfahrungen gemacht? Schreibt es in die Kommentare!\n\n👉 {url}",
        "story_text": f"NEU auf RuhrFinds:\n{titel[:50]}\n→ Link in Bio",
    }


# ── Schritt 3: Hashtags auswählen ────────────────────────────────────────────

def _select_hashtags(gruppe: str, max_tags: int = 25) -> list[str]:
    """Wählt relevante Hashtags – Mix aus Kategorie + Standard."""
    category_tags = HASHTAGS.get(gruppe, [])
    combined      = list(dict.fromkeys(category_tags + DEFAULT_HASHTAGS))
    return combined[:max_tags]


# ── Schritt 4: Bild vorbereiten ───────────────────────────────────────────────

def prepare_image(article: dict) -> str | None:
    """
    Gibt URL zu einem Beitragsbild zurück.
    Priorität:
    1. Featured Image aus WordPress
    2. Generiertes Bild (wenn DALL-E konfiguriert)
    3. Standard-Fallback-Bild von RuhrFinds
    """
    # WordPress Featured Image URL
    wp_url = article.get("wp_url", "")
    if wp_url:
        # WordPress REST API: Featured Image abrufen
        try:
            slug = wp_url.rstrip("/").split("/")[-1]
            api_url = f"{os.getenv('WP_URL', '')}/wp-json/wp/v2/posts?slug={slug}&_fields=featured_media_url"
            resp = requests.get(api_url, timeout=8)
            data = resp.json()
            if data and isinstance(data, list) and data[0].get("featured_media_url"):
                img_url = data[0]["featured_media_url"]
                print(f"✓ Bild gefunden: {img_url[:60]}")
                return img_url
        except Exception:
            pass

    # Fallback: Standard RuhrFinds Bild
    fallback = os.getenv("DEFAULT_SOCIAL_IMAGE", "")
    if fallback:
        return fallback

    print("⚠ Kein Bild verfügbar – Post wird ohne Bild veröffentlicht")
    return None


# ── Schritt 5: Instagram Post veröffentlichen ─────────────────────────────────

def post_instagram(caption: str, hashtags: list[str], image_url: str | None = None) -> dict:
    """
    Veröffentlicht auf Instagram Business via Graph API.
    Schritt 1: Media Container erstellen
    Schritt 2: Container veröffentlichen
    """
    if not META_ACCESS_TOKEN or not META_IG_ACCOUNT_ID:
        print("⚠ Instagram nicht konfiguriert – simuliere Post")
        return {"status": "simuliert", "plattform": "instagram"}

    full_caption = caption + "\n\n" + " ".join(hashtags)

    try:
        # Schritt 1: Container erstellen
        container_data = {
            "caption":      full_caption,
            "access_token": META_ACCESS_TOKEN,
        }
        if image_url:
            container_data["image_url"] = image_url
            container_data["media_type"] = "IMAGE"
        else:
            # Ohne Bild – Reels/Carousel nicht möglich, nur mit Bild
            print("⚠ Instagram braucht ein Bild – überspringe")
            return {"status": "übersprungen", "grund": "kein_bild"}

        resp = requests.post(
            f"{GRAPH_API_URL}/{META_IG_ACCOUNT_ID}/media",
            data=container_data,
            timeout=30,
        )
        resp.raise_for_status()
        container_id = resp.json().get("id")

        # Kurz warten bis Container verarbeitet
        time.sleep(4)

        # Schritt 2: Veröffentlichen
        pub_resp = requests.post(
            f"{GRAPH_API_URL}/{META_IG_ACCOUNT_ID}/media_publish",
            data={"creation_id": container_id, "access_token": META_ACCESS_TOKEN},
            timeout=30,
        )
        pub_resp.raise_for_status()
        post_id = pub_resp.json().get("id")

        print(f"✓ Instagram Post veröffentlicht: {post_id}")
        return {"status": "veröffentlicht", "plattform": "instagram", "id": post_id}

    except requests.exceptions.HTTPError as e:
        error = e.response.json() if e.response else str(e)
        print(f"✗ Instagram Fehler: {error}")
        return {"status": "fehler", "plattform": "instagram", "fehler": str(error)}
    except Exception as e:
        print(f"✗ Instagram Fehler: {e}")
        return {"status": "fehler", "plattform": "instagram", "fehler": str(e)}


# ── Schritt 6: Facebook Post veröffentlichen ──────────────────────────────────

def post_facebook(caption: str, image_url: str | None = None, link: str | None = None) -> dict:
    """Veröffentlicht auf der Facebook Seite."""
    if not META_FB_PAGE_TOKEN or not META_FB_PAGE_ID:
        print("⚠ Facebook nicht konfiguriert – simuliere Post")
        return {"status": "simuliert", "plattform": "facebook"}

    try:
        if image_url:
            # Post mit Bild
            data = {
                "message":      caption,
                "url":          image_url,
                "access_token": META_FB_PAGE_TOKEN,
            }
            endpoint = f"{GRAPH_API_URL}/{META_FB_PAGE_ID}/photos"
        else:
            # Text-Post mit Link
            data = {
                "message":      caption,
                "access_token": META_FB_PAGE_TOKEN,
            }
            if link:
                data["link"] = link
            endpoint = f"{GRAPH_API_URL}/{META_FB_PAGE_ID}/feed"

        resp = requests.post(endpoint, data=data, timeout=30)
        resp.raise_for_status()
        post_id = resp.json().get("id") or resp.json().get("post_id")

        print(f"✓ Facebook Post veröffentlicht: {post_id}")
        return {"status": "veröffentlicht", "plattform": "facebook", "id": post_id}

    except requests.exceptions.HTTPError as e:
        error = e.response.json() if e.response else str(e)
        print(f"✗ Facebook Fehler: {error}")
        return {"status": "fehler", "plattform": "facebook", "fehler": str(error)}
    except Exception as e:
        print(f"✗ Facebook Fehler: {e}")
        return {"status": "fehler", "plattform": "facebook", "fehler": str(e)}


# ── Schritt 7: Protokoll führen ───────────────────────────────────────────────

def log_social_post(article: dict, captions: dict, ig_result: dict, fb_result: dict):
    """Protokolliert alle Social Media Posts."""
    log = []
    if os.path.exists(LOG_FILE.replace("content", "social")):
        with open(LOG_FILE.replace("content", "social"), "r", encoding="utf-8") as f:
            log = json.load(f)

    eintrag = {
        "datum":          today,
        "uhrzeit":        datetime.now().strftime("%H:%M"),
        "artikel_titel":  article.get("titel", ""),
        "artikel_url":    article.get("wp_url", ""),
        "gruppe":         article.get("gruppe", ""),
        "ig_status":      ig_result.get("status"),
        "ig_id":          ig_result.get("id"),
        "fb_status":      fb_result.get("status"),
        "fb_id":          fb_result.get("id"),
        "ig_caption":     captions.get("instagram", "")[:100],
        "fb_caption":     captions.get("facebook", "")[:100],
    }
    log.append(eintrag)

    path = LOG_FILE.replace("content", "social")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"✓ Social-Log aktualisiert ({len(log)} Posts gesamt)")


# ── Zeitplan prüfen ───────────────────────────────────────────────────────────

def should_post_now(platform: str) -> bool:
    """
    Prüft ob jetzt die optimale Posting-Zeit ist.
    GitHub Actions startet um 06:00 UTC = 07:00 MEZ.
    Wir planen Posts für später am Tag.
    """
    now      = datetime.now()
    weekday  = now.weekday()
    best_str = BEST_TIMES[platform][weekday]
    best_h, best_m = map(int, best_str.split(":"))

    best_time = now.replace(hour=best_h, minute=best_m, second=0)
    diff      = abs((now - best_time).total_seconds())

    # Innerhalb von 30 Minuten der optimalen Zeit → posten
    return diff < 1800


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  📱 StammenMedia Social Publisher – {today}")
    print(f"  Projekt: RuhrFinds")
    print(f"{'='*55}\n")

    # 1. Letzten Artikel laden
    article  = load_latest_article()
    gruppe   = article.get("gruppe", "Fahrrad & Outdoor")
    hashtags = _select_hashtags(gruppe)

    # 2. Captions generieren
    print("🤖 Generiere Captions...")
    captions = generate_captions(article)

    # 3. Bilder generieren (DALL-E 3)
    print("🎨 Generiere Bilder mit DALL-E 3...")
    images = create_social_images(article)
    feed_url  = images.get("feed_url")  or images.get("feed_path")
    story_url = images.get("story_url") or images.get("story_path")

    # 4. Instagram posten (Feed-Bild)
    print("\n📸 Instagram...")
    ig_result = post_instagram(
        caption   = captions.get("instagram", ""),
        hashtags  = hashtags,
        image_url = feed_url,
    )

    time.sleep(3)

    # 5. Facebook posten
    print("👍 Facebook...")
    fb_result = post_facebook(
        caption   = captions.get("facebook", ""),
        image_url = feed_url,
        link      = article.get("wp_url"),
    )

    # 6. Protokollieren
    log_social_post(article, captions, ig_result, fb_result)

    # 7. Zusammenfassung
    print(f"\n{'='*55}")
    print(f"  ✅ SOCIAL PUBLISHING FERTIG")
    print(f"{'='*55}")
    print(f"  Instagram: {ig_result['status']}")
    print(f"  Facebook:  {fb_result['status']}")
    print(f"\n  Caption Instagram (Vorschau):")
    print(f"  {captions.get('instagram','')[:100]}...")
    print(f"\n  Hashtags: {' '.join(hashtags[:5])} ...")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
