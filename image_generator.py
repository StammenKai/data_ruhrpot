"""
RuhrFinds – KI Bildgenerator
==============================
Generiert automatisch passende Instagram/Facebook Bilder
mit DALL-E 3 basierend auf dem Artikel-Thema.

Workflow:
1. Artikel-Thema & Keywords einlesen
2. Claude schreibt optimalen Bild-Prompt auf Deutsch
3. DALL-E 3 generiert das Bild (1024x1024 für Feed, 1024x1792 für Stories)
4. Bild wird lokal gespeichert + öffentlich via WordPress hochgeladen
5. URL wird an social_publisher.py weitergegeben

Voraussetzungen:
    pip install openai anthropic requests pillow python-dotenv

Kosten:
    DALL-E 3 Standard: ~0,04€ pro Bild
    DALL-E 3 HD:       ~0,08€ pro Bild
    → 30 Bilder/Monat = ca. 1,20€
"""

import os
import json
import time
import base64
import requests
from io import BytesIO
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Konfiguration ─────────────────────────────────────────────────────────────

OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
WP_URL            = os.getenv("WP_URL", "")
WP_USER           = os.getenv("WP_USER", "admin")
WP_PASSWORD       = os.getenv("WP_PASSWORD", "")

OUTPUT_DIR  = "output"
IMAGES_DIR  = "output/images"
os.makedirs(IMAGES_DIR, exist_ok=True)
today = date.today().isoformat()

# ── Ruhrgebiet Stil-DNA ───────────────────────────────────────────────────────
#
# Diese Basis-Beschreibung sorgt für einen konsistenten visuellen Stil
# auf allen RuhrFinds Bildern – erkennbar, authentisch, regional.

RUHRFINDS_STYLE = """
Fotorealistisch, hochwertig, authentisch.
Ruhrgebiet-Atmosphäre: industrielles Erbe trifft moderne Lebensqualität.
Warme goldene Stunde oder natürliches Tageslicht.
Menschen aus dem echten Leben – keine Stock-Foto-Optik.
Farbpalette: warme Erdtöne, gelegentlich industrielles Grau & Gelb als Akzent.
Keine Texte, Logos oder Wasserzeichen im Bild.
Bildformat: quadratisch, Instagram-optimiert.
Stil: Editorial Fotografie, nicht werblich.
"""

# ── Kategorie-spezifische Bild-Motive ────────────────────────────────────────

CATEGORY_VISUALS = {
    "Fahrrad & Outdoor": [
        "E-Bike auf einer Zechenhalde im Ruhrgebiet, Sonnenuntergang",
        "Radfahrer auf dem Emscher-Weg, grüne Landschaft, Sommer",
        "Fahrrad angelehnt an eine alte Industrieanlage, authentisch",
        "Familie auf Fahrrädern im Ruhrgebiet-Park",
    ],
    "Heimwerken & Garten": [
        "Gepflegter Vorgarten eines Ruhrgebiets-Reihenhauses im Frühling",
        "Heimwerker bei der Arbeit in hellem Keller, modernes Werkzeug",
        "Gartengeräte ordentlich auf Holzdiele, natürliches Licht",
        "Balkon-Bepflanzung über Ruhrgebiet-Stadtpanorama",
    ],
    "Elektronik & Technik": [
        "Moderner Laptop auf Holztisch in gemütlichem Wohnzimmer",
        "Smartphone in Hand, urbaner Ruhrgebiet-Hintergrund",
        "Elegante Technik-Produkte auf minimalistischem Tisch",
        "Kopfhörer auf Vinylplatte, Retro-Industrie-Flair",
    ],
    "Gesundheit & Fitness": [
        "Person joggt auf Haldenpfad mit Ruhrgebiet-Panorama",
        "Heimtrainer in hellem modernem Wohnzimmer",
        "Sportliche Person nach dem Training, authentisch, nicht gestellt",
        "Gesunde Mahlzeit auf Holztisch, natürliches Licht",
    ],
    "Familie & Kinder": [
        "Familie beim Picknick im Ruhrgebiet-Park, sonniger Tag",
        "Kind auf Fahrrad in ruhiger Wohnstraße",
        "Eltern und Kind beim Spielen im Garten, authentisch",
        "Gemütliche Familienszene im modernen Ruhrgebiet-Wohnzimmer",
    ],
    "Mode & Lifestyle": [
        "Person in stylischer Herbstjacke, urbaner Ruhrgebiet-Background",
        "Schuhe auf Kopfsteinpflaster, Industriegebäude im Hintergrund",
        "Moderner Lifestyle-Flatlay auf Holzboden",
        "Person in Alltagsoutfit, natürliches Licht, authentisch",
    ],
}


# ── Schritt 1: Bild-Prompt generieren ────────────────────────────────────────

def generate_image_prompt(article: dict) -> dict:
    """
    Claude denkt sich den perfekten DALL-E Prompt aus.
    Berücksichtigt: Thema, Keywords, Jahreszeit, Ruhrgebiet-Stil.

    Gibt zurück:
    - feed_prompt:  quadratisches Bild für Feed (1:1)
    - story_prompt: hochformatiges Bild für Stories (9:16)
    """
    gruppe  = article.get("gruppe", "Fahrrad & Outdoor")
    titel   = article.get("titel", "")
    keyword = article.get("primary_keyword", artikel_keyword(article))

    # Fallback: vordefinierte Motive nutzen
    if not ANTHROPIC_API_KEY:
        import random
        motiv = random.choice(CATEGORY_VISUALS.get(gruppe, CATEGORY_VISUALS["Fahrrad & Outdoor"]))
        return {
            "feed_prompt":  f"{motiv}. {RUHRFINDS_STYLE}",
            "story_prompt": f"{motiv}, Hochformat 9:16. {RUHRFINDS_STYLE}",
            "beschreibung": motiv,
        }

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    monat = __import__("datetime").datetime.now().month
    jahreszeit = (
        "Frühling, erste Blüten, helles Licht" if monat in [3,4,5] else
        "Sommer, sattes Grün, warme Sonne"     if monat in [6,7,8] else
        "Herbst, goldene Blätter, weiche Sonne" if monat in [9,10,11] else
        "Winter, klare Luft, ruhige Stimmung"
    )

    prompt = f"""Du bist ein kreativer Art Director für den Instagram-Account @ruhrfinds.

Erstelle einen präzisen Bild-Prompt für DALL-E 3 basierend auf:

Artikel-Titel: {titel}
Thema/Kategorie: {gruppe}
Haupt-Keyword: {keyword}
Jahreszeit: {jahreszeit}
Region: Ruhrgebiet / NRW

Stil-Vorgaben für RuhrFinds:
{RUHRFINDS_STYLE}

Antworte NUR als JSON:
{{
  "feed_prompt": "Englischer DALL-E Prompt für quadratisches Feed-Bild (max. 200 Zeichen)",
  "story_prompt": "Englischer DALL-E Prompt für Story-Format 9:16 (max. 200 Zeichen)",  
  "beschreibung": "Kurze deutsche Beschreibung was zu sehen ist (für Alt-Text)"
}}

Wichtig:
- Prompts auf ENGLISCH (DALL-E versteht Englisch besser)
- Keine Menschen mit erkennbaren Gesichtern
- Kein Text im Bild
- Authentisch, nicht wie Werbung"""

    try:
        msg = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group())
            print(f"  ✓ Prompt generiert: {result['beschreibung'][:60]}")
            return result
    except Exception as e:
        print(f"  ⚠ Prompt-Generierung fehlgeschlagen: {e}")

    # Fallback
    import random
    motiv = random.choice(CATEGORY_VISUALS.get(gruppe, CATEGORY_VISUALS["Fahrrad & Outdoor"]))
    return {
        "feed_prompt":  f"{motiv}. {RUHRFINDS_STYLE}",
        "story_prompt": f"Vertical 9:16 format. {motiv}. {RUHRFINDS_STYLE}",
        "beschreibung": motiv,
    }


def artikel_keyword(article: dict) -> str:
    """Extrahiert das wichtigste Keyword aus dem Artikel."""
    return (
        article.get("primary_keyword") or
        article.get("keywords", "").split(",")[0] or
        article.get("gruppe", "Ruhrgebiet")
    ).strip()


# ── Schritt 2: Bild mit DALL-E 3 generieren ──────────────────────────────────

def generate_image_dalle(prompt: str, size: str = "1024x1024", quality: str = "standard") -> bytes | None:
    """
    Generiert ein Bild mit DALL-E 3 via OpenAI API.

    size:    "1024x1024"  → Feed (quadratisch)
             "1024x1792"  → Story (hochformat)
             "1792x1024"  → Landscape (querformat)
    quality: "standard"   → ~0,04€
             "hd"         → ~0,08€ (schärfer, mehr Details)
    """
    if not OPENAI_API_KEY:
        print("  ⚠ Kein OPENAI_API_KEY – überspringe Bildgenerierung")
        return None

    print(f"  🎨 DALL-E 3 generiert Bild ({size}, {quality})...")

    try:
        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "model":           "dall-e-3",
                "prompt":          prompt,
                "n":               1,
                "size":            size,
                "quality":         quality,
                "response_format": "b64_json",  # Base64 statt URL (stabiler)
            },
            timeout=60,
        )
        response.raise_for_status()
        data     = response.json()
        b64_data = data["data"][0]["b64_json"]
        img_bytes = base64.b64decode(b64_data)
        print(f"  ✓ Bild generiert ({len(img_bytes) // 1024} KB)")
        return img_bytes

    except requests.exceptions.HTTPError as e:
        error = e.response.json() if e.response else str(e)
        print(f"  ✗ DALL-E Fehler: {error}")
        return None
    except Exception as e:
        print(f"  ✗ DALL-E Fehler: {e}")
        return None


# ── Schritt 3: Bild lokal speichern ──────────────────────────────────────────

def save_image_locally(img_bytes: bytes, filename: str) -> str:
    """Speichert das Bild als PNG und gibt den Pfad zurück."""
    path = os.path.join(IMAGES_DIR, filename)
    with open(path, "wb") as f:
        f.write(img_bytes)
    print(f"  ✓ Gespeichert: {path}")
    return path


# ── Schritt 4: Bild in WordPress hochladen ────────────────────────────────────

def upload_image_to_wordpress(img_bytes: bytes, filename: str, alt_text: str = "") -> str | None:
    """
    Lädt das Bild in die WordPress Media Library hoch.
    Gibt die öffentliche URL zurück – die braucht Instagram!

    Instagram kann keine lokalen Dateien verwenden –
    das Bild muss öffentlich im Internet erreichbar sein.
    """
    if not WP_URL or not WP_PASSWORD:
        print("  ⚠ WordPress nicht konfiguriert – Bild nur lokal gespeichert")
        return None

    print("  📤 Lade Bild in WordPress hoch...")

    try:
        resp = requests.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type":        "image/png",
            },
            data=img_bytes,
            auth=(WP_USER, WP_PASSWORD),
            timeout=60,
        )
        resp.raise_for_status()
        wp_data   = resp.json()
        image_url = wp_data.get("source_url", "")

        # Alt-Text setzen
        if alt_text and wp_data.get("id"):
            requests.post(
                f"{WP_URL}/wp-json/wp/v2/media/{wp_data['id']}",
                json={"alt_text": alt_text},
                auth=(WP_USER, WP_PASSWORD),
                timeout=15,
            )

        print(f"  ✓ WordPress URL: {image_url[:60]}")
        return image_url

    except Exception as e:
        print(f"  ✗ WordPress Upload Fehler: {e}")
        return None


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def create_social_images(article: dict) -> dict:
    """
    Kompletter Workflow: Prompt → Bild → Speichern → WordPress Upload.

    Gibt zurück:
    {
        "feed_url":     "https://ruhrfinds.de/wp-content/...feed.png",
        "story_url":    "https://ruhrfinds.de/wp-content/...story.png",
        "feed_path":    "/lokaler/pfad/feed.png",
        "story_path":   "/lokaler/pfad/story.png",
        "beschreibung": "Alt-Text für Barrierefreiheit",
    }
    """
    print(f"\n🖼  Bildgenerierung startet...")
    gruppe  = article.get("gruppe", "Fahrrad & Outdoor")
    slug    = today.replace("-", "")

    # 1. Prompts generieren
    prompts = generate_image_prompt(article)

    result = {
        "feed_url":     None,
        "story_url":    None,
        "feed_path":    None,
        "story_path":   None,
        "beschreibung": prompts.get("beschreibung", "RuhrFinds Artikel"),
    }

    # 2. Feed-Bild (1:1 quadratisch)
    feed_bytes = generate_image_dalle(
        prompt  = prompts["feed_prompt"],
        size    = "1024x1024",
        quality = "standard",
    )
    if feed_bytes:
        feed_filename    = f"ruhrfinds_{slug}_feed.png"
        result["feed_path"] = save_image_locally(feed_bytes, feed_filename)
        result["feed_url"]  = upload_image_to_wordpress(
            feed_bytes, feed_filename, prompts.get("beschreibung", "")
        )
        time.sleep(2)

    # 3. Story-Bild (9:16 hochformat)
    story_bytes = generate_image_dalle(
        prompt  = prompts["story_prompt"],
        size    = "1024x1792",
        quality = "standard",
    )
    if story_bytes:
        story_filename      = f"ruhrfinds_{slug}_story.png"
        result["story_path"] = save_image_locally(story_bytes, story_filename)
        result["story_url"]  = upload_image_to_wordpress(
            story_bytes, story_filename, prompts.get("beschreibung", "")
        )

    # 4. Zusammenfassung
    print(f"\n  Ergebnis:")
    print(f"  Feed:  {result['feed_url'] or result['feed_path'] or '– nicht verfügbar'}")
    print(f"  Story: {result['story_url'] or result['story_path'] or '– nicht verfügbar'}")

    return result


# ── Standalone Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{'='*55}")
    print(f"  🎨 RuhrFinds Bildgenerator – Test")
    print(f"{'='*55}\n")

    test_article = {
        "titel":           "Die 7 besten E-Bikes für Touren im Ruhrgebiet",
        "gruppe":          "Fahrrad & Outdoor",
        "primary_keyword": "E-Bike kaufen Ruhrgebiet",
        "wp_url":          "https://ruhrfinds.de/beste-e-bikes-ruhrgebiet",
    }

    images = create_social_images(test_article)

    print(f"\n{'='*55}")
    if images["feed_path"]:
        print(f"  ✅ Feed-Bild: {images['feed_path']}")
    if images["story_path"]:
        print(f"  ✅ Story-Bild: {images['story_path']}")
    if not images["feed_path"] and not images["story_path"]:
        print("  ⚠ Kein Bild generiert – API Key prüfen")
    print(f"{'='*55}\n")
