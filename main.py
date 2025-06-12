import argparse
import requests
import json
from xdg_base_dirs import xdg_cache_home

EXECUTIVE_ORDERS_URL = "https://www.federalregister.gov/api/v1/documents.json?conditions[correction]=0&conditions[presidential_document_type]=executive_order&conditions[type][]=PRESDOCU"

def main() -> None:
    cache_dir = xdg_cache_home() / "trump_analysis"
    cache_dir.mkdir(exist_ok=True)

    expected_path = cache_dir / "executive_orders.json"
    if not expected_path.is_file():
        response = requests.get(EXECUTIVE_ORDERS_URL)
        with open(expected_path, "w") as f:
            f.write(response.text)

    with open(expected_path) as f:
        executive_orders = json.load(f)

    with open("inaugurations.json") as f:
        inaugurations = json.load(f)
    print(inaugurations["Donald J. Trump"])
    #print(executive_orders)


if __name__ == "__main__":
    main()
