import requests, json

BASE_URL = "https://core-prod-origin.cricclubs.com/core/series/getSeriesDetails"
HEADERS = {
    "x-api-key": "Tan@!75za",
    "x-consumer-key": "Tan#$72za5",
}

def get_series_details(club_id, series_id):
    params = {"clubId": str(club_id), "seriesId": str(series_id), "X-Auth-Token": ""}
    r = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=10)
    return r

for sid in ["1", "389"]:
    r = get_series_details("7605", sid)
    print(f"=== seriesId={sid} FULL RESPONSE ===")
    print(json.dumps(r.json(), indent=2))
    print()