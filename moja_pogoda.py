#!/usr/bin/env python3
# Moja Pogoda - prosta astro prognoza pogody w CLI (Open-Meteo, bez klucza)
# Przykłady:
#   ./pogoda --now --krakow
#   ./pogoda --tonight --glebokie

import argparse
from datetime import datetime, timedelta
import sys, time, itertools
import requests

API_GEO =   "https://geocoding-api.open-meteo.com/v1/search"
API_FC  =   "https://api.open-meteo.com/v1/forecast"

RESET = "\x1b[0m"; DIM = "\x1b[2m"; BOLD = "\x1b[1m"
SPINNER = ["|", "/", "-", "\\"]

# ============================= MAŁE, CZYTELNE KLOCKI =============================

def spin(msg, secs=1.5, fps=8):
    it = itertools.cycle(SPINNER); end = time.time()+secs
    while time.time() < end:
        sys.stdout.write(f"\r{DIM}{next(it)}{RESET} {msg}"); sys.stdout.flush()
        time.sleep(1.0/fps)
    sys.stdout.write("\r" + " "*(len(msg)+4) + "\r")

def geocode(city: str):
    r = requests.get(API_GEO, params={"name": city, "count": 1}, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data.get("results"):
        raise SystemExit(f"Nie znaleziono miasta: {city}")
    res = data["results"][0]
    return {"name": f"{res['name']}, {res.get('country_code','')}",
            "lat": res["latitude"], "lon": res["longitude"]}

def fetch(lat, lon, tz="auto"):
    params = {
        "latitude": lat, "longitude": lon, "timezone": tz,
        "hourly": "cloudcover,visibility,wind_speed_10m,temperature_2m",
        "daily": "sunrise,sunset",
        "current": "temperature_2m,apparent_temperature,is_day,precipitation,cloud_cover,wind_speed_10m,wind_direction_10m,visibility",
    }
    r = requests.get(API_FC, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def astro_score(cloud, wind, vis_km):
    # prosta heurystyka 0..100: mało chmur + niewielki wiatr + dobra widoczność
    base = 100 - cloud
    wind_pen = max(0, (wind-15)*1.5)
    vis_boost = min(10, max(0, (vis_km - 5)))
    return max(0, min(100, int(base - wind_pen + vis_boost)))

def bar(score, width=12):
    filled = int(round(score/100*width))
    return "★"*filled + "."*(width-filled)

def fmt_dir(deg):
    if deg is None: return "—"
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((deg%360)/45+0.5)%8]

def tonight_indexes(times):
    dt = [datetime.fromisoformat(t) for t in times]
    if not dt: return list(range(len(times)))
    today = dt[0].date()
    start = datetime.combine(today, datetime.min.time()).replace(hour=18)
    end   = datetime.combine(today+timedelta(days=1), datetime.min.time()).replace(hour=8)
    idxs  = [i for i,t in enumerate(dt) if (t >= start and t < end)]
    return idxs or list(range(len(times)))

# ============================= PROGRAM GŁÓWNY =============================

def parse_args():
    ap = argparse.ArgumentParser(description="Prosta astro-pogoda (Open-Meteo).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--krakow", action="store_true", help="Skrót: Kraków")
    g.add_argument("--glebokie", action="store_true", help="Skrót: Głębokie gm. Uścimów")
    ap.add_argument("--city", help="Inne miasto (np. 'Warsaw' / 'Cracow').")
    ap.add_argument("--lat", type=float, help="Szerokość geograficzna.")
    ap.add_argument("--lon", type=float, help="Długość geograficzna.")
    ap.add_argument("--now", action="store_true", help="Pokaż warunki teraz (przydatne przed wyjściem z domu).")
    ap.add_argument("--tonight", action="store_true", help="Pokaż prognozę na dzisiejszą noc (18.00-6.00)")
    ap.add_argument("--limit", type=int, default=None, help="Ile wierszy maks. (domyślnie cała noc do 7.00)")
    return ap.parse_args()

def resolve_location(args):
    if args.lat is not None and args.lon is not None:
        return {"name": f"{args.lat:.3f},{args.lon:.3f}", "lat": args.lat, "lon": args.lon}
    if args.krakow:     return geocode("Kraków")
    if args.glebokie:   return {
        "name": "Głębokie gm. Uścimów",
        "lat": 51.478611,
        "lon": 22.923333
    }
    if args.city:       return geocode(args.city)
    return geocode("Lublin")

def show_now(fc, locname):
    cur = fc.get("current", {})
    T   = cur.get("temperature_2m")
    Tw  = cur.get("apparent_temperature")
    CC  = cur.get("cloud_cover")
    WS  = cur.get("wind_speed_10m")
    WD  = cur.get("wind_direction_10m")
    VI  = cur.get("visibility") # metry
    is_day = cur.get("is_day")
    vis_km = (VI/1000.0) if isinstance(VI,(int,float)) else 10.0
    cloud = int(round(CC)) if isinstance(CC,(int,float)) else 50
    wind  = float(WS) if isinstance(WS,(int,float)) else 5.0
    score = astro_score(cloud, wind, vis_km)

    print(f"{BOLD}Warunki obecnie — {locname}{RESET}")
    print(f"{DIM}(Czas lokalny wg API){RESET}")
    print(f"Chmury: {cloud:>3d}%    Wiatr: {wind:>4.1f} km/h {fmt_dir(WD)}  "
          f"Widoczność: {vis_km:>4.1f} km   Temperatura: {T if T is not None else '—'}°C    "
          f"Odczuwalna.: {Tw if Tw is not None else '—'}°C")
    if is_day == 0:  # tylko noc
        print(f"Score: {score:>3d} {bar(score, 20)}\n")
    else:
        print(f"{DIM}Dzień — astro-score nie wyliczany{RESET}\n")

def show_tonight(fc, limit):
    h = fc["hourly"]
    times = h["time"]; cloud = h["cloudcover"]; wind = h["wind_speed_10m"]
    vis = h.get("visibility"); temp = h.get("temperature_2m")
    idxs = tonight_indexes(times)

    print(f"{'Godz':<5} {'Chmury%':>7} {'Wiatr[km/h]':>12} {'Widoczność[km]':>11} {'Temperatura':>7}°C {'Warunki obserwacyjne':>7}")
    print("-"*68)
    shown = 0
    best = (-1, None)
    for i in idxs:
        if limit is not None and shown >= limit:
            break
        t   = datetime.fromisoformat(times[i])
        cc  = int(round(cloud[i])); ws = float(wind[i])
        vk  = None if (vis is None or vis[i] is None) else (vis[i]/1000.0)
        tp  = temp[i] if (temp and temp[i] is not None) else None
        sc  = astro_score(cc, ws, vk if vk is not None else 10.0)
        if sc > best[0]: best = (sc, t)
        vk_txt = f"{vk:>5.1f}" if vk is not None else " n/a"
        tp_txt = f"{tp:>5.1f}" if tp is not None else " n/a"
        print(f"{t.strftime('%H:%M'):>5} {cc:>7d} {ws:>12.1f} {vk_txt:>11} {tp_txt:>7} {sc:>7d} {bar(sc)}")
        shown += 1
    if best[1]:
        print("\n" + BOLD + f"Najlepsza godzina: {best[1].strftime('%Y-%m-%d %H:%M')} (score {best[0]})" + RESET)

def main():
    args = parse_args()
    spin("Ustalam lokalizację...")
    loc = resolve_location(args)
    spin(f"Pobieram prognozę dla {loc['name']} ...")
    fc = fetch(loc["lat"], loc["lon"])

    print(f"{BOLD}Astro-Pogoda — {loc['name']}{RESET}\n")

    if args.now:
        show_now(fc, loc["name"])
        # jeśli tylko snapshot - skończ
        if not args.tonight:
            return

    if args.tonight:
        print(f"{DIM}Dzisiejsza noc (ok. 18.00-6.00){RESET}\n")
        show_tonight(fc, args.limit)

    if not (args.now or args.tonight):
        # domyślnie pokaż snapshot, jak nic nie podano
        show_now(fc, loc["name"])

if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:
        print(f"⚠️ Błąd sieci/API: {e}")
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nPrzerwano.")
