import argparse
import requests
import json
from xdg_base_dirs import xdg_cache_home
import time
import datetime
from dataclasses import dataclass
from collections import defaultdict

EXECUTIVE_ORDERS_URL = "https://www.federalregister.gov/api/v1/documents.json"


@dataclass
class Inauguration:
    president: str
    date: datetime.datetime


def find_inauguration(sorted_inaugurations: list[tuple[int, str]], date: datetime.datetime) -> Inauguration:
    index = len(sorted_inaugurations) // 2
    start = 0
    end = len(sorted_inaugurations) - 1

    while index >= start and index <= end:
        if sorted_inaugurations[index].date > date:
            end = index - 1
        elif sorted_inaugurations[index].date < date:
            start = index + 1
        else:
            return sorted_inaugurations[index]
        index = start + (end - start) // 2

    if end - start <= 1:
        return sorted_inaugurations[index]

    raise IndexError(f"Unable to find president for date {date}")


def main() -> None:
    cache_dir = xdg_cache_home() / "trump_analysis"
    cache_dir.mkdir(exist_ok=True)

    expected_path = cache_dir / "executive_orders.json"
    if not expected_path.is_file():
        print("Fetching orders from federal database...")
        next_url = None
        orders = []
        pages = 0

        while True:
            if next_url is None:
                response = requests.get(EXECUTIVE_ORDERS_URL,
                                        params={
                                        "conditions[correction]": "0",
                                        "conditions[presidential_document_type]": "executive_order",
                                        "conditions[type][]": "PRESDOCU",
                                        "fields[]": ["signing_date", "title", "executive_order_number"],
                                        "include_pre_1994_docs": "true",
                                        "order": "executive_order",
                                        "per_page": "100",
                                        })
            else:
                response = requests.get(next_url)

            data = response.json()
            if next_url is None:
                print("{} total page(s) to fetch".format(data["total_pages"]))

            if pages > 0 and pages % 10 == 0:
                print(f"Fetched {pages} pages...")

            pages += 1

            orders.extend(data["results"])
            next_url = data.get("next_page_url")
            if next_url is None:
                break

        print(f"Done. Fetched {pages} page(s)")

        with open(expected_path, "w") as f:
            json.dump(orders, f)

    with open(expected_path) as f:
        executive_orders = json.load(f)

    with open("inaugurations.json") as f:
        inaugurations = json.load(f)

    sorted_inaugurations = []
    for president, inauguration_dates in inaugurations.items():
        for inauguration_date in inauguration_dates:
            date = datetime.datetime.strptime(inauguration_date, "%m/%d/%Y")
            sorted_inaugurations.append(Inauguration(president, date))

    sorted_inaugurations.sort(key=lambda t: t.date)

    by_president = defaultdict(list)
    for order in executive_orders:
        inauguration = find_inauguration(sorted_inaugurations, datetime.datetime.strptime(order["signing_date"], "%Y-%m-%d"))
        by_president[inauguration.president].append(order)

    for president, orders in by_president.items():
        print(f"{president}: {len(orders)}")


if __name__ == "__main__":
    main()
