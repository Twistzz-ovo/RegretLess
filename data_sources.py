"""Cached access to optional public data sources."""

import json
import re
import ssl
import time
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from model_validation import number


class DataSourceError(Exception):
    def __init__(self, message, code="unavailable", retry_after=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


@lru_cache(maxsize=1)
def _trusted_ssl_context():
    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"] == 0:
        # Some macOS python.org installations have no configured CA bundle.
        # Load the operating system's trusted bundle while retaining normal
        # certificate-chain and hostname verification.
        for name in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt",
                     "/etc/pki/tls/certs/ca-bundle.crt"):
            path = Path(name)
            if path.is_file():
                context.load_verify_locations(cafile=str(path))
                break
    return context


def _http_json(url, timeout, headers):
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout, context=_trusted_ssl_context()) as response:
        body = response.read(2_000_001)
    if len(body) > 2_000_000:
        raise DataSourceError("The data response is too large. Please use manual input.", "invalid_response")
    return json.loads(body.decode("utf-8"))


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    return value.strip()


def _integer(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}.")
    return value


def _coordinates(latitude, longitude):
    return {"latitude": number(latitude, "Latitude", -90, 90),
            "longitude": number(longitude, "Longitude", -180, 180)}


def _time_series(payload, section, fields):
    values = payload[section]
    units = payload[section + "_units"]
    timestamps = values["time"]
    if not isinstance(timestamps, list) or not timestamps:
        raise ValueError("The provider returned no time-series data.")
    if any(not isinstance(stamp, str) or not stamp for stamp in timestamps):
        raise ValueError("The provider returned invalid timestamps.")
    for field in fields:
        if not isinstance(values[field], list) or len(values[field]) != len(timestamps):
            raise ValueError("The provider returned misaligned time-series data.")
        _text(units[field], "Provider unit")
    records = []
    for index, stamp in enumerate(timestamps):
        record = {"time": stamp}
        for field in fields:
            value = values[field][index]
            record[field] = None if value is None else number(value, "Provider value")
        records.append(record)
    if not any(record[field] is not None for record in records for field in fields):
        raise ValueError("The provider returned only missing values.")
    return {"data": records, "unit": {field: units[field] for field in fields},
            "data_time": {"start": timestamps[0], "end": timestamps[-1],
                          "timezone": payload.get("timezone", "UTC")},
            "has_missing_values": any(record[field] is None for record in records for field in fields)}


class FreeDataClient:
    """Low-volume client with in-memory TTL cache and per-host pacing.

    Cache/pacing apply to this client instance. A web app should reuse a single
    instance in its server resource cache; these are not deployment-wide quotas.
    """

    def __init__(self, timeout=8.0, contact_email=None, transport=None, clock=None):
        self.timeout = number(timeout, "Timeout", minimum=0)
        if self.timeout == 0:
            raise ValueError("Timeout must be greater than zero.")
        if contact_email is not None:
            contact_email = _text(contact_email, "Contact email")
            if "\r" in contact_email or "\n" in contact_email or "@" not in contact_email:
                raise ValueError("Contact email must be valid header-safe contact information.")
        self.contact_email = contact_email
        self._transport = transport or _http_json
        self._clock = clock or time.monotonic
        self._cache = {}
        self._last_request = {}
        self._cooldown_until = {}

    def _request(self, url, ttl):
        current = self._clock()
        cached = self._cache.get(url)
        if cached is not None and current - cached[0] < ttl:
            return deepcopy(cached[1]), cached[2], True
        host = urlsplit(url).hostname
        delay = 0.35 if host == "openlibrary.org" and self.contact_email else 1.05
        last = self._last_request.get(host)
        next_allowed = max(self._cooldown_until.get(host, current),
                           current if last is None else last + delay)
        if current < next_allowed:
            raise DataSourceError("Please wait before requesting this provider again, or use manual input.",
                                  "rate_limited", round(next_allowed - current, 2))
        self._last_request[host] = current
        agent = "RegretLess-MathHacks/1.0"
        if self.contact_email:
            agent += f" (contact: {self.contact_email})"
        try:
            payload = self._transport(url, self.timeout,
                                      {"User-Agent": agent, "Accept": "application/json"})
        except HTTPError as error:
            retry_after = None
            if error.code == 429:
                # Respect the provider's Retry-After cooldown without automatic retries.
                try:
                    retry_after = max(1.05, float(error.headers.get("Retry-After", 60)))
                    if not retry_after < float("inf"):
                        retry_after = 60.0
                except (TypeError, ValueError, AttributeError):
                    retry_after = 60.0
                self._cooldown_until[host] = current + retry_after
            raise DataSourceError(
                "The free data provider is unavailable or rate-limited. Please use manual input.",
                "rate_limited" if error.code == 429 else "unavailable", retry_after) from None
        except (URLError, OSError, TimeoutError):
            raise DataSourceError("The free data request failed. Please use manual input.") from None
        except (ValueError, UnicodeError):
            raise DataSourceError("The provider returned invalid JSON. Please use manual input.",
                                  "invalid_response") from None
        if not isinstance(payload, dict) or payload.get("error"):
            raise DataSourceError("The provider returned an invalid response. Please use manual input.",
                                  "invalid_response")
        retrieved_at = datetime.now(timezone.utc).isoformat()
        self._cache[url] = (current, deepcopy(payload), retrieved_at)
        return payload, retrieved_at, False

    def _fetch(self, url, ttl, source, source_url, kind, attribution, parser, location=None):
        result = {"ok": False, "source": source, "source_url": source_url,
                  "request_url": url, "kind": kind, "location": location,
                  "retrieved_at": None, "data_time": None, "unit": None, "data": None,
                  "from_cache": False, "stale": False, "has_missing_values": False,
                  "requires_confirmation": True, "manual_input_required": True,
                  "attribution": attribution, "error": None, "error_code": None,
                  "retry_after": None}
        try:
            payload, retrieved_at, from_cache = self._request(url, ttl)
            result.update({"retrieved_at": retrieved_at, "from_cache": from_cache})
            result.update(parser(payload))
            result.update({"ok": True, "manual_input_required": False})
        except DataSourceError as error:
            result.update({"error": str(error), "error_code": error.code,
                           "retry_after": error.retry_after})
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            self._cache.pop(url, None)
            result.update({"error": "The provider returned missing or invalid fields. Please use manual input.",
                           "error_code": "invalid_response"})
        return result

    def search_cities(self, query, count=5):
        query = _text(query, "City search")
        _integer(count, "Result count", 1, 10)
        url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
            {"name": query, "count": count, "language": "en", "format": "json"})

        def parse(payload):
            records = payload.get("results", [])
            if not isinstance(records, list):
                raise ValueError("Invalid location results.")
            if not records:
                raise DataSourceError("No matching cities were found. Please enter a location manually.", "no_data")
            data = []
            for record in records:
                coordinates = _coordinates(record["latitude"], record["longitude"])
                data.append({"name": _text(record["name"], "City name"), **coordinates,
                             "country": record.get("country"), "admin1": record.get("admin1"),
                             "timezone": record.get("timezone")})
            return {"data": data, "unit": "WGS84 degrees"}

        return self._fetch(url, 86400, "Open-Meteo Geocoding",
                           "https://open-meteo.com/en/docs/geocoding-api", "Reference data",
                           "Location data: Open-Meteo / GeoNames (CC BY attribution required).", parse)

    def weather_forecast(self, latitude, longitude, days=3):
        location = _coordinates(latitude, longitude)
        _integer(days, "Forecast days", 1, 16)
        fields = ["temperature_2m_max", "temperature_2m_min",
                  "precipitation_probability_max", "precipitation_sum"]
        url = "https://api.open-meteo.com/v1/forecast?" + urlencode({
            **location, "daily": ",".join(fields), "forecast_days": days,
            "timezone": "UTC", "temperature_unit": "celsius", "precipitation_unit": "mm"})

        def parse(payload):
            result = _time_series(payload, "daily", fields)
            for row in result["data"]:
                if row["precipitation_probability_max"] is not None:
                    number(row["precipitation_probability_max"], "Precipitation probability", 0, 100)
                if row["precipitation_sum"] is not None:
                    number(row["precipitation_sum"], "Precipitation", minimum=0)
            return result

        return self._fetch(url, 600, "Open-Meteo Forecast", "https://open-meteo.com/en/docs",
                           "Provider estimates", "Weather data: Open-Meteo (CC BY 4.0).", parse, location)

    def air_quality(self, latitude, longitude, days=1):
        location = _coordinates(latitude, longitude)
        _integer(days, "Forecast days", 1, 7)
        fields = ["pm2_5", "us_aqi"]
        url = "https://air-quality-api.open-meteo.com/v1/air-quality?" + urlencode({
            **location, "hourly": ",".join(fields), "forecast_days": days, "timezone": "UTC"})

        def parse(payload):
            result = _time_series(payload, "hourly", fields)
            for row in result["data"]:
                for field in fields:
                    if row[field] is not None:
                        number(row[field], "Air quality value", minimum=0)
            return result

        return self._fetch(url, 600, "Open-Meteo Air Quality",
                           "https://open-meteo.com/en/docs/air-quality-api", "Provider estimates",
                           "Air quality data: Open-Meteo / CAMS ENSEMBLE. Environmental estimates, not personal medical risk.",
                           parse, location)

    def exchange_rate(self, base, quote):
        base, quote = _text(base, "Base currency").upper(), _text(quote, "Quote currency").upper()
        if not re.fullmatch(r"[A-Z]{3}", base) or not re.fullmatch(r"[A-Z]{3}", quote):
            raise ValueError("Currency codes must contain three ASCII letters.")
        url = f"https://api.frankfurter.dev/v2/rate/{base.lower()}/{quote.lower()}"

        def parse(payload):
            if payload["base"].upper() != base or payload["quote"].upper() != quote:
                raise ValueError("The provider returned a different currency pair.")
            date = _text(payload["date"], "Rate date")
            rate = number(payload["rate"], "Exchange rate", minimum=0)
            if rate == 0:
                raise ValueError("Exchange rate must be positive.")
            return {"data": {"base": base, "quote": quote, "rate": rate},
                    "data_time": date, "unit": f"{quote} per {base}"}

        return self._fetch(url, 3600, "Frankfurter", "https://frankfurter.dev/", "Reference data",
                           "Exchange rate: Frankfurter, blended reference rate; not a live trading quote.", parse)

    def search_books(self, query, limit=5):
        query = _text(query, "Book search")
        _integer(limit, "Result limit", 1, 10)
        url = "https://openlibrary.org/search.json?" + urlencode({
            "q": query, "limit": limit,
            "fields": "key,title,author_name,first_publish_year,edition_count"})

        def parse(payload):
            documents = payload["docs"]
            if not isinstance(documents, list):
                raise ValueError("Invalid book results.")
            if not documents:
                raise DataSourceError("No matching books were found. Please enter the details manually.", "no_data")
            records = []
            for document in documents:
                key = _text(document["key"], "Book key")
                if not re.fullmatch(r"(?:/works/)?OL\d+W", key):
                    raise ValueError("Invalid book identifier.")
                authors = document.get("author_name", [])
                if not isinstance(authors, list) or any(not isinstance(author, str) for author in authors):
                    raise ValueError("Invalid book authors.")
                year = document.get("first_publish_year")
                editions = document.get("edition_count")
                if year is not None:
                    _integer(year, "Publication year", -10000, 10000)
                if editions is not None:
                    _integer(editions, "Edition count", 0, 1000000000)
                records.append({"title": _text(document["title"], "Book title"),
                                "authors": authors, "first_publish_year": year,
                                "edition_count": editions,
                                "url": "https://openlibrary.org/works/" + key.split("/")[-1]})
            return {"data": records, "unit": "Book metadata"}

        return self._fetch(url, 86400, "Open Library", "https://openlibrary.org/dev/docs/api/search",
                           "Catalog data", "Book metadata: Open Library. Low-volume lookup; not a measure of learning outcomes.", parse)
