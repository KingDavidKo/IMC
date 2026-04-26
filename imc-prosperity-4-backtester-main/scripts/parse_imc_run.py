#!/usr/bin/env python3
import argparse
import csv
import io
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_run(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def parse_activities(raw: str) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(raw), delimiter=";"))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def parse_graph(raw: str) -> tuple[list[str], list[list[str]]]:
    lines = [line for line in raw.strip().splitlines() if line]
    if not lines:
        return [], []
    if ";" in lines[0] and not lines[0].split(";", 1)[0].isdigit():
        header = lines[0].split(";")
        lines = lines[1:]
    else:
        header = ["timestamp", "profit_and_loss"]
    rows = [line.split(";") for line in lines]
    return header, rows


def try_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def summarize(
    run_data: dict[str, Any],
    activity_rows: list[list[str]],
    graph_rows: list[list[str]],
) -> dict[str, Any]:
    by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in activity_rows:
        if len(row) < 17:
            continue
        by_product[row[2]].append(
            {
                "day": int(row[0]),
                "timestamp": int(row[1]),
                "product": row[2],
                "mid_price": float(row[-2]),
                "profit_and_loss": float(row[-1]),
            }
        )

    product_summary: dict[str, Any] = {}
    for product, rows in sorted(by_product.items()):
        pnls = [row["profit_and_loss"] for row in rows]
        mids = [row["mid_price"] for row in rows]
        final_row = rows[-1]
        min_row = min(rows, key=lambda row: row["profit_and_loss"])
        max_row = max(rows, key=lambda row: row["profit_and_loss"])
        product_summary[product] = {
            "final_profit": final_row["profit_and_loss"],
            "final_mid_price": final_row["mid_price"],
            "min_profit": min_row["profit_and_loss"],
            "min_profit_timestamp": min_row["timestamp"],
            "min_profit_mid_price": min_row["mid_price"],
            "max_profit": max_row["profit_and_loss"],
            "max_profit_timestamp": max_row["timestamp"],
            "max_profit_mid_price": max_row["mid_price"],
            "mid_price_min": min(mids),
            "mid_price_max": max(mids),
            "num_rows": len(rows),
        }

    graph_points = []
    for row in graph_rows:
        if len(row) < 2:
            continue
        timestamp = try_float(row[0])
        profit = try_float(row[1])
        if timestamp is None or profit is None:
            continue
        graph_points.append((int(timestamp), float(profit)))

    graph_summary = {}
    if graph_points:
        graph_summary = {
            "num_points": len(graph_points),
            "min_profit_point": {
                "timestamp": min(graph_points, key=lambda point: point[1])[0],
                "profit": min(graph_points, key=lambda point: point[1])[1],
            },
            "max_profit_point": {
                "timestamp": max(graph_points, key=lambda point: point[1])[0],
                "profit": max(graph_points, key=lambda point: point[1])[1],
            },
            "num_negative_points": sum(1 for _, profit in graph_points if profit < 0),
            "num_positive_points": sum(1 for _, profit in graph_points if profit > 0),
        }

    positions = {
        entry["symbol"]: entry["quantity"]
        for entry in run_data.get("positions", [])
        if isinstance(entry, dict) and "symbol" in entry and "quantity" in entry
    }

    return {
        "round": run_data.get("round"),
        "status": run_data.get("status"),
        "profit": run_data.get("profit"),
        "positions": positions,
        "product_summary": product_summary,
        "graph_summary": graph_summary,
    }


def print_summary(summary: dict[str, Any]) -> None:
    print(f"round: {summary.get('round')}")
    print(f"status: {summary.get('status')}")
    print(f"profit: {summary.get('profit')}")
    print()

    print("positions:")
    positions = summary.get("positions", {})
    if positions:
        for symbol, quantity in sorted(positions.items()):
            print(f"  {symbol}: {quantity}")
    else:
        print("  none")
    print()

    graph_summary = summary.get("graph_summary", {})
    if graph_summary:
        print("graph:")
        print(
            f"  min pnl: {graph_summary['min_profit_point']['profit']} at {graph_summary['min_profit_point']['timestamp']}"
        )
        print(
            f"  max pnl: {graph_summary['max_profit_point']['profit']} at {graph_summary['max_profit_point']['timestamp']}"
        )
        print(
            f"  negative points: {graph_summary['num_negative_points']}, positive points: {graph_summary['num_positive_points']}"
        )
        print()

    print("products:")
    for product, stats in summary.get("product_summary", {}).items():
        print(
            f"  {product}: final={stats['final_profit']}, "
            f"min={stats['min_profit']}@{stats['min_profit_timestamp']}, "
            f"max={stats['max_profit']}@{stats['max_profit_timestamp']}, "
            f"final_mid={stats['final_mid_price']}"
        )


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="") as file:
        writer = csv.writer(file)
        if header:
            writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse an IMC Prosperity website run JSON export.")
    parser.add_argument("run_json", type=Path, help="Path to the Prosperity website JSON export.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Optional directory to write normalized CSVs and summary JSON.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print the parsed summary to stdout.",
    )
    args = parser.parse_args()

    run_data = load_run(args.run_json)
    activity_header, activity_rows = parse_activities(run_data.get("activitiesLog", ""))
    graph_header, graph_rows = parse_graph(run_data.get("graphLog", ""))
    summary = summarize(run_data, activity_rows, graph_rows)

    if not args.quiet:
        print_summary(summary)

    if args.out_dir is not None:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        write_csv(args.out_dir / "activities.csv", activity_header, activity_rows)
        write_csv(args.out_dir / "graph.csv", graph_header, graph_rows)
        (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
