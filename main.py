import argparse
import requests
import json
from xdg_base_dirs import xdg_cache_home
import time
import datetime
from dataclasses import dataclass
from collections import defaultdict
import matplotlib.pyplot as plt

EXECUTIVE_ORDERS_URL = "https://www.federalregister.gov/api/v1/documents.json"
# I'm lazy, sorry not sorry
ONE_YEAR_IN_DAYS = 365

def parse_date(value: str) -> datetime.datetime:
    return datetime.datetime.strptime(value, "%Y-%m-%d")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-counts", action="store_true", help="Show a table of total EO counts as well as rate of change chart")
    parser.add_argument("--start-date", type=parse_date, help="Date to track EOs after (format YYYY-MM-DD)")
    parser.add_argument("--end-date", type=parse_date, help="Date to track EOs before (format YYYY-MM-DD)")
    parser.add_argument("--only-terms", nargs="*", help="Only include the listed presidential terms (format \"Donald J. Trump term 1\")")
    return parser.parse_args()


@dataclass
class Inauguration:
    president: str
    term: int
    term_end_days: int
    date: datetime.datetime

    @classmethod
    def new(cls, president: str, date: datetime.datetime) -> "Inauguration":
        return Inauguration(president=president, term=0, term_end_days=0, date=date)


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
    args = parse_args()

    cache_dir = xdg_cache_home() / "executive_order_analysis"
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
            sorted_inaugurations.append(Inauguration.new(president, date))

    sorted_inaugurations.sort(key=lambda t: t.date)

    seen_count = defaultdict(int)
    for i, inauguration in enumerate(sorted_inaugurations):
        seen_count[inauguration.president] += 1
        sorted_inaugurations[i].term = seen_count[inauguration.president]

    by_term = defaultdict(list)
    earliest_order_date = None
    president_per_day = defaultdict(lambda: defaultdict(int))

    for order in executive_orders:
        order_date = datetime.datetime.strptime(order["signing_date"], "%Y-%m-%d")
        if earliest_order_date is None or earliest_order_date > order_date:
            earliest_order_date = order_date

        inauguration = find_inauguration(sorted_inaugurations, order_date)

        days_from_inauguration = (order_date - inauguration.date).days
        
        term_key = f"{inauguration.president} term {inauguration.term}"
        president_per_day[term_key][days_from_inauguration] += 1

        by_term[term_key].append(order)

    inaugurations_by_term = {}
    sorted_terms = []

    for i, inauguration in enumerate(sorted_inaugurations):
        if inauguration.date < earliest_order_date:
            continue

        if args.start_date and inauguration.date < args.start_date:
            continue

        if args.end_date and inauguration.date >= args.end_date:
            continue

        if i < len(sorted_inaugurations) - 1:
            sorted_inaugurations[i].term_end_days = (sorted_inaugurations[i + 1].date - inauguration.date).days
        else:
            sorted_inaugurations[i].term_end_days = (datetime.datetime.now() - inauguration.date).days

        term_key = f"{inauguration.president} term {inauguration.term}"
        sorted_terms.append(term_key)
        inaugurations_by_term[term_key] = sorted_inaugurations[i]

    table_data = []
    for term in sorted_terms:
        table_data.append([term, len(by_term[term])])

    datapoints = defaultdict(list)
    total_sums = defaultdict(int)
    for term in sorted_terms:
        if args.only_terms and term not in args.only_terms:
            continue

        for i in range(ONE_YEAR_IN_DAYS):
            if i > inaugurations_by_term[term].term_end_days:
                break

            total_sums[term] += president_per_day[term].get(i, 0)
            datapoints[term].append(total_sums[term])

    if not datapoints:
        print("No datapoints to display. Did you filter too aggressively?")
        return

    if args.show_counts:
        fig, axes = plt.subplots(2, 1, constrained_layout=True)
        axes[0].axis('off')
        axes[0].table(cellText=table_data, colLabels=["term", "#EOs total"])
        axes[0].set_title("#EOs count")

        axes[1].set_xlabel("days since inauguration")
        axes[1].set_ylabel("total EOs to date")
        axes[1].set_title("Rate of EOs by term")

        for term in sorted_terms:
            axes[1].plot(list(range(len(datapoints[term]))), datapoints[term], label=term)

        axes[1].legend()
    else:
        plt.xlabel("days since inauguration")
        plt.ylabel("total EOs to date")
        title = "Rate of EOs by term"
        if args.start_date:
            title += " for terms starting after {}".format(args.start_date.strftime("%Y-%m-%d"))
        plt.title(title)

        for term in sorted_terms:
            if args.only_terms and term not in args.only_terms:
                continue

            plt.plot(list(range(len(datapoints[term]))), datapoints[term], label=term)

        plt.legend()

    plt.show()


if __name__ == "__main__":
    main()
