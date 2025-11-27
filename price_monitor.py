import requests
import json
import os
import argparse
from bs4 import BeautifulSoup
from datetime import datetime
from telegram import Bot

TOKEN = "8553481078:AAF85WofRd8-7jaLf8d3XEF_-pLA9-v-YoY"
CHAT_ID = 5286549684
HISTORY_FILE = "history.json"

SITES = {
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

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {"min_all_time": 999999, "morning_price": None}
    with open(HISTORY_FILE, "r") as f:
        return json.load(f)

def save_history(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f)

def parse_price(url):
    try:
        r = requests.get(url, timeout=12)
    except:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    selectors = [
        ".price", ".product-price", ".price-number", ".price__value",
        ".product-prices__big", ".product__price", ".price_value"
    ]

    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            text = el.get_text().strip()
            text = text.replace("₴", "").replace("грн", "").replace(" ", "")
            try:
                return float(text)
            except:
                continue

    return None

def check_prices():
    best = None  # (price, key, url)

    for key, url in SITES.items():
        price = parse_price(url)
        if price is not None:
            if best is None or price < best[0]:
                best = (price, key, url)

    return best  # None или (цена, ключ, урл)

def send(msg):
    Bot(TOKEN).send_message(chat_id=CHAT_ID, text=msg)

def morning_check(history):
    result = check_prices()
    if not result:
        send("❗️Утром нет ни одного магазина с товаром в наличии.")
        return

    price, key, url = result
    shop = SITE_NAMES[key]

    history["morning_price"] = price

    send(
        f"🌅 Утренний мониторинг\n"
        f"Минимальная цена: {price} грн\n"
        f"Магазин: {shop}\n"
        f"Ссылка: {url}"
    )

    save_history(history)

def afternoon_check(history):
    result = check_prices()
    if not result:
        return

    price, key, url = result
    shop = SITE_NAMES[key]

    morning_price = history.get("morning_price", None)
    min_all_time = history.get("min_all_time", 999999)

    changed = False
    msg = f"📉 Снижение цены!\n"
    msg += f"Магазин: {shop}\nСсылка: {url}\n"

    if morning_price and price < morning_price:
        msg += f"— Ниже утренней: {morning_price} → {price} грн\n"
        changed = True

    if price < min_all_time:
        msg += f"— Новый исторический минимум: {min_all_time} → {price} грн\n"
        history["min_all_time"] = price
        changed = True

    if changed:
        send(msg)

    save_history(history)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--morning", action="store_true")
    parser.add_argument("--afternoon", action="store_true")
    args = parser.parse_args()

    history = load_history()

    if args.morning:
        morning_check(history)
    elif args.afternoon:
        afternoon_check(history)
    else:
        result = check_prices()
        if result:
            price, key, url = result
            shop = SITE_NAMES[key]
            send(f"Текущая минимальная цена: {price} грн\nМагазин: {shop}\n{url}")
        else:
            send("Нет магазинов с товаром.")