import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "model_training"))

import common  # noqa: E402
import llm_masker  # noqa: E402
import regex_rules  # noqa: E402
import rule_masker  # noqa: E402
import run_all  # noqa: E402
import seed_tools as st  # noqa: E402


def found(text, spans):
    spans = common.resolve_overlaps([common.tidy(text, s) for s in spans])
    return [(s["category"], text[s["start"]:s["end"]]) for s in spans]


@pytest.mark.parametrize("text,expected", [
    ("тел. +380 67 000 12 34.", ("CODE", "+380 67 000 12 34")),
    ("(РНОКПП 3012345678)", ("CODE", "3012345678")),
    ("пишіть на a.b95@example.com.", ("CODE", "a.b95@example.com")),
    ("Справа № 640/9071/22", ("CODE", "№ 640/9071/22")),
    ("12 травня 2023 року суд", ("DATETIME", "12 травня 2023 року")),
    ("У березні 2024 року мене", ("DATETIME", "У березні 2024 року")),
    ("Позивачка, 1985 р. н., медична", ("DATETIME", "1985 р. н.")),
    ("34-річна педагогиня", ("DEM", "34-річна")),
    ("у розмірі 48 600 грн.", ("QUANTITY", "48 600 грн.")),
    ("за адресою: м. Харків, вул. Вигадана, буд. 7, кв. 12.",
     ("LOC", "м. Харків, вул. Вигадана, буд. 7, кв. 12")),
    ("на Вінниччині", ("LOC", "Вінниччині")),
    ("до ТОВ «Вигадана Логістика» про", ("ORG", "ТОВ «Вигадана Логістика»")),
])
def test_regex_layer(text, expected):
    assert expected in found(text, regex_rules.find(text))


def test_regex_no_false_region_in_surname():
    assert found("Андрій Ліщинчук", regex_rules.find("Андрій Ліщинчук")) == []


def test_longest_span_wins():
    spans = [{"start": 0, "end": 5, "category": "A"}, {"start": 3, "end": 12, "category": "B"},
             {"start": 12, "end": 14, "category": "C"}]
    assert [s["category"] for s in common.resolve_overlaps(spans)] == ["B", "C"]


def test_rule_names_and_clusters():
    text = ("за позовом Ковальчинського Тараса Петровича до відповідача. "
            "Ковальчинський Т. П. зазначив. Суд надав слово Ковальчинському Тарасові. "
            "Фермер із Сосонки Андрій Ліщинчук.")
    row = common.to_row("X", "rule", text, rule_masker.mask_spans(text))
    m = row["masked_text"]
    assert "Ковальчин" not in m and "Тарас" not in m and "Петрович" not in m
    assert m.count("ОСОБА_1") == 3 and "ОСОБА_2" in m  # Ліщинчук is someone else
    assert "Сосонки ОСОБА" not in m  # a village, not part of the name


def test_rule_inflected_first_names_and_diminutive():
    text = "Колеги привітали Оксану. Односельці називають його Андрійком. «Олександре, ти винен»."
    m = common.to_row("X", "rule", text, rule_masker.mask_spans(text))["masked_text"]
    assert "Оксану" not in m and "Андрійком" not in m and "Олександре" not in m


def test_rule_on_seed_validates():
    gold = st.read_jsonl(st.SEED_DIR / "gold_docs.jsonl")
    rows = rule_masker.run(gold)
    assert st.validate_masked(rows, gold) == []
    scores = common.score(gold, rows)["rule"]
    assert scores["span_recall"]["cat=PERSON"] > 0.9


class FakeClient:
    def __init__(self, content):
        self.calls = 0
        self.content = content
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls += 1
        msg = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def fake_answer(entities):
    return "```json\n" + json.dumps({"entities": entities}, ensure_ascii=False) + "\n```"


def llm_row(monkeypatch, tmp_path, text, entities):
    monkeypatch.setattr(llm_masker, "CACHE_DIR", tmp_path)
    client = FakeClient(fake_answer(entities))
    spans, missing = llm_masker.mask_doc({"doc_id": "X", "text": text}, model="fake",
                                         client=client)
    return common.to_row("X", "llm", text, spans), missing, client


def test_llm_alignment_and_cache(tmp_path, monkeypatch):
    text = "Привітали Оксану Вигаданчук. Пані Вигаданчук з Вербівки."
    ents = [{"category": "PERSON", "mentions": ["Оксану Вигаданчук", "Петро"]},
            {"category": "LOC", "mentions": ["Вербівки"]}]
    row, missing, client = llm_row(monkeypatch, tmp_path, text, ents)
    assert row["masked_text"] == "Привітали ОСОБА_1. Пані ОСОБА_1 з МІСЦЕ_1."
    assert missing == ["Петро"]  # invented by the model
    llm_masker.mask_doc({"doc_id": "X", "text": text}, model="fake", client=client)
    assert client.calls == 1


def test_llm_matches_inflected_forms(tmp_path, monkeypatch):
    text = "разом із чоловіком Ігорем. Фермер із Сосонки. Лист Щербанюку О. І. надіслано."
    ents = [{"category": "PERSON", "mentions": ["Ігор"]},
            {"category": "LOC", "mentions": ["Сосонка"]},
            {"category": "PERSON", "mentions": ["Щербанюк О. І."]}]
    row, missing, _ = llm_row(monkeypatch, tmp_path, text, ents)
    assert missing == []
    assert "Ігорем" not in row["masked_text"] and "Сосонки" not in row["masked_text"]
    assert "Щербанюку" not in row["masked_text"] and "О. І." not in row["masked_text"]


def test_llm_masks_name_parts_and_keeps_people_apart(tmp_path, monkeypatch):
    text = "Привітали Оксану Вигаданчук. Вигаданчук сама все зробила. Директорка Галина Сидоренко."
    ents = [{"category": "PERSON", "mentions": ["Оксану Вигаданчук"]},
            {"category": "PERSON", "mentions": ["Галина Сидоренко"]}]
    row, _, _ = llm_row(monkeypatch, tmp_path, text, ents)
    assert row["masked_text"] == "Привітали ОСОБА_1. ОСОБА_1 сама все зробила. Директорка ОСОБА_2."


def test_llm_capitalized_mention_skips_common_word(tmp_path, monkeypatch):
    text = "Роман прочитав роман."
    row, _, _ = llm_row(monkeypatch, tmp_path, text, [{"category": "PERSON", "mentions": ["Роман"]}])
    assert row["masked_text"] == "ОСОБА_1 прочитав роман."


def test_llm_settings_prefer_mask_vars(monkeypatch):
    monkeypatch.setattr(llm_masker, "load_env", lambda: {
        "LLM_MODEL": "gemma", "LLM_BASE_URL": "http://a/v1", "MASK_LLM_MODEL": "qwen"})
    for k in ("LLM_MODEL", "MASK_LLM_MODEL", "LLM_BASE_URL", "MASK_LLM_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    cfg = llm_masker.settings()
    assert cfg["model"] == "qwen" and cfg["base_url"] == "http://a/v1"
    assert cfg["max_tokens"] == 8000 and cfg["no_think"] is False


def test_strip_thoughts():
    assert llm_masker.strip_thoughts("<think>hmm</think>\n{\"entities\": []}") == '{"entities": []}'
    assert llm_masker.strip_thoughts("<think>never closed") == ""


def test_llm_bad_json_gives_no_spans():
    assert llm_masker.parse_entities("sorry, I cannot") == []


def test_run_all_rule_only(tmp_path):
    out = tmp_path / "masked.jsonl"
    assert run_all.main([str(st.SEED_DIR), "--systems", "rule", "--out", str(out)])
    rows = st.read_jsonl(out)
    assert {r["system_or_condition"] for r in rows} >= {"rule", "gold_full", "gold_drop_p20"}
