#!/usr/bin/env python3
import os
import json
import urllib.request
import time

import pixel_common

CONFIG_PATH = pixel_common.config_path("weather-config.json")
CACHE_PATH = pixel_common.cache_path("weather-cache.json")

# Default fallback coordinates (Rome, Italy)
DEFAULT_CITY = "Rome"
DEFAULT_LAT = 41.9028
DEFAULT_LON = 12.4964

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "auto_location": True,
        "manual_city": DEFAULT_CITY,
        "manual_lat": DEFAULT_LAT,
        "manual_lon": DEFAULT_LON
    }

def load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(data):
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def fetch_ip_location():
    providers = [
        # Provider 1: ipwho.is (Free, HTTPS, highly reliable)
        (
            "https://ipwho.is/",
            lambda d: (d.get("city"), float(d.get("latitude")), float(d.get("longitude")))
            if d.get("success") else None
        ),
        # Provider 2: ip-api.com
        (
            "http://ip-api.com/json/",
            lambda d: (d.get("city"), float(d.get("lat")), float(d.get("lon")))
            if d.get("status") == "success" else None
        ),
        # Provider 3: ipinfo.io
        (
            "https://ipinfo.io/json",
            lambda d: (d.get("city"), float(d.get("loc").split(",")[0]), float(d.get("loc").split(",")[1]))
            if "loc" in d and "," in d["loc"] else None
        )
    ]

    for url, parser in providers:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
            )
            with urllib.request.urlopen(req, timeout=3) as res:
                raw = json.loads(res.read().decode("utf-8"))
                parsed = parser(raw)
                if parsed and parsed[0] and parsed[1] is not None and parsed[2] is not None:
                    return {
                        "city": parsed[0],
                        "lat": parsed[1],
                        "lon": parsed[2]
                    }
        except Exception:
            continue
    return None

def get_weather():
    config = load_config()
    cache = load_cache()

    city = DEFAULT_CITY
    lat = DEFAULT_LAT
    lon = DEFAULT_LON

    # Check if manual mode or auto mode
    if not config.get("auto_location", True):
        city = config.get("manual_city", DEFAULT_CITY)
        lat = config.get("manual_lat", DEFAULT_LAT)
        lon = config.get("manual_lon", DEFAULT_LON)
    else:
        # Auto-detect via multi-provider IP geolocation; fall back to the
        # last known location, then to Rome (Italy).
        detected = fetch_ip_location()
        if detected:
            city = detected["city"]
            lat = detected["lat"]
            lon = detected["lon"]
            cache["last_location"] = detected
        elif "last_location" in cache:
            city = cache["last_location"].get("city", city)
            lat = cache["last_location"].get("lat", lat)
            lon = cache["last_location"].get("lon", lon)
        # else: keep the Rome defaults

    # Fetch weather forecast from Open-Meteo
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&"
            f"current=temperature_2m,relative_humidity_2m,weather_code,apparent_temperature&"
            f"daily=temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max&"
            f"timezone=auto"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
        )
        with urllib.request.urlopen(req, timeout=4) as wr:
            w = json.loads(wr.read().decode("utf-8"))
            sunrise_str = w['daily']['sunrise'][0].split('T')[-1][:5]
            sunset_str = w['daily']['sunset'][0].split('T')[-1][:5]
            uv_max = w['daily']['uv_index_max'][0]
            res = {
                'city': city,
                'temp': round(w['current']['temperature_2m']),
                'feels': round(w['current']['apparent_temperature']),
                'humidity': w['current']['relative_humidity_2m'],
                'code': w['current']['weather_code'],
                'max': round(w['daily']['temperature_2m_max'][0]),
                'min': round(w['daily']['temperature_2m_min'][0]),
                'sunrise': sunrise_str,
                'sunset': sunset_str,
                'uv': uv_max
            }
            # Save successful response to cache
            cache["last_weather"] = res
            cache["timestamp"] = int(time.time())
            save_cache(cache)
            print(json.dumps(res))
            return
    except Exception as e:
        # If network error, return cached weather if available
        if "last_weather" in cache:
            print(json.dumps(cache["last_weather"]))
            return
        print(json.dumps({'error': str(e)}))

if __name__ == '__main__':
    get_weather()

