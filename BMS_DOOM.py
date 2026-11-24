import re
import time
import os
import requests
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Direct Prasads Multiplex venue URL
# BMS URL format: /buytickets/VENUE_CODE/YYYYMMDD
VENUE_URL = "https://in.bookmyshow.com/cinemas/hyderabad/prasads-multiplex-hyderabad/buytickets/PRHN/20261217"
MOVIE_KEYWORD = "avengers: doomsday"

# Extract the target date from the URL so the redirect check stays in sync
_TARGET_DATE = VENUE_URL.rstrip("/").split("/")[-1]  # e.g. "20261218"

# Tags associated with Prasads Screen 6 (PCX / Infinity Vision) on BookMyShow.
# BMS does NOT render "PCX" as text — it only appears in banner images.
# The actual text tags are "Infinity Vision 3D" and "MS-Infinity Vsn 3d".
PCX_TAGS = ["infinity vision", "infinity vsn", "inf vsn", "pcx", "screen 6", "barco 4k"]
CHECK_INTERVAL_SECONDS = 10

# --- TEST MODE ---
# Set to True to send a test notification on startup and exit, without monitoring BMS.
TEST_MODE = False


def send_telegram_alert(message: str):
    """Send a message via Telegram Bot API. Returns True on success."""
    if not BOT_TOKEN or not CHAT_ID:
        print("ERROR: BOT_TOKEN or CHAT_ID is empty. Cannot send Telegram message.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200 and resp.json().get("ok"):
            print("Telegram alert sent successfully!")
            return True
        else:
            print(f"Telegram API error: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


def run_test_mode():
    """Send a test notification to verify Telegram credentials are working."""
    print("=" * 50)
    print("TEST MODE - Verifying Telegram setup")
    print("=" * 50)

    test_msg = (
        "✅ <b>BMS_DOOM Test Notification</b>\n\n"
        "Your Telegram bot is configured correctly!\n"
        f"🎬 Monitoring for: <b>Avengers: Doomsday</b>\n"
        f"🏢 Venue: <b>Prasads Multiplex, Hyderabad</b>\n"
        f"📅 Target date: <b>{_TARGET_DATE}</b>\n"
        f"🎯 Target: <b>PCX / Infinity Vision / Screen 6</b>\n\n"
        f"👉 <a href='{VENUE_URL}'>BookMyShow Link</a>"
    )

    success = send_telegram_alert(test_msg)
    if success:
        print("\n✅ Test passed! You should see a message in your Telegram chat.")
    else:
        print("\n❌ Test failed! Check your BOT_TOKEN and CHAT_ID above.")
    return success


def extract_showtimes(block_lines):
    """Extract showtime strings like '08:00 AM', '02:10 PM' from a block of lines."""
    time_pattern = re.compile(r"^\d{1,2}:\d{2}\s*[AP]M$", re.IGNORECASE)
    return [line for line in block_lines if time_pattern.match(line.strip())]


def find_movie_showtime_blocks(lines):
    """
    Find the actual showtime listing for the movie (not footer mentions).
    BMS page structure for a venue date:
      - Movie title line (e.g. "Avengers: Doomsday (UA16+)")
      - Language line (e.g. "English")
      - Format/tag line (e.g. ", MS-Infinity Vsn 3d")
      - Showtimes interleaved with format labels
    
    We only want the FIRST match (the actual showtime listing), not footer
    sections like "MOVIES NOW SHOWING" which also contain the movie name.
    """
    results = []
    for i, line in enumerate(lines):
        if MOVIE_KEYWORD in line.lower():
            # Look at the next few lines — if they contain showtimes, this is a real listing
            block = lines[i : i + 30]
            showtimes = extract_showtimes(block)
            if showtimes:
                results.append({"index": i, "block": block, "showtimes": showtimes})
    return results


def monitor_prasads():
    print(f"Monitoring Prasads Multiplex ({_TARGET_DATE}) for Avengers: Doomsday PCX / Infinity Vision...")
    print(f"URL: {VENUE_URL}")
    print(f"Checking every {CHECK_INTERVAL_SECONDS} seconds\n")
    alerted_times = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        while True:
            try:
                page.goto(VENUE_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(4000)

                # Verify BookMyShow didn't redirect to a different date
                current_url = page.url
                if _TARGET_DATE not in current_url:
                    print(f"[{time.strftime('%H:%M:%S')}] {_TARGET_DATE} schedule not live yet (redirected to {current_url}).")
                    time.sleep(CHECK_INTERVAL_SECONDS)
                    continue

                content = page.inner_text("body")
                lines = [line.strip() for line in content.splitlines() if line.strip()]

                # Find real showtime blocks for Avengers: Doomsday
                blocks = find_movie_showtime_blocks(lines)

                if blocks:
                    for entry in blocks:
                        idx = entry["index"]
                        block = entry["block"]
                        showtimes = entry["showtimes"]
                        block_text = " | ".join(block)
                        block_lower = block_text.lower()

                        # Check if any PCX / Infinity Vision tag is present
                        matched_tags = [tag for tag in PCX_TAGS if tag in block_lower]
                        is_pcx = len(matched_tags) > 0

                        new_shows = [t for t in showtimes if f"{idx}_{t}" not in alerted_times]

                        if is_pcx and new_shows:
                            for t in new_shows:
                                alerted_times.add(f"{idx}_{t}")

                            alert_msg = (
                                f"🚨 <b>PRASADS PCX (INFINITY VISION) - {_TARGET_DATE} OPEN!</b>\n\n"
                                f"🎬 <b>Avengers: Doomsday</b>\n"
                                f"🏷 <b>Format:</b> {', '.join(matched_tags)}\n"
                                f"🕒 <b>Shows:</b> {', '.join(showtimes)}\n"
                                f"📋 <b>Details:</b> <code>{block_text[:280]}</code>\n\n"
                                f"👉 <a href='{VENUE_URL}'>Book Now on BookMyShow</a>"
                            )
                            print(f"[{time.strftime('%H:%M:%S')}] PCX shows found! Sending alert...")
                            send_telegram_alert(alert_msg)
                        elif not is_pcx and showtimes:
                            print(f"[{time.strftime('%H:%M:%S')}] Doomsday shows listed ({showtimes}) but NOT PCX/Infinity Vision format.")
                        elif not new_shows:
                            print(f"[{time.strftime('%H:%M:%S')}] Already alerted for these shows, waiting for new slots...")
                else:
                    # Check if the movie name appears at all (even in footer)
                    any_mention = any(MOVIE_KEYWORD in line.lower() for line in lines)
                    if any_mention:
                        print(f"[{time.strftime('%H:%M:%S')}] Doomsday mentioned on page but no showtimes listed yet...")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] {_TARGET_DATE} page active, Avengers: Doomsday not listed yet...")

            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] Check failed (retrying): {e}")

            time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    if TEST_MODE:
        run_test_mode()
    else:
        monitor_prasads()
