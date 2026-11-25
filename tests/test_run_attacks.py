import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))

import candidates as cd  # noqa: E402
import run_attacks as ra  # noqa: E402

SAMPLE = ROOT / "data" / "sample"
CONDITIONS = ["gold_full", "rule"]
FIRST_FIVE = ["C001", "C002", "C003", "C004", "C005"]
ATTRS = {"gender": "F", "birth_decade": 1970, "oblast": "Харківська", "occupation": "кухар"}


class FakeModel:
    """Stands in for llm.chat. `answer` gets the call number and the messages."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, messages, temperature=0.8, max_tokens=None, extra=None, use_cache=True):
        self.calls.append({"messages": messages, "temperature": temperature, "extra": extra})
        return self.answer(len(self.calls), messages), {"prompt": 100, "completion": 10}, False


def ranking(labels=FIRST_FIVE):
    return json.dumps({"clues": "село", "ranking": labels}, ensure_ascii=False)


def attributes(**kw):
    return json.dumps({"clues": "позивачка", **ATTRS, **kw}, ensure_ascii=False)


@pytest.fixture
def model(monkeypatch):
    def use(answer):
        fake = FakeModel(answer if callable(answer) else lambda i, messages: answer)
        monkeypatch.setattr(ra.llm, "chat", fake)
        return fake
    return use


@pytest.fixture(scope="module")
def data():
    return ra.load(SAMPLE)


def jobs(data, task="reid", conditions=CONDITIONS, sizes=(10,), limit=3, name="fake"):
    return ra.make_jobs(data, task, name, conditions, sizes, limit=limit)


# ---------- jobs ----------

def test_full_grid_size(data):
    assert data["conditions"][0] == "gold_full" and len(data["conditions"]) == 12
    assert len(jobs(data, conditions=None, sizes=cd.SIZES, limit=None)) == 30 * 12 * 2
    assert len(jobs(data, "nodoc", sizes=cd.SIZES, limit=None)) == 30 * 2
    assert len(jobs(data, "attr", conditions=None, limit=None)) == 30 * 12


def test_jobs_are_unique_and_limit_is_spread_over_genres(data):
    js = jobs(data, conditions=None, sizes=cd.SIZES, limit=6)
    assert len({ra.key(j) for j in js}) == len(js)
    genre = {g["doc_id"]: g["genre"] for g in data["gold"]}
    docs = {j["doc_id"] for j in js}
    assert sorted(genre[d] for d in docs) == ["court", "court", "forum", "forum", "news", "news"]


def test_unmasked_condition_uses_the_original_text(data):
    gold = {g["doc_id"]: g["text"] for g in data["gold"]}
    for j in jobs(data, conditions=["unmasked"]):
        assert gold[j["doc_id"]] in j["messages"][1]["content"]


def test_unknown_condition_or_size_is_an_error(data):
    with pytest.raises(KeyError):
        jobs(data, conditions=["gold_fulll"])
    with pytest.raises(KeyError):
        jobs(data, sizes=(50,))


def test_no_document_jobs_hold_no_document(data):
    for j in jobs(data, "nodoc"):
        assert j["system_or_condition"] is None
        assert not any(text in j["messages"][1]["content"]
                       for (doc, _), text in data["texts"].items() if doc == j["doc_id"])


# ---------- one call ----------

def test_ranking_is_stored_as_people_and_the_target_is_found(data, model):
    model(ranking())
    for j in jobs(data, limit=None):
        row = ra.run_job(j)
        assert row["ranking"] == j["people"][:5]
        place = j["people"].index(j["target"]) + 1
        assert row["target_rank"] == (place if place <= 5 else None)
        assert row["parse_ok"] and row["attempts"] == 1


def test_invented_label_does_not_promote_the_next_one(data, model):
    j = jobs(data)[0]
    right = cd.labels(10)[j["people"].index(j["target"])]
    others = [label for label in cd.labels(10) if label != right]
    model(ranking(["C999", right] + others[:3]))
    row = ra.run_job(j)
    assert row["ranking"][0] is None and row["target_rank"] == 2


def test_bad_reply_is_repeated_at_a_higher_temperature(data, model):
    fake = model(lambda i, messages: "Не знаю." if i == 1 else ranking())
    row = ra.run_job(jobs(data)[0])
    assert row["attempts"] == 2 and row["errors"] == [] and row["parse_ok"]
    assert [c["temperature"] for c in fake.calls] == [0, 0.7]
    assert [c["extra"]["attempt"] for c in fake.calls] == [0, 1]
    assert row["usage"] == {"prompt": 200, "completion": 20}


def test_repeated_label_is_accepted_without_a_retry(data, model):
    fake = model(ranking(["C001", "C002", "C003", "C001", "C002"]))
    row = ra.run_job(jobs(data)[0])
    assert len(fake.calls) == 1 and len(row["ranking"]) == 3
    assert row["parse_ok"] and row["errors"]


def test_unreadable_replies_count_as_a_miss(data, model):
    fake = model("Sorry, I cannot identify people.")
    row = ra.run_job(jobs(data)[0])
    assert len(fake.calls) == 3
    assert not row["parse_ok"] and row["ranking"] == [] and row["target_rank"] is None
    assert row["errors"]


def test_best_reply_is_kept_when_none_is_perfect(data, model):
    replies = [ranking(["C001", "C002"]), ranking(FIRST_FIVE[:4]), "???"]
    model(lambda i, messages: replies[i - 1])
    row = ra.run_job(jobs(data)[0])
    assert len(row["ranking"]) == 4 and row["parse_ok"] and row["attempts"] == 3


def test_attribute_row(data, model):
    model(attributes())
    row = ra.run_job(jobs(data, "attr")[0])
    assert row["values"] == ATTRS and row["parse_ok"]
    assert row["design"] is None and row["n"] is None and "ranking" not in row


# ---------- files ----------

def test_second_run_makes_no_calls(data, model, tmp_path):
    fake, path = model(ranking()), tmp_path / "attacks" / "reid.jsonl"
    js = jobs(data)
    rows, failed = ra.run(js, path)
    assert (len(rows), failed, len(fake.calls)) == (6, 0, 6)
    assert ra.validate(rows, js) == []
    first = path.read_bytes()
    ra.run(js, path)
    assert len(fake.calls) == 6 and path.read_bytes() == first


def test_file_does_not_depend_on_the_order_of_the_runs(data, model, tmp_path):
    model(ranking())
    ra.run(jobs(data), tmp_path / "a.jsonl")
    for cond in reversed(CONDITIONS):
        ra.run(jobs(data, conditions=[cond]), tmp_path / "b.jsonl")
    assert (tmp_path / "a.jsonl").read_bytes() == (tmp_path / "b.jsonl").read_bytes()


def test_only_changed_documents_are_attacked_again(data, model, tmp_path):
    fake, path = model(ranking()), tmp_path / "reid.jsonl"
    old = jobs(data)
    ra.run(old, path)
    doc = old[0]["doc_id"]
    texts = dict(data["texts"])
    texts[doc, "rule"] += " Новий текст."
    new = jobs(dict(data, texts=texts))
    assert any("prompt changed" in e for e in ra.validate(ra.read_rows(path).values(), new))
    rows, _ = ra.run(new, path)
    assert len(fake.calls) == 7 and len(rows) == 6
    assert "Новий текст." in fake.calls[-1]["messages"][1]["content"]
    assert ra.validate(rows, new) == []


def test_rows_of_dropped_documents_are_removed(data, model, tmp_path):
    fake, path = model(ranking()), tmp_path / "reid.jsonl"
    js = jobs(data)
    ra.run(js, path)
    gone = js[0]["doc_id"]
    rest = [j for j in js if j["doc_id"] != gone]
    rows, _ = ra.run(rest, path, docs={j["doc_id"] for j in rest})
    assert len(fake.calls) == 6 and len(rows) == 4
    assert gone not in path.read_text(encoding="utf-8")


def test_another_model_adds_rows_instead_of_replacing(data, model, tmp_path):
    model(ranking())
    ra.run(jobs(data), tmp_path / "reid.jsonl")
    rows, _ = ra.run(jobs(data, name="other"), tmp_path / "reid.jsonl")
    assert len(rows) == 12


def test_failed_calls_are_left_for_the_next_run(data, model, tmp_path):
    path, js = tmp_path / "reid.jsonl", jobs(data)
    bad = js[0]["messages"]

    def flaky(i, messages):
        if messages == bad:
            raise RuntimeError("connection lost")
        return ranking()
    model(flaky)
    rows, failed = ra.run(js, path)
    assert (len(rows), failed) == (5, 1)
    assert len(ra.validate(rows, js)) == 1
    fake = model(ranking())
    rows, failed = ra.run(js, path)
    assert (len(rows), failed, len(fake.calls)) == (6, 0, 1)
    assert ra.validate(rows, js) == []


def test_run_stops_when_everything_fails(data, model, tmp_path):
    def broken(i, messages):
        raise RuntimeError("no server")
    fake = model(broken)
    js = jobs(data, conditions=None, limit=None)
    rows, failed = ra.run(js, tmp_path / "reid.jsonl", workers=2)
    assert rows == [] and failed >= ra.MAX_FAILURES
    assert len(fake.calls) < 50 < len(js)


def test_half_written_line_is_dropped(data, model, tmp_path):
    fake, path = model(ranking()), tmp_path / "reid.jsonl"
    js = jobs(data)
    ra.run(js, path)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1] + [lines[-1][:40]]), encoding="utf-8")
    rows, _ = ra.run(js, path)
    assert len(fake.calls) == 7 and ra.validate(rows, js) == []
    assert all(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())


def test_validate_rejects_missing_duplicate_and_foreign_rows(data, model, tmp_path):
    model(ranking())
    js = jobs(data)
    rows, _ = ra.run(js, tmp_path / "reid.jsonl")
    assert ra.validate(rows[1:], js) and ra.validate(rows + rows[:1], js)
    assert ra.validate([dict(rows[0], ranking=["P9999"])] + rows[1:], js)


# ---------- command line ----------

@pytest.mark.parametrize("task,answer,n_rows", [("reid", ranking(), 6), ("nodoc", ranking(), 3),
                                                ("attr", attributes(), 6)])
def test_main(model, monkeypatch, tmp_path, capsys, task, answer, n_rows):
    fake = model(answer)
    monkeypatch.setenv("LLM_MODEL", "fake")
    args = [str(SAMPLE), "--task", task, "--conditions", "gold_full,rule", "--n", "10",
            "--limit", "3", "--out", str(tmp_path)]
    assert ra.main(args) and ra.main(args)
    assert len(fake.calls) == n_rows
    assert "complete" in capsys.readouterr().out
    assert len((tmp_path / f"{task}.jsonl").read_text(encoding="utf-8").splitlines()) == n_rows


def test_dry_run_calls_nothing(model, capsys):
    fake = model(ranking())
    assert ra.main([str(SAMPLE), "--task", "reid", "--dry-run"])
    assert not fake.calls and "720 jobs" in capsys.readouterr().out
