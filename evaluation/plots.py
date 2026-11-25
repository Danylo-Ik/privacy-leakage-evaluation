"""Figures and the main table from the scoring results.

Usage: python evaluation/plots.py DIR [--results DIR/results] [--out RESULTS/figures]

Reads the CSV files written by score.py and writes PNG and PDF figures plus main_table.md:

- headline_n100, headline_n10   masking recall against re-identification, one point per condition
- reid                          top-1 per condition with the no-document baseline
- dropout                       top-1 and k = 1 against the share of mentions left open
- k_buckets                     top-1 by k where the target's name is fully masked
- gender                        gender accuracy per condition, and per genre when all is masked
- lists                         what the two list designs give away without the document

A figure whose data is missing is skipped with a message. Needs the `evaluation` group.
"""
import argparse
import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, QUIET, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8f8d86", "#e4e3dd", "#ffffff"
LEADER = "#bdbcb5"
SYSTEMS = ("rule", "spacy", "llm")
NAMES = {"no_document": "no document", "gold_full": "all masked", "gold_di_only": "DI only",
         "gold_edrsr_policy": "registry policy", "gold_miss_one_oblique": "one oblique name left",
         "gold_keep_patronymic": "patronymic left", "gold_drop_p05": "5% left open",
         "gold_drop_p10": "10% left open", "gold_drop_p20": "20% left open",
         "gold_drop_p40": "40% left open", "rule": "rule-based", "spacy": "spaCy NER",
         "llm": "LLM masker", "unmasked": "unmasked text"}
DROPS = {"gold_full": 0, "gold_drop_p05": 5, "gold_drop_p10": 10, "gold_drop_p20": 20,
         "gold_drop_p40": 40}

plt.rcParams.update({
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.edgecolor": GRID, "axes.labelcolor": QUIET, "xtick.color": QUIET, "ytick.color": QUIET,
    "text.color": INK, "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "legend.frameon": False,
    "xtick.major.size": 0, "ytick.major.size": 0, "pdf.fonttype": 42})


# ---------- data ----------

def number(text):
    try:
        return float(text)
    except ValueError:
        return text or None


def read(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [{k: number(v) for k, v in row.items()} for row in csv.DictReader(f)]


def load(results):
    return {name: read(Path(results) / f"{name}.csv")
            for name in ("summary", "reid", "attributes", "gender", "k_buckets")}


def reid(data, design, n):
    return {r["condition"]: r for r in data["reid"] if (r["design"], r["n"]) == (design, n)}


def name(condition):
    return NAMES.get(condition, condition)


def pct(value):
    return 100 * value


def color(condition):
    return BLUE if condition in SYSTEMS else MUTED if condition == "no_document" else ORANGE


# ---------- drawing helpers ----------

def percent_axis(ax, which="y", label=None, pad=3):
    getattr(ax, f"set_{which}lim")(-pad, 100 + pad)
    getattr(ax, f"set_{which}ticks")([0, 25, 50, 75, 100])
    getattr(ax, f"set_{which}ticklabels")(["0%", "25%", "50%", "75%", "100%"])
    if label:
        getattr(ax, f"set_{which}label")(label)


def dot(ax, x, y, c, **kw):
    ax.plot([x], [y], "o", ms=7, color=c, mec=SURFACE, mew=1.5, zorder=4, **kw)


def spread(values, gap, low, high):
    """Label positions close to `values` (ascending), at least `gap` apart, inside low-high."""
    out = []
    for v in values:
        out.append(max(v, out[-1] + gap) if out else max(v, low))
    over = out[-1] - high if out else 0
    if over > 0:
        out[-1] = high
        for i in range(len(out) - 2, -1, -1):
            out[i] = min(out[i], out[i + 1] - gap)
    return out


def label_points(ax, points, xmin, xmax):
    """Names in a column at the left of the points, tied to them by thin lines."""
    points = sorted(points, key=lambda p: p[1])
    places = spread([p[1] for p in points], 6.6, -2, 104)
    x_text = xmin + 0.015 * (xmax - xmin)
    for (x, y, text), y_text in zip(points, places):
        ax.annotate(text, (x, y), (x_text, y_text), va="center", ha="left", fontsize=7.5, color=QUIET,
                    arrowprops={"arrowstyle": "-", "color": LEADER, "lw": 0.6, "shrinkA": 2, "shrinkB": 4},
                    zorder=2)


def interval_rows(ax, rows, colors, value="top1", low="top1_low", high="top1_high", order=None):
    """Horizontal dots with intervals, first condition on top, the value at the right.
    `order` lists the conditions to leave room for; those without a row stay empty."""
    order = order or [r["condition"] for r in rows]
    for r in rows:
        i, c = len(order) - 1 - order.index(r["condition"]), colors(r["condition"])
        ax.plot([pct(r[low]), pct(r[high])], [i, i], color=c, lw=2, alpha=0.45, zorder=3,
                solid_capstyle="round")
        dot(ax, pct(r[value]), i, c)
        ax.text(103, i, f"{pct(r[value]):.0f}%", va="center", ha="left", fontsize=8, color=INK)
    ax.set_yticks(range(len(order)), [name(c) for c in reversed(order)])
    ax.set_ylim(-0.6, len(order) - 0.4)
    ax.grid(axis="y", visible=False)
    percent_axis(ax, "x")


def kind_legend(ax, **kw):
    handles = [plt.Line2D([], [], marker="o", ls="", ms=7, color=c, mec=SURFACE, label=t)
               for c, t in ((BLUE, "masking system"), (ORANGE, "controlled condition"))]
    ax.legend(handles=handles, fontsize=8, **kw)


# ---------- figures ----------

def headline(data, n):
    rows, summary = reid(data, "balanced", n), {r["condition"]: r for r in data["summary"]}
    conds = [c for c in rows if c in summary and c != "unmasked"]
    if not conds:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.9), sharey=True)
    for ax, col, title in ((axes[0], "mention_recall", "Name mentions masked"),
                           (axes[1], "entity_recall", "Persons with every mention masked")):
        xs = [pct(summary[c][col]) for c in conds]
        span = 100 - min(xs)
        xmin = min(xs) - 0.62 * max(span, 20)
        for c, x in zip(conds, xs):
            r = rows[c]
            ax.plot([x, x], [pct(r["top1_low"]), pct(r["top1_high"])], color=color(c), lw=2, alpha=0.35,
                    zorder=3, solid_capstyle="round")
            dot(ax, x, pct(r["top1"]), color(c))
        label_points(ax, [(x, pct(rows[c]["top1"]), name(c)) for c, x in zip(conds, xs)], xmin, 100)
        ax.set_xlim(xmin, 100 + 0.04 * (100 - xmin))
        ticks = [t for t in range(0, 101, 10) if t >= min(xs) - 5]
        ax.set_xticks(ticks, [f"{t}%" for t in ticks])
        ax.set_xlabel(title)
        ax.grid(axis="x", visible=False)
        percent_axis(ax)
        if "no_document" in rows:
            y = pct(rows["no_document"]["top1"])
            ax.axhline(y, color=MUTED, lw=1.2, zorder=1)
            ax.text(100 + 0.04 * (100 - xmin), y + 1.2, f"no document {y:.0f}%", ha="right", va="bottom",
                    fontsize=7.5, color=QUIET)
    axes[0].set_ylabel(f"Target ranked first, N = {n}")
    kind_legend(axes[1], loc="upper right", bbox_to_anchor=(1.0, 1.12), ncols=2)
    fig.suptitle("High recall does not mean that the person is safe", x=0.01, ha="left", fontsize=11,
                 fontweight="bold")
    fig.tight_layout()
    return fig


def reid_figure(data):
    sizes = [n for n in (100, 10) if reid(data, "balanced", n)]
    if not sizes:
        return None
    first = reid(data, "balanced", sizes[0])
    order = sorted(first, key=lambda c: (c != "no_document", first[c]["top1"]))
    fig, axes = plt.subplots(1, len(sizes), figsize=(5.2 * len(sizes), 0.34 * len(order) + 1.5),
                             sharey=True, squeeze=False)
    for ax, n in zip(axes[0], sizes):
        rows = reid(data, "balanced", n)
        interval_rows(ax, [rows[c] for c in order if c in rows], color, order=order)
        ax.set_title(f"N = {n}")
        ax.set_xlabel("Target ranked first (95% interval)")
    kind_legend(axes[0][-1], loc="lower right", bbox_to_anchor=(1.0, 1.0), ncols=2)
    fig.tight_layout()
    return fig


def dropout(data):
    rows, summary = reid(data, "balanced", 100), {r["condition"]: r for r in data["summary"]}
    conds = [c for c in DROPS if c in rows and c in summary]
    if len(conds) < 2:
        return None
    others = [c for c in ("gold_full", "gold_keep_patronymic", "gold_miss_one_oblique") if c in rows]
    fig, (ax, right) = plt.subplots(1, 2, figsize=(10, 3.8), width_ratios=(1.5, 1))
    xs = [DROPS[c] for c in conds]
    ax.fill_between(xs, [pct(rows[c]["top1_low"]) for c in conds],
                    [pct(rows[c]["top1_high"]) for c in conds], color=BLUE, alpha=0.12, lw=0)
    series = ((BLUE, "attack: target ranked first, N = 100", [pct(rows[c]["top1"]) for c in conds]),
              (ORANGE, "k = 1: only one person matches", [pct(summary[c]["pct_k1"]) for c in conds]))
    for c, text, ys in series:
        ax.plot(xs, ys, color=c, lw=2, marker="o", ms=7, mec=SURFACE, mew=1.5, label=text, zorder=3)
        ax.text(xs[-1] + 0.8, ys[-1], f"{ys[-1]:.0f}%", va="center", fontsize=8)
    ax.set_xticks(xs, [f"{x}%" for x in xs])
    ax.set_xlim(-1, xs[-1] + 4)
    ax.set_xlabel("Mentions left open at random")
    ax.grid(axis="x", visible=False)
    percent_axis(ax, label="Documents")
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title("Risk against incomplete masking")
    interval_rows(right, [rows[c] for c in others], lambda c: BLUE)
    right.set_title("A single leak")
    right.set_xlabel("Target ranked first, N = 100")
    fig.tight_layout()
    return fig


def k_buckets(data):
    rows = [r for r in data["k_buckets"] if r["top1"] is not None]
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(6, 3.6))
    labels = list(dict.fromkeys(str(r["k"]).replace(".0", "") for r in data["k_buckets"]))
    for shift, c, n in ((-0.12, BLUE, 100), (0.12, ORANGE, 10)):
        part = [r for r in rows if r["n"] == n]
        for r in part:
            x = labels.index(str(r["k"]).replace(".0", "")) + shift
            ax.plot([x, x], [pct(r["low"]), pct(r["high"])], color=c, lw=2, alpha=0.45,
                    solid_capstyle="round", zorder=3)
            dot(ax, x, pct(r["top1"]), c)
        if part:
            ax.plot([], [], "o", ms=7, color=c, label=f"N = {n}")
    counts = {str(r["k"]).replace(".0", ""): int(r["rows"]) for r in rows if r["n"] == 100} or \
             {str(r["k"]).replace(".0", ""): int(r["rows"]) for r in rows}
    ax.set_xticks(range(len(labels)), [f"{v.replace('-', '–')}\n({counts.get(v, 0)} texts)" for v in labels])
    ax.set_xlim(-0.5, len(labels) - 0.5)
    ax.set_xlabel("k: people who match what the text still shows")
    ax.grid(axis="x", visible=False)
    percent_axis(ax, label="Target ranked first")
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title("Does k predict the attack? (target's name fully masked)")
    fig.tight_layout()
    return fig


def gender(data):
    if not data["gender"]:
        return None
    order = sorted(data["gender"], key=lambda r: r["all"])
    full = next((r for r in data["gender"] if r["condition"] == "gold_full"), None)
    majority = next((r["majority"] for r in data["attributes"] if r["attribute"] == "gender"), None)
    fig, axes = plt.subplots(1, 2, figsize=(10, max(2.6, 0.32 * len(order) + 1.3)), width_ratios=(1.4, 1))
    interval_rows(axes[0], order, color, "all", "all_low", "all_high")
    axes[0].set_title("Gender guessed correctly")
    if full:
        genres = [{"condition": g, "v": full[g], "lo": full[f"{g}_low"], "hi": full[f"{g}_high"]}
                  for g in ("court", "news", "forum") if full[g] is not None]
        interval_rows(axes[1], genres, lambda c: ORANGE, "v", "lo", "hi")
    axes[1].set_title("Everything masked, by genre")
    for ax in axes:
        ax.set_xlabel("Documents (95% interval)")
        if majority is not None:
            ax.axvline(pct(majority), color=MUTED, lw=1.2, zorder=1)
            ax.text(pct(majority) - 1.5, -0.5, "commonest\nvalue", fontsize=7.5, color=QUIET, va="bottom",
                    ha="right")
    fig.tight_layout()
    return fig


def lists(data):
    cells = [(design, n, reid(data, design, n).get("no_document")) for n in (10, 100)
             for design in ("random", "balanced")]
    if any(r is None for _, _, r in cells):
        return None
    fig, ax = plt.subplots(figsize=(6, 3.4))
    xs = [0, 1, 2.5, 3.5]
    for x, (design, n, r) in zip(xs, cells):
        for shift, c, v in ((-0.19, BLUE, r["top1"]), (0.19, ORANGE, r["rule_without_document"])):
            ax.bar(x + shift, pct(v), 0.34, color=c, zorder=3)
            ax.text(x + shift, pct(v) + 1.5, f"{pct(v):.0f}%", ha="center", fontsize=8)
    ax.bar([0], [0], color=BLUE, label="LLM attacker")
    ax.bar([0], [0], color=ORANGE, label="simple rule: event, look-alikes, genre")
    ax.set_xticks(xs, [f"{design}\nN = {n}" for design, n, _ in cells])
    ax.grid(axis="x", visible=False)
    percent_axis(ax, label="Target found", pad=0)
    ax.set_ylim(0, 108)
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title("Found without reading the document")
    fig.tight_layout()
    return fig


# ---------- table ----------

def main_table(data):
    """Markdown table, one row per condition."""
    head = ["condition", "mentions", "persons", "QI", "k = 1", "median k", "top-1 N=100", "top-5 N=100",
            "top-1 N=10", "gender"]
    cols = ["mention_recall", "entity_recall", "qi_recall", "pct_k1", "median_k", "top1_n100", "top5_n100",
            "top1_n10", "gender_accuracy"]

    def cell(col, v):
        return "–" if v is None else f"{v:.0f}" if col == "median_k" else f"{pct(v):.1f}"
    lines = ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
    for r in data["summary"]:
        lines.append("| " + " | ".join([name(r["condition"])] + [cell(c, r[c]) for c in cols]) + " |")
    base = {n: reid(data, "balanced", n).get("no_document") for n in (10, 100)}
    row = dict.fromkeys(cols)
    if base[100]:
        row.update(top1_n100=base[100]["top1"], top5_n100=base[100]["top5"])
    if base[10]:
        row["top1_n10"] = base[10]["top1"]
    lines.append("| " + " | ".join(["no document"] + [cell(c, row[c]) for c in cols]) + " |")
    return "\n".join(lines) + "\n"


FIGURES = {"headline_n100": lambda d: headline(d, 100), "headline_n10": lambda d: headline(d, 10),
           "reid": reid_figure, "dropout": dropout, "k_buckets": k_buckets, "gender": gender,
           "lists": lists}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--results", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    results = args.results or args.data_dir / "results"
    out = args.out or results / "figures"
    data = load(results)
    if not data["summary"]:
        sys.exit(f"No results in {results}; run score.py first.")
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for key, draw in FIGURES.items():
        fig = draw(data)
        if fig is None:
            print(f"{key}: skipped, no data yet")
            continue
        for ext in ("png", "pdf"):
            fig.savefig(out / f"{key}.{ext}", dpi=200, bbox_inches="tight")
        plt.close(fig)
        made.append(key)
    with open(out / "main_table.md", "w", encoding="utf-8", newline="\n") as f:
        f.write(main_table(data))
    print(f"wrote {', '.join(made)} and main_table.md to {out}")
    return made


if __name__ == "__main__":
    main()
