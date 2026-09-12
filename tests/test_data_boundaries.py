from copy import deepcopy
from datetime import date, timedelta

import pytest

from driftops.annotations import describe_channel, describe_window
from driftops.windows import observed_window, partition_for, read_yaml, seven_day_label


def history(days=36):
    return [{"date": date(2024, 7, 1) + timedelta(days=i), "failure": 0,
             "smart_5_raw": i, "smart_194_raw": 30} for i in range(days)]


def test_future_changes_cannot_change_window_or_description():
    rows = history()
    cutoff = date(2024, 7, 28)
    altered = deepcopy(rows)
    for row in altered:
        if row["date"] > cutoff:
            row.update(failure=1, smart_5_raw=999999, smart_194_raw=-999999)
    before = observed_window(rows, cutoff)
    after = observed_window(altered, cutoff)
    assert before == after
    assert describe_window(before, ["smart_5_raw", "smart_194_raw"]) == describe_window(
        after, ["smart_5_raw", "smart_194_raw"])


@pytest.mark.parametrize("damage", ["gap", "duplicate", "event"])
def test_bad_history_is_not_silently_repaired(damage):
    rows = history()
    if damage == "gap":
        rows.pop(10)
    elif damage == "duplicate":
        rows.append(deepcopy(rows[10]))
    else:
        rows[27]["failure"] = 1
    assert observed_window(rows, date(2024, 7, 28)) == []


def test_censoring_is_not_a_negative_label():
    rows = history()
    cutoff = date(2024, 7, 28)
    assert seven_day_label(rows, cutoff) == 0
    assert seven_day_label(rows[:30], cutoff) is None
    incomplete = [row for row in rows if row["date"] != date(2024, 7, 30)]
    assert seven_day_label(incomplete, cutoff) is None
    incomplete[-2]["failure"] = 1  # August 4 is inside the seven-day horizon.
    assert seven_day_label(incomplete, cutoff) == 1
    rows[27]["failure"] = 1
    assert seven_day_label(rows, cutoff) is None


def test_drive_and_label_time_partitions_do_not_overlap():
    config = read_yaml("config/splits.yaml")
    names = {name: set() for name in config["partitions"]}
    for i in range(1000):
        serial = f"fixture-{i}"
        name, _ = partition_for(serial, config)
        names[name].add(serial)
        assert partition_for(serial, config)[0] == name
    assert sum(map(len, names.values())) == len(set.union(*names.values())) == 1000
    assert all(names.values())
    prior_available = None
    for rule in config["partitions"].values():
        first = date.fromisoformat(rule["first_cutoff"])
        last = date.fromisoformat(rule["last_cutoff"])
        available = date.fromisoformat(rule["labels_available_by"])
        assert first <= last
        assert last + timedelta(days=config["horizon_days"]) <= available
        assert prior_available is None or prior_available < first
        prior_available = available


def test_counter_decreases_and_nonfinite_data_are_explicit():
    assert describe_channel("smart_5_raw", [0, 4, 1])["pattern"] == "counter reset or decrease"
    assert describe_channel("smart_194_raw", [30] * 28)["pattern"] == "constant"
    with pytest.raises(ValueError, match="finite"):
        describe_channel("smart_194_raw", [30, float("nan")])
