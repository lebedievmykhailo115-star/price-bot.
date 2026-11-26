"""
Облачная версия бота: один запуск = одна проверка цен.
Расписание задаёт GitHub Actions (файл .github/workflows/check.yml).
Бот НЕ говорит, что покупать: падение цены не значит, что она скоро вырастет.
"""
import json
import os
import time

import requests
import yfinance as yf

# ---------- Настройки (можно менять) ----------
STOCKS = {"NVDA": "Nvidia", "AAPL": "Apple"}          # тикер: имя
CRYPTO = {"bitcoin": "Bitcoin", "ethereum": "Ethereum",
          "official-trump": "Trump coin"}              # id на coingecko.com: имя
DROP_PERCENT = 5.0       # присылать, если цена упала на столько процентов и больше
COOLDOWN_HOURS = 6       # не повторять уведомление по одной бумаге чаще, чем раз в N часов
# -----------------------------------------------

TOKEN = os.environ.get("TG_TOKEN", "").strip()
CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
STATE_FILE = "state.json"   # тут запоминается, когда бот писал в последний раз


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)


def fmt(price):
    return f"${price:,.2f}" if price >= 1 else f"${price:.6f}"


def send(text):
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                      data={"chat_id": CHAT_ID, "text": text}, timeout=20)
    if not r.ok:
        print("Telegram не принял сообщение:", r.status_code)
    return r.ok


def stock_changes():
    """Изменение цены акции относительно предыдущего закрытия."""
    out = []
    for ticker, name in STOCKS.items():
        for attempt in (1, 2):
            try:
                fi = yf.Ticker(ticker).fast_info
  
          last, prev = float(fi["last_price"]), float(fi["previous_close"])
                out.append((name, last, (last / prev - 1) * 100, "за день"))
                break
            except Exception as e:
                if attempt == 2:
                    print(f"{ticker}: нет данных ({e})")
                else:
                    time.sleep(3)
    return out


def crypto_changes():
    """Изменение цены монеты за последние 24 часа (данные CoinGecko)."""
    out = []
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                         params={"ids": ",".join(CRYPTO), "vs_currencies": "usd",
                                 "include_24hr_change": "true"}, timeout=20)
        data = r.json()
        for coin_id, name in CRYPTO.items():
            info = data.get(coin_id) if isinstance(data, dict) else None
            if info and info.get("usd_24h_change") is not None:
                out.append((name, float(info["usd"]),
                            float(info["usd_24h_change"]), "за 24 часа"))
            else:
                print(f"{name}: нет данных (ответ CoinGecko: {r.status_code})")
    except Exception as e:
        print(f"Крипта: ошибка ({e})")
    return out


def main():
    if not TOKEN or not CHAT_ID:
        print("Нет TG_TOKEN или TG_CHAT_ID: добавьте их в секреты репозитория.")
        return

    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        send("Проверка: облачный бот запущен и работает.")

    state = load_state()
    now = time.time()
    items = stock_changes() + crypto_changes()
    if not items:
        print("Ни одной цены получить не удалось.")

    for name, price, change, period in items:
        print(f"{name}: {fmt(price)} ({change:+.1f}% {period})")
        if change <= -DROP_PERCENT and now - state.get(name, 0) > COOLDOWN_HOURS * 3600:
            text = (f"Цена {name} упала на {abs(change):.1f}% {period}. Сейчас {fmt(price)}.\n"
                    "Это не сигнал покупать: цена может упасть и дальше.")
            if send(text):
                state[name] = now

    save_state(state)


if __name__ == "__main__":
    main()
