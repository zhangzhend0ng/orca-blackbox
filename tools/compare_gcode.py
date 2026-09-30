#!/usr/bin/env python3
# compare_gcode.py — OFFICIAL comparison script, vendored from the Feishu
# doc 「gcode测试方案」 (wiki RZQuwbdFzi3E2YkES5acOcB3nIf, attachment
# compare_gcode.py, 8226 bytes, fetched 2026-09-23 via lark-cli).
#
# It compares the FINAL CONFIG BLOCK carried by two gcodes ('; CONFIG_BLOCK_
# START' .. END) and reports, separately: flow-MODE field changes
# (filament/nozzle/process/printer *_flow_support, *_volume_type,
# filament_flow_step_size) and NUMERIC config changes. exit 0 = no
# differences, 1 = differences, 2 = parse error.
# Do not edit the body: it is the tester's authority for #135/#136.
"""比较两个 Orca/Snapmaker G-code 携带的最终配置值。"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence


FLOW_MODE_KEYS = (
    "filament_volume_type",
    "nozzle_volume_type",
    "filament_flow_support",
    "process_flow_support",
    "printer_flow_support",
    "filament_flow_step_size",
)
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?%?"
NUMERIC_VALUE_RE = re.compile(rf"^{NUMBER}(?:\s*[,;]\s*{NUMBER})*$")


@dataclass(frozen=True)
class ConfigEntry:
    key: str
    value: str
    line: int


@dataclass
class ParsedConfig:
    path: Path
    entries: list[ConfigEntry]
    complete: bool
    by_key: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def values(self, key: str) -> Optional[tuple[str, ...]]:
        values = self.by_key.get(key)
        return tuple(values) if values is not None else None


@dataclass(frozen=True)
class ConfigDifference:
    key: str
    a: Optional[tuple[str, ...]]
    b: Optional[tuple[str, ...]]
    category: str


@dataclass
class Comparison:
    a: ParsedConfig
    b: ParsedConfig
    mode_changed: list[ConfigDifference]
    numeric_changed: list[ConfigDifference]
    only_a: list[ConfigDifference]
    only_b: list[ConfigDifference]

    @property
    def has_differences(self) -> bool:
        return bool(self.mode_changed or self.numeric_changed or self.only_a or self.only_b)


def parse_gcode_config(path: Path) -> ParsedConfig:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path} 不是有效的 UTF-8 G-code：{exc}") from exc

    entries: list[ConfigEntry] = []
    in_config = False
    found_start = False
    complete = False

    for line_number, line in enumerate(text.splitlines(), 1):
        marker = line.strip()
        if marker == "; CONFIG_BLOCK_START":
            if in_config:
                raise ValueError(f"{path}:{line_number} 出现嵌套 CONFIG_BLOCK_START")
            in_config = True
            found_start = True
            continue
        if marker == "; CONFIG_BLOCK_END":
            if not in_config:
                raise ValueError(f"{path}:{line_number} 的 CONFIG_BLOCK_END 没有对应开始标记")
            in_config = False
            complete = True
            continue
        if not in_config or not line.lstrip().startswith(";"):
            continue

        body = line.lstrip()[1:].lstrip()
        if "=" not in body:
            continue
        key, value = body.split("=", 1)
        key = key.strip()
        if key:
            entries.append(ConfigEntry(key, value.strip(), line_number))

    if not found_start:
        raise ValueError(f"{path} 未找到 CONFIG_BLOCK_START，无法读取最终配置")

    by_key: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        by_key[entry.key].append(entry.value)

    warnings: list[str] = []
    if not complete:
        warnings.append("CONFIG_BLOCK_END 缺失，配置块可能被截断")
    for key, values in by_key.items():
        if len(values) > 1:
            warnings.append(f"配置 {key} 重复 {len(values)} 次，报告保留全部值")

    return ParsedConfig(path, entries, complete, dict(by_key), warnings)


def is_numeric_config(values: Optional[tuple[str, ...]]) -> bool:
    return bool(values) and all(NUMERIC_VALUE_RE.fullmatch(value.strip()) for value in values)


def compare_configs(a: ParsedConfig, b: ParsedConfig) -> Comparison:
    mode_changed: list[ConfigDifference] = []
    numeric_changed: list[ConfigDifference] = []
    only_a: list[ConfigDifference] = []
    only_b: list[ConfigDifference] = []

    for key in sorted(set(a.by_key) | set(b.by_key)):
        left, right = a.values(key), b.values(key)
        if left == right:
            continue

        is_mode = key in FLOW_MODE_KEYS
        is_numeric = is_numeric_config(left) or is_numeric_config(right)
        if not is_mode and not is_numeric:
            continue

        difference = ConfigDifference(key, left, right, "mode" if is_mode else "numeric")
        if left is None:
            only_b.append(difference)
        elif right is None:
            only_a.append(difference)
        elif is_mode:
            mode_changed.append(difference)
        else:
            numeric_changed.append(difference)

    return Comparison(a, b, mode_changed, numeric_changed, only_a, only_b)


def format_values(values: Optional[tuple[str, ...]], missing: str) -> str:
    if values is None:
        return missing
    if len(values) == 1:
        return values[0] if values[0] else "<空>"
    return " | ".join(value if value else "<空>" for value in values)


def append_differences(lines: list[str], differences: list[ConfigDifference], missing_a: str = "<缺失>", missing_b: str = "<缺失>") -> None:
    if not differences:
        lines.append("无。")
        return
    for difference in differences:
        mode_missing = "<旧版未定义>" if difference.category == "mode" else None
        left_missing = mode_missing or missing_a
        right_missing = mode_missing or missing_b
        lines.append(difference.key)
        lines.append(f"  A = {format_values(difference.a, left_missing)}")
        lines.append(f"  B = {format_values(difference.b, right_missing)}")


def format_report(result: Comparison) -> str:
    lines = [
        "G-code 最终配置白盒对比报告",
        "=" * 80,
        f"A: {result.a.path}",
        f"B: {result.b.path}",
        "",
        "一、对比结论",
        "-" * 80,
        f"高流量模式字段变化：{len(result.mode_changed)} 项",
        f"数值配置变化：{len(result.numeric_changed)} 项",
        f"仅 A 存在：{len(result.only_a)} 项",
        f"仅 B 存在：{len(result.only_b)} 项",
        "说明：本报告只比较 G-code 携带的最终配置，不判断可执行 G-code 和打印效果。",
        "",
        "二、高流量模式字段差异",
        "-" * 80,
    ]
    append_differences(lines, result.mode_changed, "<旧版未定义>", "<旧版未定义>")

    lines.extend(["", "三、数值配置差异", "-" * 80])
    append_differences(lines, result.numeric_changed)

    lines.extend(["", "四、仅 A 存在的目标配置", "-" * 80])
    append_differences(lines, result.only_a, "<缺失>", "<缺失>")

    lines.extend(["", "五、仅 B 存在的目标配置", "-" * 80])
    append_differences(lines, result.only_b, "<缺失>", "<缺失>")

    warnings = [("A", warning) for warning in result.a.warnings] + [("B", warning) for warning in result.b.warnings]
    if warnings:
        lines.extend(["", "六、解析警告", "-" * 80])
        lines.extend(f"{label}: {warning}" for label, warning in warnings)

    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="白盒比较两个 Orca/Snapmaker G-code 携带的最终配置")
    parser.add_argument("gcode_a", type=Path, help="基准 G-code（A）")
    parser.add_argument("gcode_b", type=Path, help="待比较 G-code（B）")
    parser.add_argument("--output", type=Path, help="将 UTF-8 报告写入文本文件")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = compare_configs(parse_gcode_config(args.gcode_a), parse_gcode_config(args.gcode_b))
        report = format_report(result)
        if args.output:
            args.output.write_text(report, encoding="utf-8")
            print(f"报告已写入：{args.output}")
        else:
            try:
                sys.stdout.write(report)
            except UnicodeEncodeError:
                sys.stdout.buffer.write(report.encode("utf-8"))
        return 1 if result.has_differences else 0
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
