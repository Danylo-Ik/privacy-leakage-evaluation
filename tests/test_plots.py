import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))

import plots as pl  # noqa: E402

CONDITIONS = [c for c in pl.NAMES if c not in ("no_document", "unmasked")]


def reid_row(cond, top1, n=100, design="balanced"):
    return {"design": design, "n": n, "condition": cond, "docs": 30, "top1": top1,
            "top1_low": max(top1 - 0.1, 0), "top1_high": min(top1 + 0.1, 1), "top5": min(top1 + 0.2, 1),
            "rule_without_document": 0.027}


@pytest.fixture
def data():
    tops = {c: i / len(CONDITIONS) for i, c in enumerate(CONDITIONS)}
    reid = [reid_row(c, t, n) for n in (10, 100) for c, t in tops.items()]
    reid += [reid_row("no_document", 0.02, n, design) for n in (10, 100) for design in ("balanced", "random")]
    summary = [{"condition": c, "docs": 30, "mention_recall": 0.9, "entity_recall": 0.8, "qi_recall": 0.5,
                "target_closed": 0.7, "di_recall": 0.9, "pct_k1": 0.4, "median_k": 26.0, "top1_n100": t,
                "top5_n100": t, "top1_n10": t, "top5_n10": t, "gender_accuracy": None}
               for c, t in tops.items()]
    gender = [{"condition": c, **{f"{g}{s}": 0.9 for g in ("all", "court", "news", "forum")
                                  for s in ("", "_low", "_high")}} for c in CONDITIONS]
    buckets = [{"n": n, "k": k, "rows": 40.0, "docs": 20.0, "top1": 0.5, "low": 0.4, "high": 0.6}
               for n in (10, 100) for k in (1.0, "2-5", "6-50", "51+")]
    return {"summary": summary, "reid": reid, "gender": gender, "k_buckets": buckets,
            "attributes": [{"condition": "gold_full", "attribute": "gender", "majority": 0.52}]}


def test_every_figure_is_drawn(data):
    for key, draw in pl.FIGURES.items():
        assert draw(data) is not None, key
    pl.plt.close("all")


def test_figures_without_data_are_skipped():
    empty = {name: [] for name in ("summary", "reid", "attributes", "gender", "k_buckets")}
    assert all(draw(empty) is None for draw in pl.FIGURES.values())


def test_partial_data_leaves_room_for_every_condition(data):
    data["reid"] = [r for r in data["reid"] if r["n"] == 100 or r["condition"] in ("rule", "no_document")]
    fig = pl.reid_figure(data)
    assert [len(ax.get_yticks()) for ax in fig.axes] == [len(CONDITIONS) + 1] * 2
    pl.plt.close("all")


def test_every_condition_has_a_name():
    from run_attacks import load
    for cond in load(ROOT / "data" / "sample")["conditions"] + ["unmasked", "no_document"]:
        assert cond in pl.NAMES


def test_spread_keeps_order_gap_and_limits():
    out = pl.spread([10, 11, 12, 50, 99, 100, 100], 6, 0, 104)
    assert out == sorted(out) and out[-1] <= 104
    assert all(b - a >= 6 - 1e-9 for a, b in zip(out, out[1:]))
    assert pl.spread([20, 60], 6, 0, 104) == [20, 60]


def test_main_table(data):
    lines = pl.main_table(data).strip().split("\n")
    assert len(lines) == 2 + len(CONDITIONS) + 1
    assert all(line.count("|") == lines[0].count("|") for line in lines)
    assert "| 90.0 | 80.0 | 50.0 | 40.0 | 26 |" in lines[2]
    assert lines[-1].startswith("| no document | – |") and "2.0" in lines[-1]


def test_csv_values_are_read_back(tmp_path):
    (tmp_path / "reid.csv").write_text("design,n,top1\nbalanced,10,0.5000\nrandom,100,\n", encoding="utf-8")
    assert pl.read(tmp_path / "reid.csv") == [{"design": "balanced", "n": 10, "top1": 0.5},
                                              {"design": "random", "n": 100, "top1": None}]
    assert pl.read(tmp_path / "missing.csv") == []
