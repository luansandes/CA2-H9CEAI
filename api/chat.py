import csv
import io
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openai import OpenAI


MAX_MESSAGES = 20
MAX_MESSAGE_LENGTH = 8_000
MAX_TOOL_ROUNDS = 4
MAX_OFFERS = 8
ALLOWED_ROLES = {"user", "assistant"}

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1balBGf8QhZ5dc-RCCAPt2kcrcf6m_YRh0HL_r8bBtJw/"
    "export?format=csv&gid=120683740"
)
REQUIRED_COLUMNS = {
    "tour_id",
    "tour_name",
    "category",
    "location",
    "meeting_point",
    "price_eur",
    "duration_hours",
    "capacity",
    "availability",
    "slots_this_week",
    "special_offer",
    "description",
}
CARD_FIELDS = (
    "tour_id",
    "tour_name",
    "category",
    "location",
    "meeting_point",
    "price_eur",
    "duration_hours",
    "capacity",
    "availability",
    "slots_this_week",
    "special_offer",
    "description",
)

PROMPT_PATH = Path(__file__).with_name("system_prompt.txt")
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8").strip()
INTERNAL_NOTE_PATTERN = re.compile(
    r"\bnotes?\s+to\s+ai\s*:[^\n]*(?:\n|$)",
    flags=re.IGNORECASE,
)


def ireland_today():
    try:
        return datetime.now(ZoneInfo("Europe/Dublin")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(timezone.utc).date()


def system_instructions(today=None):
    current_date = today or ireland_today()
    date_context = current_date.strftime("%A, %d %B %Y")
    return (
        f"{SYSTEM_PROMPT}\n\n"
        "Current date context\n"
        f"- Today is {date_context} ({current_date.isoformat()}) in Europe/Dublin.\n"
        "- Resolve relative dates such as today, tomorrow, this weekend, and next "
        "Monday against this date."
    )


def public_text(value):
    return INTERNAL_NOTE_PATTERN.sub("\n", str(value or "")).strip()


def public_offer(row):
    return {field: public_text(row.get(field, "")) for field in CARD_FIELDS}


class TourDataError(RuntimeError):
    pass


class WeatherDataError(RuntimeError):
    pass


def allowed_origins():
    configured = os.environ.get("FRONTEND_ORIGIN", "")
    origins = {origin.strip() for origin in configured.split(",") if origin.strip()}
    origins.update({"http://localhost:8000", "http://127.0.0.1:8000"})
    return origins


def _read_url(request, timeout=8, opener=urlopen):
    try:
        with opener(request, timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise RuntimeError(str(error)) from error


def fetch_live_tours(opener=urlopen):
    """Read the public sheet once. No result is retained beyond this call."""
    separator = "&" if "?" in SHEET_CSV_URL else "?"
    url = f"{SHEET_CSV_URL}{separator}_fresh={time.time_ns()}"
    request = Request(
        url,
        headers={
            "Accept": "text/csv",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "User-Agent": "AtlanticCoastToursPilot/1.0",
        },
        method="GET",
    )

    try:
        payload = _read_url(request, opener=opener).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(payload))
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise TourDataError(
                "The live tour sheet is missing required columns: "
                + ", ".join(sorted(missing))
            )

        rows = []
        for row in reader:
            if not row.get("tour_id", "").strip():
                continue
            rows.append({column: row.get(column, "") for column in reader.fieldnames})
        return rows
    except (UnicodeDecodeError, csv.Error, RuntimeError) as error:
        if isinstance(error, TourDataError):
            raise
        raise TourDataError("The live tour catalogue could not be read.") from error


def _number(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def search_live_tours(filters, opener=urlopen):
    rows = fetch_live_tours(opener=opener)
    query = str(filters.get("query") or "").strip().casefold()
    tour_id = str(filters.get("tour_id") or "").strip().casefold()
    location = str(filters.get("location") or "").strip().casefold()
    category = str(filters.get("category") or "").strip().casefold()
    availability = str(filters.get("availability") or "").strip().casefold()
    max_price = _number(filters.get("max_price_eur"))
    group_size = _number(filters.get("group_size"))
    available_only = filters.get("available_only") is True
    specials_only = filters.get("special_offers_only") is True
    if specials_only and query in {"offer", "offers", "special offer", "special offers"}:
        query = ""

    try:
        limit = max(1, min(int(filters.get("limit") or MAX_OFFERS), MAX_OFFERS))
    except (TypeError, ValueError):
        limit = MAX_OFFERS

    matches = []
    for row in rows:
        if tour_id and row["tour_id"].casefold() != tour_id:
            continue
        if location and location not in row["location"].casefold():
            continue
        if category and category not in row["category"].casefold():
            continue
        if availability and availability not in row["availability"].casefold():
            continue
        if query and query not in " ".join(row.values()).casefold():
            continue

        price = _number(row["price_eur"])
        capacity = _number(row["capacity"])
        slots = _number(row["slots_this_week"])
        if max_price is not None and (price is None or price > max_price):
            continue
        if group_size is not None and (capacity is None or capacity < group_size):
            continue
        if available_only and (slots is None or slots <= 0):
            continue
        if specials_only and not row["special_offer"].strip():
            continue

        matches.append(row)
        if len(matches) >= limit:
            break

    return matches


def get_weather(location, requested_date, opener=urlopen):
    try:
        target_date = date.fromisoformat(requested_date)
    except (TypeError, ValueError) as error:
        raise WeatherDataError("The weather date must use YYYY-MM-DD format.") from error

    today = date.today()
    last_forecast_date = today + timedelta(days=15)
    if target_date < today or target_date > last_forecast_date:
        return {
            "status": "outside_forecast_window",
            "location": location,
            "date": requested_date,
            "available_from": today.isoformat(),
            "available_through": last_forecast_date.isoformat(),
        }

    # Open-Meteo's name search is most reliable with the locality rather than
    # an Irish postal-style "Town, Co. County" value.
    geocode_query = str(location).split(",", 1)[0].strip()
    geocode_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
        {
            "name": geocode_query,
            "count": 10,
            "language": "en",
            "format": "json",
            "countryCode": "IE",
        }
    )
    geocode_request = Request(
        geocode_url,
        headers={"Accept": "application/json", "User-Agent": "AtlanticCoastToursPilot/1.0"},
        method="GET",
    )

    try:
        geocode = json.loads(_read_url(geocode_request, opener=opener))
        results = geocode.get("results") or []
        if not results:
            raise WeatherDataError(f"No Irish weather location matched {location}.")
        place = results[0]

        forecast_url = "https://api.open-meteo.com/v1/forecast?" + urlencode(
            {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max,precipitation_sum,wind_speed_10m_max"
                ),
                "timezone": "Europe/Dublin",
                "start_date": requested_date,
                "end_date": requested_date,
            }
        )
        forecast_request = Request(
            forecast_url,
            headers={"Accept": "application/json", "User-Agent": "AtlanticCoastToursPilot/1.0"},
            method="GET",
        )
        forecast = json.loads(_read_url(forecast_request, opener=opener))
        daily = forecast.get("daily") or {}
        if not daily.get("time"):
            raise WeatherDataError("Open-Meteo returned no forecast for that date.")

        return {
            "status": "ok",
            "requested_location": location,
            "resolved_location": ", ".join(
                part
                for part in (place.get("name"), place.get("admin1"), place.get("country"))
                if part
            ),
            "date": daily["time"][0],
            "weather_code": daily.get("weather_code", [None])[0],
            "temperature_max_c": daily.get("temperature_2m_max", [None])[0],
            "temperature_min_c": daily.get("temperature_2m_min", [None])[0],
            "precipitation_probability_max_percent": daily.get(
                "precipitation_probability_max", [None]
            )[0],
            "precipitation_sum_mm": daily.get("precipitation_sum", [None])[0],
            "wind_speed_max_kmh": daily.get("wind_speed_10m_max", [None])[0],
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, RuntimeError) as error:
        if isinstance(error, WeatherDataError):
            raise
        raise WeatherDataError("Weather information is temporarily unavailable.") from error


TOOLS = [
    {
        "type": "function",
        "name": "search_live_tours",
        "description": (
            "Read the Atlantic Coast Tours Google Sheet live and return matching rows. "
            "Call this before stating any tour, price, availability, slot, offer, or description."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Optional words to find inside sheet cell values. Omit this when a "
                        "structured filter such as special_offers_only fully expresses the search."
                    ),
                },
                "tour_id": {"type": "string"},
                "location": {"type": "string"},
                "category": {"type": "string"},
                "availability": {"type": "string"},
                "max_price_eur": {"type": "number"},
                "group_size": {"type": "integer"},
                "available_only": {"type": "boolean"},
                "special_offers_only": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_OFFERS},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_weather",
        "description": (
            "Get a live Open-Meteo forecast. Call whenever the conversation contains both "
            "a tour location and a concrete calendar date."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "date": {"type": "string", "description": "ISO date in YYYY-MM-DD format."},
            },
            "required": ["location", "date"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

FINAL_RESPONSE_FORMAT = {
    "type": "json_schema",
    "name": "atlantic_coast_tours_chat_response",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "offer_ids": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": MAX_OFFERS,
            },
        },
        "required": ["message", "offer_ids"],
        "additionalProperties": False,
    },
}


def _execute_tool(name, arguments, live_rows, force_full_catalogue=False):
    if name == "search_live_tours":
        rows = fetch_live_tours() if force_full_catalogue else search_live_tours(arguments)
        for row in rows:
            live_rows[row["tour_id"]] = row
        return {"status": "ok", "count": len(rows), "tours": rows}
    if name == "get_weather":
        try:
            return get_weather(arguments["location"], arguments["date"])
        except WeatherDataError as error:
            return {"status": "unavailable", "error": str(error)}
    return {"status": "error", "error": "Unknown tool."}


def create_chat_response(messages, client=None):
    client = client or OpenAI()
    running_input = list(messages)
    live_rows = {}

    for round_index in range(MAX_TOOL_ROUNDS + 1):
        response = client.responses.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
            instructions=system_instructions(),
            input=running_input,
            tools=TOOLS,
            tool_choice=(
                {"type": "function", "name": "search_live_tours"}
                if round_index == 0
                else "auto"
            ),
            reasoning={"effort": "low", "context": "current_turn"},
            text={"format": FINAL_RESPONSE_FORMAT, "verbosity": "low"},
        )
        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            try:
                result = json.loads(response.output_text)
            except (TypeError, json.JSONDecodeError) as error:
                raise RuntimeError("The assistant returned an invalid response.") from error

            message = public_text(result.get("message")).replace("**", "")
            if not message:
                raise RuntimeError("The assistant returned an empty response.")

            offers = []
            seen = set()
            requested_ids = list(result.get("offer_ids") or [])
            requested_ids.extend(re.findall(r"\bACT\d{3}\b", message, flags=re.IGNORECASE))
            folded_message = message.casefold()
            requested_ids.extend(
                tour_id
                for tour_id, row in live_rows.items()
                if row.get("tour_name", "").casefold() in folded_message
            )
            for tour_id in requested_ids:
                tour_id = tour_id.upper()
                if tour_id in seen or tour_id not in live_rows:
                    continue
                seen.add(tour_id)
                offers.append(public_offer(live_rows[tour_id]))
                if len(offers) >= MAX_OFFERS:
                    break
            return {"message": message, "offers": offers}

        running_input += response.output
        for call in function_calls:
            try:
                arguments = json.loads(call.arguments)
                tool_result = _execute_tool(
                    call.name,
                    arguments,
                    live_rows,
                    force_full_catalogue=(round_index == 0),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                tool_result = {"status": "error", "error": f"Invalid tool request: {error}"}
            running_input.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(tool_result, ensure_ascii=False),
                }
            )

    raise RuntimeError("The assistant used too many tool calls.")


def _clean_messages(messages):
    if not isinstance(messages, list) or not messages:
        raise ValueError("A non-empty messages array is required.")

    cleaned = []
    for item in messages[-MAX_MESSAGES:]:
        if not isinstance(item, dict):
            raise ValueError("Each message must be an object.")
        role = item.get("role")
        content = item.get("content")
        if role not in ALLOWED_ROLES or not isinstance(content, str):
            raise ValueError("Each message needs a valid role and text content.")
        content = content.strip()
        if not content or len(content) > MAX_MESSAGE_LENGTH:
            raise ValueError("A message is empty or too long.")
        cleaned.append({"role": role, "content": content})
    return cleaned


class handler(BaseHTTPRequestHandler):
    def _origin(self):
        origin = self.headers.get("Origin", "")
        return origin if origin in allowed_origins() else ""

    def _send_json(self, status, payload):
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self):
        origin = self._origin()
        if not origin:
            self._send_json(403, {"error": "Origin is not allowed."})
            return

        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_POST(self):
        if self.headers.get("Origin") and not self._origin():
            self._send_json(403, {"error": "Origin is not allowed."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 200_000:
                raise ValueError("Invalid request size.")

            body = json.loads(self.rfile.read(content_length))
            cleaned_messages = _clean_messages(body.get("messages"))
            self._send_json(200, create_chat_response(cleaned_messages))
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": str(error)})
        except TourDataError as error:
            print(f"Live catalogue request failed: {error}")
            self._send_json(502, {"error": "The live tour catalogue is temporarily unavailable."})
        except Exception as error:
            print(f"Chat request failed: {error}")
            self._send_json(500, {"error": "The travel assistant is temporarily unavailable."})
