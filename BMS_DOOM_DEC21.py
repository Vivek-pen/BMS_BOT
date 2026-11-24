import re
import sys
import time

from playwright.sync_api import sync_playwright

from BMS_DOOM import send_telegram_alert


TARGET_DATE = "20261221"
MOVIE_KEYWORD = "avengers: doomsday"
INFINITY_FORMAT_TAGS = [
    "ms-infinity vision",
    "ms-infinity vsn",
    "infinity vision",
    "infinity vsn",
]
CHECK_INTERVAL_SECONDS = 100
CINEMAS_URL = "https://in.bookmyshow.com/explore/cinemas-hyderabad"
TEST_VENUE_URL = (
    "https://in.bookmyshow.com/cinemas/hyderabad/"
    "prasads-multiplex-hyderabad/buytickets/PRHN/20261217"
)
TARGET_THEATER_PAGES = [
    (
        "prasads-multiplex-hyderabad",
        "https://in.bookmyshow.com/cinemas/hyderabad/prasads-multiplex-hyderabad",
        "PRHN",
    ),
    (
        "aaa-cinemas-ameerpet-hyderabad",
        "https://in.bookmyshow.com/cinemas/hyderabad/aaa-cinemas-ameerpet-hyderabad",
        "ACAS",
    ),
    (
        "amb-cinemas-gachibowli-hyderabad",
        "https://in.bookmyshow.com/cinemas/hyderabad/amb-cinemas-gachibowli-hyderabad",
        "AMBH",
    ),
]


def extract_showtimes(block_lines):
    time_pattern = re.compile(r"^\d{1,2}:\d{2}\s*[AP]M$", re.IGNORECASE)
    return [line.strip() for line in block_lines if time_pattern.match(line.strip())]


def find_movie_showtime_blocks(lines):
    results = []
    for index, line in enumerate(lines):
        if MOVIE_KEYWORD not in line.lower():
            continue

        block = lines[index:index + 30]
        showtimes = extract_showtimes(block)
        if showtimes:
            results.append({
                "index": index,
                "block": block,
                "showtimes": showtimes,
            })
    return results


def find_english_infinity_blocks(lines):
    matches = []
    for entry in find_movie_showtime_blocks(lines):
        block = entry["block"]
        block_text = " | ".join(block)
        block_lower = block_text.lower()

        is_english = re.search(r"\benglish\b", block_lower) is not None
        matched_formats = [
            tag for tag in INFINITY_FORMAT_TAGS if tag in block_lower
        ]
        if is_english and matched_formats:
            entry["block_text"] = block_text
            entry["matched_formats"] = matched_formats
            matches.append(entry)

    return matches


def send_test_notification():
    message = (
        "Test notification: BMS_DOOM_DEC21\n\n"
        "Telegram is configured correctly.\n"
        "Tested the English MS-Infinity Vision filter for 21 December 2026."
    )
    return send_telegram_alert(message)


def run_test_mode():
    print("=" * 60)
    print("BMS_DOOM_DEC21 - ONE-SHOT TEST (Dec 17 — live shows)")
    print("=" * 60)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        print(f"\n1. Loading {TEST_VENUE_URL}")
        page.goto(TEST_VENUE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        print(f"   Final URL: {page.url}")
        if "20261217" not in page.url:
            print("   FAIL: Redirected away from Dec 17. Date is not live.")
            browser.close()
            return False

        print("   PASS: Dec 17 page is live.")
        content = page.inner_text("body")
        lines = [line.strip() for line in content.splitlines() if line.strip()]

        print("\n2. Searching for English Avengers: Doomsday MS-Infinity Vision")
        blocks = find_english_infinity_blocks(lines)

        if not blocks:
            print("   FAIL: No English MS-Infinity Vision showtime block found.")
            browser.close()
            return False

        entry = blocks[0]
        print(f"   PASS: Found showtimes: {', '.join(entry['showtimes'])}")
        print(f"   Matched formats: {', '.join(entry['matched_formats'])}")

        message = (
            "<b>BMS_DOOM_DEC21 TEST ALERT</b>\n\n"
            "Avengers: Doomsday English MS-Infinity Vision detection passed.\n"
            f"<b>Theater:</b> Prasads Multiplex\n"
            f"<b>Test date:</b> 17 December 2026\n"
            f"<b>Formats:</b> {', '.join(entry['matched_formats'])}\n"
            f"<b>Shows:</b> {', '.join(entry['showtimes'])}\n"
            f"<b>Details:</b> <code>{entry['block_text'][:280]}</code>\n\n"
            f"<a href='{TEST_VENUE_URL}'>Test on BookMyShow</a>"
        )

        print("\n3. Sending Telegram test alert")
        success = send_telegram_alert(message)
        browser.close()
        print("\nTEST COMPLETE")
        return success


def run_one_shot_check():
    print(
        f"GitHub Actions check for English Avengers: Doomsday MS-Infinity Vision "
        f"in the three target theaters on {TARGET_DATE}."
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        for theater_url, (venue_code, theater_slug) in get_theater_urls(page).items():
            try:
                page.goto(theater_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2500)

                if TARGET_DATE not in page.url:
                    print(f"{theater_slug}: target date is not live.")
                    continue

                lines = [
                    line.strip()
                    for line in page.inner_text("body").splitlines()
                    if line.strip()
                ]
                blocks = find_english_infinity_blocks(lines)
                if not blocks:
                    print(f"{theater_slug}: no English MS-Infinity Vision match.")
                    continue

                entry = blocks[0]
                showtimes = entry["showtimes"]
                block_text = " | ".join(entry["block"])
                format_label = ", ".join(entry["matched_formats"])
                message = (
                    f"<b>{TARGET_DATE[-2:]} DECEMBER ENGLISH MS-INFINITY VISION ALERT - HYDERABAD!</b>\n\n"
                    f"Avengers: Doomsday English MS-Infinity Vision tickets are now listed.\n"
                    f"<b>Theater:</b> {theater_slug.replace('-', ' ').title()}\n"
                    f"<b>Theater code:</b> {venue_code}\n"
                    f"<b>Format:</b> {format_label}\n"
                    f"<b>Shows:</b> {', '.join(showtimes)}\n"
                    f"<b>Details:</b> <code>{block_text[:280]}</code>\n\n"
                    f"<a href='{theater_url}'>Book on BookMyShow</a>"
                )

                if send_telegram_alert(message):
                    with open(".bms-alert-sent", "w", encoding="utf-8") as marker:
                        marker.write(TARGET_DATE)
                    browser.close()
                    return True

            except Exception as theater_error:
                print(
                    f"Could not check theater {venue_code}: {theater_error}"
                )

        browser.close()
        return False


def get_theater_urls(page):
    theater_urls = {}
    for theater_slug, _theater_base_url, venue_code in TARGET_THEATER_PAGES:
        target_url = (
            f"https://in.bookmyshow.com/cinemas/hyderabad/"
            f"{theater_slug}/buytickets/{venue_code}/{TARGET_DATE}"
        )
        theater_urls[target_url] = (venue_code, theater_slug)

    return theater_urls


def monitor_december_21():
    print(
        f"Monitoring Prasads, AAA Cinemas, and AMB Cinemas for English Avengers: Doomsday "
        f"MS-Infinity Vision on {TARGET_DATE}."
    )
    print(f"Cinema listing: {CINEMAS_URL}")
    print(f"Checking every {CHECK_INTERVAL_SECONDS} seconds.")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        while True:
            try:
                theater_urls = get_theater_urls(page)
                print(
                    f"[{time.strftime('%H:%M:%S')}] "
                    f"Checking {len(theater_urls)} Hyderabad theaters..."
                )

                for theater_url, (venue_code, theater_slug) in theater_urls.items():
                    try:
                        page.goto(theater_url, wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(2500)

                        current_url = page.url
                        if TARGET_DATE not in current_url:
                            continue

                        content = page.inner_text("body")
                        lines = [
                            line.strip()
                            for line in content.splitlines()
                            if line.strip()
                        ]
                        blocks = find_english_infinity_blocks(lines)
                        if not blocks:
                            any_movie = any(
                                MOVIE_KEYWORD in line.lower()
                                for line in lines
                            )
                            if any_movie:
                                print(
                                    f"[{time.strftime('%H:%M:%S')}] "
                                    f"{theater_slug}: Doomsday is listed, but no "
                                    "English MS-Infinity Vision match."
                                )
                            elif TARGET_DATE in current_url:
                                print(
                                    f"[{time.strftime('%H:%M:%S')}] "
                                    f"{theater_slug}: date page live, "
                                    "Doomsday is not listed yet."
                                )
                            continue

                        entry = blocks[0]
                        showtimes = entry["showtimes"]
                        block_text = " | ".join(entry["block"])
                        format_label = ", ".join(entry["matched_formats"])

                        message = (
                            f"<b>{TARGET_DATE[-2:]} DECEMBER ENGLISH MS-INFINITY VISION ALERT - HYDERABAD!</b>\n\n"
                            f"Avengers: Doomsday English MS-Infinity Vision tickets are now listed.\n"
                            f"<b>Theater:</b> {theater_slug.replace('-', ' ').title()}\n"
                            f"<b>Theater code:</b> {venue_code}\n"
                            f"<b>Format:</b> {format_label}\n"
                            f"<b>Shows:</b> {', '.join(showtimes)}\n"
                            f"<b>Details:</b> <code>{block_text[:280]}</code>\n\n"
                            f"<a href='{theater_url}'>Book on BookMyShow</a>"
                        )

                        print(
                            f"[{time.strftime('%H:%M:%S')}] "
                            f"{TARGET_DATE[-2:]} Dec tickets found at theater {venue_code}: "
                            f"{', '.join(showtimes)}"
                        )
                        if send_telegram_alert(message):
                            print("Alert delivered. Monitoring stopped.")
                            browser.close()
                            return

                        print("Telegram delivery failed. Retrying monitoring.")

                    except Exception as theater_error:
                        print(
                            f"[{time.strftime('%H:%M:%S')}] "
                            f"Could not check theater {venue_code}: {theater_error}"
                        )

            except Exception as error:
                print(
                    f"[{time.strftime('%H:%M:%S')}] "
                    f"Check failed (retrying): {error}"
                )

            time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test_mode()
    elif "--check-one-shot" in sys.argv:
        run_one_shot_check()
    else:
        monitor_december_21()
