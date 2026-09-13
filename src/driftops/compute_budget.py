"""Conservative compute accounting from this job's provider operation records."""

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Compute timestamps must include a time zone")
    return result


def instance_cost(operations, now, hourly_rate, disk_hourly_rate, disk_created):
    """Include transitions and failed starts. Merge overlap so a VM is counted once."""
    intervals = []
    active = None
    deleted = None
    for event in sorted(operations, key=lambda item: item["created_at"]):
        start = timestamp(event["created_at"])
        if start > now:
            raise ValueError("A compute operation is in the future")
        finish = min(timestamp(event["finished_at"]), now) if event.get("finished_at") else now
        if finish < start:
            raise ValueError("A compute operation finishes before it starts")
        failed = bool(event.get("status", {}).get("code", 0))
        name = event["description"]
        if name == "Start Instance":
            if failed:
                intervals.append((start, finish))
            elif active is None:
                active = start
        elif name in ("Stop Instance", "Delete Instance") and not failed and event.get("finished_at"):
            if active is not None:
                intervals.append((active, finish))
                active = None
            if name == "Delete Instance":
                deleted = finish
    if active is not None:
        intervals.append((active, now))
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    seconds = sum((end - start).total_seconds() for start, end in merged)
    disk_seconds = max(0., ((deleted or now) - disk_created).total_seconds())
    gpu_cost = Decimal(str(seconds)) * Decimal(str(hourly_rate)) / Decimal(3600)
    disk_cost = Decimal(str(disk_seconds)) * Decimal(str(disk_hourly_rate)) / Decimal(3600)
    return {"compute_seconds_upper": seconds, "compute_usd_upper": float(gpu_cost),
            "disk_seconds_upper": disk_seconds, "disk_usd_upper": float(disk_cost),
            "total_usd_upper": float(gpu_cost + disk_cost), "open_compute_interval": active is not None}


def report(root=Path("artifacts/nebius/full-history-v1")):
    now = datetime.now(timezone.utc)
    entries = []
    instances = [
        (root, 4.5, root / "vm-budget.json", "created_at"),
        (root / "parallel", 36., root / "eight-gpu-budget.json", "updated_at"),
    ]
    if (root / "rtx6000" / "resources.json").exists():
        instances.append((root / "rtx6000", 14.4, root / "rtx6000" / "vm-budget.json", "created_at"))
    for directory, rate, budget_path, date_key in instances:
        operations = json.loads((directory / "operations.json").read_text())["operations"]
        budget = json.loads(budget_path.read_text())
        resources = json.loads((directory / "resources.json").read_text())
        if any(event["resource_id"] != resources["instance_id"] for event in operations):
            raise ValueError("A cost record belongs to a different VM")
        cost = instance_cost(operations, now, rate, budget.get("disk_hourly_usd", .012444416), timestamp(budget[date_key]))
        entries.append({"instance_id": resources["instance_id"], "hourly_rate_usd": rate, **cost})
    spent = sum(item["total_usd_upper"] for item in entries)
    result = {"as_of": now.isoformat(), "project_ceiling_usd": 600., "instances": entries,
              "estimated_spend_upper_usd": spent, "remaining_under_ceiling_usd": max(0., 600. - spent),
              "method": "Quoted rates applied from start requests through completed stops. Includes failed scheduling intervals and continuous disk storage. Conservative estimate, not an invoice or voucher balance."}
    (root / "cost-ledger.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(report(), indent=2))
