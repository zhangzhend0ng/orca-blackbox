"""Measure the single-object Fit result on the isolated Feishu #18 fixture."""
# feishu: none (partial evidence for baseline 18, not eligible for writeback)
from m8_fit18_profile import main


if __name__ == "__main__":
    raise SystemExit(main(("ready_boot",), "fit18_single.json"))
