#!/usr/bin/env python3
# price_monitor.py
# Usage:
#   python3 price_monitor.py --morning
#   python3 price_monitor.py --afternoon
#   python3 price_monitor.py            # quick manual run (sends current min if any)

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from typing import Optional, Tuple, Dict

import requests
from bs4 import BeautifulSoup
from telegram import Bot

# ---------------- CONFIG ----------------
TOKEN = "8553481078:AAF85WofRd8-7jaLf8d3XEF_-pLA9-v-YoY"
# replace with your chat id if needed; otherwise ensure you /start the bot at least once
CHAT_ID = 5286549684

HISTORY_FILE = "history.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
REQUEST_TIMEOUT = 15

SITES: Dict[str, str] = {
    "kruti": "https://kruti.com.ua/pokryshka-schwalbe-TIR-61-47.html",
    "rozetka": "https://rozetka.com.ua/ua/schwalbe-tir-61-47/p426701688/",
    "veliki": "https://veliki.com.ua/goods_tire-schwalbe-smart-sam-27-5-2-25.htm#black_brown",
    "veloplaneta": "https://veloplaneta.ua/ua/pokryshka-29x2-35-60-622-schwalbe-smart-sam-perf-b-brz-sk-hs624-addix-67epi",
    "velosiped": "https://velosiped.com/ru/pokrishka-schwalbe-smart-sam-performance-29x225-57-622-bbrz-sk-addix-11159464",
    "velopuls": "https://velopuls.ua/ua/product/pokryshka-275-schwalbe-smart-sam-235-hs476-bronze-60-584-/"
}

SITE_NAMES = {
    "kruti": "Kruti",
    "rozetka": "Rozetka",
    "veliki": "Veliki",
    "veloplaneta": "Veloplaneta",
    "velosiped": "Velosiped",
    "velopuls": "Velopuls"
}
# ----------------------------------------

# small helpers
def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"  # safe simple iso


def load_history() -> dict:
    if not os.path.exists(HISTORY_FILE):
        return {"min_all_time": None, "morning_price": None}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"min_all_time": None, "morning_price": None}


def save_history(h: dict):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)


def http_get(url: str) -> Optional[str]:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9,uk;q=0.8,en;q=0.7"}
    try:
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[WARN] Request failed for {url}: {e}", file=sys.stderr)
        return None


def _num_from_str(s: str) -> Optional[float]:
    if not s:
        return None
    s = s.replace("\xa0", " ").strip()
    # remove currency symbols and letters
    s = re.sub(r"[^\d,.\s]", "", s)
    s = s.replace(" ", "")
    # normalize separators
    if s.count(",") > 0 and s.count(".") == 0:
        s = s.replace(",", ".")
    if s.count(",") > 0 and s.count(".") > 0:
        if s.find(",") < s.find("."):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def parse_price_from_text(text: str) -> Optional[float]:
    # try patterns with currency
    patterns = [
        r"([\d\.,\s]+)\s*(?:грн|грн\.|гривн|UAH|₴)",
        r"₴\s*([\d\.,\s]+)",
        r"price\":\s*\"?([\d\.,\s]+)\"?"
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            v = _num_from_str(m.group(1))
            if v:
                return v
    # fallback: first big-looking number
    nums = re.findall(r"[\d\.,\s]{2,}", text)
    cand = []
    for n in nums:
        v = _num_from_str(n)
        if v and v > 10:
            cand.append(v)
    if cand:
        return sorted(cand)[0]
    return None


def extract_price(url: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Extract price and return (price, method_info).
    If no price or product absent, return (None, reason).
    """
    html = http_get(url)
    if not html:
        return None, "request-failed"
    soup = BeautifulSoup(html, "lxml")

    # 1) JSON-LD
    for s in soup.find_all("script", type="application/ld+json"):
        txt = s.string or ""
        p = parse_price_from_text(txt)
        if p:
            return p, "json-ld"

    # 2) meta tags
    metas = [('meta', {'property': 'product:price:amount'}),
             ('meta', {'name': 'price'}),
             ('meta', {'itemprop': 'price'})]
    for tag, attrs in metas:
        t = soup.find(tag, attrs=attrs)
        if t and t.get("content"):
            v = _num_from_str(t["content"])
            if v:
                return v, f"meta:{attrs}"

    # 3) common selectors
    selectors = ['[itemprop="price"]', '.price', '.product-price', '.price__value',
                 '.product__price', '.price-new', '.price_value', '.product-prices__big']
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            txt = el.get_text(" ", strip=True)
            v = parse_price_from_text(txt)
            if v:
                return v, f"sel:{sel}"

    # 4) final full-text
    v = parse_price_from_text(soup.get_text(" ", strip=True))
    if v:
        return v, "fulltext"

    # If we reached here — treat as "not available / no price"
    return None, "not-found"


def check_all_sites() -> Optional[Tuple[float, str, str]]:
    """
    Return tuple (price, key, url) of the best (min) available price,
    or None if no site has the product in stock / price.
    """
    best = None  # (price, key, url)
    for key, url in SITES.items():
        price, method = extract_price(url)
        print(f"[DEBUG] {key}: price={price} method={method}")
        if price is not None:
            if best is None or price < best[0]:
                best = (price, key, url)
    return best


# Async telegram send wrappers (PTB 20.x is async)
async def _async_send(msg: str):
    bot = Bot(TOKEN)
    try:
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="HTML")
    except Exception as e:
        # As fallback, print to stdout/stderr
        print(f"[ERROR] Failed to send Telegram message: {e}", file=sys.stderr)


def send_message(msg: str):
    # run the async send and wait until completion
    try:
        asyncio.run(_async_send(msg))
    except Exception as e:
        print(f"[ERROR] asyncio.run failed: {e}", file=sys.stderr)


# ---------------- Main flows ----------------
def morning_flow(history: dict):
    best = check_all_sites()
    if not best:
        send_message("❗️ Утренний мониторинг: ни один магазин сейчас не показал цену (товар отсутствует).")
        return
    price, key, url = best
    shop = SITE_NAMES.get(key, key)
    history["morning_price"] = price
    msg = (f"🌅 <b>Утренний мониторинг</b>\n"
           f"Минимальная текущая цена: <b>{price:.2f} грн</b>\n"
           f"Магазин: {shop}\n{url}")
    send_message(msg)
    save_history(history)


def afternoon_flow(history: dict):
    best = check_all_sites()
    if not best:
        # молчим если ничего нет
        print("[INFO] Afternoon: no available prices, nothing to do.")
        return
    price, key, url = best
    shop = SITE_NAMES.get(key, key)

    morning_price = history.get("morning_price")
    min_all_time = history.get("min_all_time")

    changed = False
    msg_lines = [f"📉 <b>Проверка в 13:00</b>\nМагазин: {shop}\n{url}"]
    if morning_price is not None and price < morning_price:
        msg_lines.append(f"— Ниже утренней: {morning_price:.2f} → {price:.2f} грн")
        changed = True
    if min_all_time is None or price < min_all_time:
        msg_lines.append(f"— Новый исторический минимум: {min_all_time if min_all_time is not None else '—'} → {price:.2f} грн")
        history["min_all_time"] = price
        changed = True

    if changed:
        send_message("\n".join(msg_lines))
    else:
        print(f"[INFO] No new low. Current {price:.2f}, morning {morning_price}, hist {min_all_time}")

    save_history(history)


def quick_run(history: dict):
    best = check_all_sites()
    if not best:
        send_message("Нет магазинов с товаром.")
        return
    price, key, url = best
    shop = SITE_NAMES.get(key, key)
    send_message(f"Текущая минимальная цена: {price:.2f} грн\nМагазин: {shop}\n{url}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--morning", action="store_true")
    parser.add_argument("--afternoon", action="store_true")
    args = parser.parse_args()

    history = load_history()

    if args.morning:
        morning_flow(history)
    elif args.afternoon:
        afternoon_flow(history)
    else:
        quick_run(history)


if __name__ == "__main__":
    main()
