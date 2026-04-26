import sys
from pathlib import Path

sys.path.append(str((Path(__file__).resolve().parent.parent / "strategies")))

from common.single_file_builder import build


def default_output_path(entry_file: Path) -> Path:
    stem = entry_file.stem
    if stem.endswith("_dev"):
        stem = stem[:-4]
    return Path("submit") / f"{stem}.py"


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("usage: python scripts/build_strategy.py <entry.py> [output.py]")
        return 1

    entry_file = Path(sys.argv[1])
    output_file = default_output_path(entry_file) if len(sys.argv) == 2 else Path(sys.argv[2])
    output_file.parent.mkdir(parents=True, exist_ok=True)
    build(entry_file, output_file)
    print(f"Wrote {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
