"""Generate the fixed-fixture value and dependency case plans from one catalog."""
from decimal import Decimal
from itertools import combinations, permutations, product
import json
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "contracts/config_dependencies.json"
CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
DOMAIN = CATALOG["legal_domain"]
RULES = {rule["id"]: rule for rule in CATALOG["rules"]}


def value_pairs(values):
    return set(combinations(values.items(), 2))


def generate(admitted):
    factors = DOMAIN["factors"]
    constraints = [RULES[ident] for ident in DOMAIN["constraint_ids"]]
    candidates, eligible = [], []
    for index, items in enumerate(product(*factors.values()), 1):
        values = dict(zip(factors, items))
        inputs = {**DOMAIN["fixed"], **values}
        row = {"id": f"cfg_value_{index:02}", "family": "legal", "values": values}
        candidates.append(row)
        rejects = []
        for rule in constraints:
            left, right = rule["candidate_filter"]["reject_if_gt"]
            if rule["evidence"] != "source_confirmed":
                raise ValueError("config_case_unconfirmed_constraint")
            if Decimal(inputs[left]) > Decimal(inputs[right]):
                rejects.append(rule["id"])
        if rejects:
            row.update(selection="excluded", reason="source_validation", rules=rejects)
            continue
        routes = [factors[key][value] for key, value in values.items()]
        if None in routes:
            row.update(selection="blocked", reason="missing_admitted_operation")
            continue
        ops = tuple(op for route in routes for op in route)
        orders = tuple(dict.fromkeys(permutations(ops)))
        allowed = [order for order in orders if admitted(order)]
        row["orders"] = [{"order": order, "admitted": order in allowed,
                          "reason": None if order in allowed else "recording_precondition"} for order in orders]
        if allowed:
            row["order"] = allowed[0]
            eligible.append(row)
        else:
            row.update(selection="blocked", reason="no_admitted_order")

    target = set().union(*(value_pairs(row["values"]) for row in eligible))
    # This domain is bounded to the frozen eight executable combinations.
    if not eligible or len(eligible) > 12:
        raise ValueError("config_case_coverage_domain")
    for size in range(1, len(eligible) + 1):
        selected = next((batch for batch in combinations(eligible, size)
                         if set().union(*(value_pairs(row["values"]) for row in batch)) == target), None)
        if selected is not None:
            break
    for row in eligible:
        row["selection"] = "selected" if row in selected else "redundant"
        if row not in selected:
            row["reason"] = "all_value_pairs_covered"
    dependency = []
    defaults = {key: next(iter(domain)) for key, domain in factors.items()}
    for rule in RULES.values():
        replay = rule.get("replay")
        if replay:
            for case in replay["scenarios"]:
                order = tuple(case["order"])
                values = {key: next((value for value, ops in domain.items() if ops and set(ops) <= set(order)),
                                    defaults[key]) for key, domain in factors.items()}
                dependency.append({**case, "family": "dependency", "rule": rule["id"],
                                   "kind": replay["kind"], "order": order, "values": values,
                                   "selection": "selected" if admitted(order) else "blocked",
                                   "expected": rule["expected"]})
        if rule.get("blocked_reason"):
            dependency.append({"id": rule["id"] + "-pending", "family": "dependency", "rule": rule["id"],
                               "selection": "blocked", "reason": rule["blocked_reason"]})
    return {"legal": candidates, "dependency": dependency,
            "target_value_pairs": [list(pair) for pair in sorted(target)]}
