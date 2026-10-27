"""Collect public ActiveSG gym/pool capacities; never guess missing measurements.

The public interface is dynamic. Parse rendered cards and, when discoverable,
public JSON responses. If the page changes, exit with an error and preserve data.
"""
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://activesg.gov.sg/gym-pool-crowd"
TZ = ZoneInfo("Asia/Singapore")
PERCENT = re.compile(r"(?<!\d)(100|[1-9]?\d)\s*%")
STATUS = re.compile(r"\b(closed|temporarily closed|full|open)\b", re.I)
FACILITY = re.compile(r"gym|swimming|pool|sport centre|sports centre", re.I)
NOISE = re.compile(r"^(all|gyms?|pools?|filter|search|occupancy|capacity|open|closed|view|details|location)$", re.I)


def slug(name):
    value = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return value[:100]


def infer_type(name, hint=""):
    txt = f"{name} {hint}".lower()
    if "swim" in txt or "pool" in txt:
        return "pool"
    if "gym" in txt:
        return "gym"
    return hint if hint in ("gym", "pool") else "unknown"


def normalize(name, display, hint="", source="rendered"):
    name = re.sub(r"\s+", " ", str(name or "")).strip(" -:|")
    display = re.sub(r"\s+", " ", str(display or "")).strip()
    if not (4 <= len(name) <= 115) or NOISE.fullmatch(name):
        return None
    m = PERCENT.search(display)
    occupancy = int(m.group(1)) if m else None
    lower = display.lower()
    if occupancy is None and not ("closed" in lower or "full" in lower):
        return None
    typ = infer_type(name, hint)
    if typ == "unknown" and not FACILITY.search(name):
        return None
    status = "closed" if "closed" in lower else "full" if "full" in lower and occupancy is None else "open"
    if status == "closed":
        occupancy = None
    # "Full" is not automatically 100%: preserve what the provider explicitly says.
    return dict(id=f"{typ}-{slug(name)}", name=name, type=typ, pct=occupancy,
                status=status, display=display[:120], source=source)


def parse_card_lines(text, hint=""):
    """Card text usually places venue name before a capacity badge."""
    lines = [re.sub(r"\s+", " ", s).strip() for s in text.splitlines()]
    lines = [s for s in lines if s]
    if len(lines) > 22 or len(text) > 550:
        return None
    marker = next((s for s in lines if PERCENT.search(s) or
                   re.search(r"\bclosed\b|\bfull\b", s, re.I)), None)
    if not marker:
        return None
    possible = [s for s in lines if s != marker and
                4 <= len(s) <= 115 and not PERCENT.search(s) and
                not NOISE.fullmatch(s) and not re.match(r"^(?:as of|updated|capacity|occupancy|open now)", s, re.I)]
    if not possible:
        return None
    # Names normally occur at the start of each provider card.
    names = [s for s in possible if FACILITY.search(s)]
    name = (names or possible)[0]
    return normalize(name, marker, hint)


def parse_json_objects(obj, hint="", depth=0):
    """Conservatively examine public page responses for obvious venue/capacity records."""
    if depth > 8:
        return []
    found = []
    if isinstance(obj, list):
        for el in obj:
            found.extend(parse_json_objects(el, hint, depth + 1))
    elif isinstance(obj, dict):
        keyset = {str(k).lower(): k for k in obj}
        name = next((obj[keyset[k]] for k in ("venue_name", "facility_name", "gym_name", "pool_name", "outlet_name", "name")
                     if k in keyset and isinstance(obj[keyset[k]], str)), None)
        pct = next((obj[keyset[k]] for k in ("occupancy_percentage", "occupancypercent", "occupancy_percent", "capacity_percentage", "capacity_percent", "percentage", "occupancy")
                    if k in keyset), None)
        status = next((obj[keyset[k]] for k in ("status", "availability_status") if k in keyset), "")
        if name is not None and (pct is not None or status):
            pct_text = f"{pct}%" if isinstance(pct, (int, float)) and 0 <= pct <= 100 else str(pct or "")
            val = normalize(name, f"{pct_text} {status}", hint=hint, source="page-json")
            if val:
                found.append(val)
        for v in obj.values():
            if isinstance(v, (dict, list)):
                found.extend(parse_json_objects(v, hint, depth + 1))
    return found


def dedupe(items):
    out = {}
    for item in items:
        if not item:
            continue
        # Prefer explicit readings over closure-only if both are on page.
        prior = out.get(item["id"])
        if not prior or (prior["pct"] is None and item["pct"] is not None):
            out[item["id"]] = item
    return list(out.values())


def scrape():
    from playwright.sync_api import sync_playwright
    records, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1380, "height": 1000},
                                user_agent="ActiveSGCrowdResearch/1.0 (+https://github.com/spacecadet00/data)")
        def on_response(response):
            if response.status != 200 or not re.search(r"activesg|api", response.url, re.I):
                return
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return
            try:
                obj = response.json()
                records.extend(parse_json_objects(obj))
            except Exception:
                pass
        page.on("response", on_response)
        try:
            page.goto(SOURCE, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            for hint in ("gym", "pool"):
                # Switch only if a specifically labeled tab/button exists; do not
                # click arbitrary text that merely includes "gym" or "pool".
                selectors = [
                    f'[role="tab"]:has-text("{hint}")',
                    f'button:has-text("{hint.title()}")',
                ]
                for sel in selectors:
                    try:
                        item = page.locator(sel).first
                        if item.count() and item.is_visible() and len(item.inner_text()) < 25:
                            item.click(timeout=2500)
                            page.wait_for_timeout(1200)
                            break
                    except Exception:
                        continue
                selectors = [
                    ".chakra-card__body", "[data-testid*='facility-card']",
                    "[data-testid*='gym-card']", "[data-testid*='pool-card']",
                    "article", ".chakra-card",
                ]
                for selector in selectors:
                    try:
                        for card in page.locator(selector).all()[:250]:
                            rec = parse_card_lines(card.inner_text(timeout=1000), hint)
                            if rec:
                                records.append(rec)
                    except Exception as exc:
                        errors.append(f"{selector}: {exc}")
                # Fallback: find small DOM containers containing a percentage.
                # Never parse the whole page as a single record.
                raw = page.evaluate("""() => {
                  const nodes = Array.from(document.querySelectorAll("main p, main span, main strong, main h3, main h4, article p, article span"));
                  const out = [];
                  for (const node of nodes) {
                    if (!/(?:\\d{1,3}\\s*%|\\bClosed\\b)/i.test(node.innerText || "")) continue;
                    let ancestor = node.parentElement;
                    for (let i = 0; i < 4 && ancestor; i++, ancestor = ancestor.parentElement) {
                      const value = ancestor.innerText || "";
                      if (value.length >= 10 && value.length < 400 && value.includes("\\n")) {
                        out.push(value); break;
                      }
                    }
                  }
                  return out.slice(0, 400);
                }""")
                for txt in raw:
                    rec = parse_card_lines(txt, hint)
                    if rec:
                        records.append(rec)
        finally:
            browser.close()
    records = dedupe(records)
    # Fail closed when no credible outlet records can be extracted.
    if len(records) < 4:
        raise RuntimeError(f"Only {len(records)} credible outlet records from {SOURCE}; parsing or access may have changed. No data written. Details: {errors[:3]}")
    return records


def read_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def geocode_one(metadata):
    """One cached OpenStreetMap Nominatim lookup per run, never bulk per-poll."""
    import requests
    now = datetime.now(TZ)
    for venue in metadata.values():
        if venue.get("lat") is not None:
            continue
        attempted = venue.get("geocode_attempt_date")
        if attempted:
            try:
                if (now.date() - datetime.fromisoformat(attempted).date()).days < 14:
                    continue
            except ValueError:
                pass
        venue["geocode_attempt_date"] = now.date().isoformat()
        query = f"{venue['name']}, Singapore"
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": query, "format": "jsonv2", "countrycodes": "sg", "limit": 1},
                headers={"User-Agent": "ActiveSGCrowdResearch/1.0 (https://github.com/spacecadet00/data)"},
                timeout=8,
            )
            response.raise_for_status()
            matches = response.json()
            if matches:
                m = matches[0]
                lat, lon = float(m["lat"]), float(m["lon"])
                if 1.15 <= lat <= 1.48 and 103.58 <= lon <= 104.12:
                    venue.update(lat=lat, lon=lon, location_source="nominatim")
        except Exception as exc:
            print(f"Geocoding unavailable for {query}: {exc}", file=sys.stderr)
        break


def collect():
    now = datetime.now(TZ)
    config = read_json(ROOT / "config.json", {})
    start = datetime.fromisoformat(config["start_inclusive"])
    end = datetime.fromisoformat(config["end_exclusive"])
    if not (start <= now < end):
        print(f"Collection stopped: outside {start.isoformat()} to {end.isoformat()}")
        return
    if not (6 <= now.hour < 23):
        print("Outside sampling window 06:00–23:00 SGT")
        return
    records = scrape()
    metadata_path = ROOT / "data" / "outlets.json"
    live_path = ROOT / "data" / "live.json"
    day_path = ROOT / "data" / "raw" / (now.strftime("%Y-%m-%d") + ".csv")
    day_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = read_json(metadata_path, {})
    for r in records:
        item = metadata.get(r["id"], {})
        item.update(id=r["id"], name=r["name"], type=r["type"])
        metadata[r["id"]] = item
    geocode_one(metadata)
    # Deduplicate approximate scheduled slot in case of manual/retry run.
    slot = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    slot_id = slot.isoformat(timespec="minutes")
    existing = set()
    if day_path.exists():
        with day_path.open(newline="", encoding="utf-8") as f:
            existing = {(r["ts"], r["id"]) for r in csv.DictReader(f)}
    with day_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if day_path.stat().st_size == 0:
            writer.writerow(("ts", "id", "pct", "status"))
        for r in records:
            if (slot_id, r["id"]) not in existing:
                writer.writerow((slot_id, r["id"], "" if r["pct"] is None else r["pct"], r["status"]))
    live = {"observed_at": now.isoformat(timespec="seconds"), "source": SOURCE,
            "outlets": {r["id"]: {"pct": r["pct"], "status": r["status"]} for r in records}}
    live_path.parent.mkdir(parents=True, exist_ok=True)
    live_path.write_text(json.dumps(live, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(records)} outlet readings at {slot_id}. Location coverage: {sum(v.get('lat') is not None for v in metadata.values())}/{len(metadata)}")


if __name__ == "__main__":
    collect()
