import asyncio
import logging
import os
import requests
from bs4 import BeautifulSoup
from telegram import Bot

TOKEN = os.environ.get("8553481078:AAF85WofRd8-7jaLf8d3XEF_-pLA9-v-YoY")
CHAT_ID = os.environ.get("8553481078")

logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )
}

STORES = {
    "kruti": "https://kruti.com.ua/ua/pokryshka-schwalbe-smart-sam-29x2.35/",
    "rozetka": "https://rozetka.com.ua/ua/schwalbe-tir-61-47/p426701688/",
    "veliki": "https://veliki.ua/pokryshka-29-smart-sam/",
    "veloplaneta": "https://veloplaneta.ua/ua/pokryshka-29x2-35-60-622-schwalbe-smart-sam-perf-b-brz-sk-hs624-addix-67epi",
    "velosiped": "https://velosiped.com/katalog/shiny/schwalbe/smart-sam-29.html",
    "velopuls": "https://velopuls.ua/schwalbe-smart-sam-29.html"
}


def fetch_price(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except Exception as e:
        logging.warning(f"{url}: {e}")
        return None, "request-failed"

    soup = BeautifulSoup(r.text, "lxml")

    # JSON-LD
    ld = soup.find("script", {"type": "application/ld+json"})
    if ld:
        try:
            import json
            data = json.loads(ld.text)
            if isinstance(data, dict) and "offers" in data:
                price = float(data["offers"]["price"])
                return price, "json-ld"
        except Exception:
            pass

    # Meta price itemprop
    meta_price = soup.find("meta", {"itemprop": "price"})
    if meta_price and meta_price.get("content"):
        return float(meta_price["content"]), "meta:itemprop"

    # OG price
    meta_og = soup.find("meta", {"property": "product:price:amount"})
    if meta_og and meta_og.get("content"):
        return float(meta_og["content"]), "meta:og-price"

    return None, "not-found"


async def send_message(text):
    if not TOKEN or not CHAT_ID:
        logging.error("TOKEN or CHAT_ID missing!")
        return

    bot = Bot(token=TOKEN)
    try:
        await bot.send_message(chat_id=CHAT_ID, text=text)
        logging.info("Message sent.")
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")


async def main():
    logging.info("START CHECK")

    prices = {}

    for store, url in STORES.items():
        price, method = fetch_price(url)
        logging.debug(f"{store}: price={price} method={method}")

        if price:
            prices[store] = price

    if not prices:
        await send_message("⛔ Не удалось получить цены ни в одном магазине!")
        return

    best_store = min(prices, key=prices.get)
    best_price = prices[best_store]

    msg = f"🔥 Лучшая цена: *{best_price} грн*\nмагазин: {best_store}\n\n"
    msg += "\n".join([f"{k}: {v} грн" for k, v in prices.items()])

    await send_message(msg)


if __name__ == "__main__":
    asyncio.run(main())
