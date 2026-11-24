"""Measure the single-object Fit result on the isolated Feishu #18 fixture."""
# feishu: baseline#18
from m8_fit18_profile import main


if __name__ == "__main__":
    raise SystemExit(main(("guided_select",), "fit18_single.json"))
