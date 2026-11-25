# Data understanding plan: data and gold-based metrics

Status as of Nov 17: shared tools, schema v2 and the uniqueness metric are in place.

The automatic checks (DU-6) are required: every later number depends on them.

## Data generation

### DU-1 Schema v2 ✅ done
`owner`, derived `edrsr_type`, `gold_edrsr_policy`, apostrophe normalization, stricter validator. 14 tests in `tests/test_kit.py`.

### DU-2 Population v2: `data_understanding/population.py` ✅ done
- 2,000 people; P0001–P0008 copied unchanged from `seed_tools.TARGETS`.
- Surnames: about 70% common real Ukrainian surname stems (realistic difficulty for maskers) and about 30% constructed from stem + suffix type, to test generalization. Store `surname_type` ∈ {`chuk` (-чук/-юк/-ук), `enko`, `skyi` (-ський/-ська, -цький), `adj` (-ий/-а), `yshyn` (-ишин)} so inflection is deterministic. Aim for 400+ distinct surnames.
- First names: about 30 per gender, each with patronymic forms (m/f) and 1–2 diminutives.
- Places: 5–8 oblasts with weighted settlements (city > town > village). This affects k on village facts.
- Occupations: about 20, with gender constraints only where real (not "медична сестра" for men, etc.).
- `targets.csv`: about 150 targets with genre from event (`court_*` → court, `award_*`/`grant_*` → news, `dismissal_*` → forum), plus 1–3 planted look-alikes each (same gender, birth_year, oblast, occupation).
- Deterministic (fixed seed). **Accept:** columns = `POP_COLUMNS` (+ `surname_type` is fine), 2,000 rows, P0001–P0008 identical, the validator passes on seed docs against the new population.

### DU-3 Name forms: `data_understanding/names.py` ✅ done
- `forms(first, patronymic, surname, gender, surname_type) -> set[str]`: all 7 cases of each part, full-name orders (І П Б, Б І П), initials ("Т. П.", "Т.П."), diminutives and vocative.
- Paradigm tables by surname type and gender (-енко and -чук are invariant for women; -ський declines like an adjective).
- Side characters the LLM invents go through the same rules (`side_forms`). pymorphy3 was tested on 10 made-up surnames and dropped: it picks the invariant feminine reading for -чук/-енко/-юк and reads -ишин as a plural noun.
- **Accept:** forms of P0001–P0005 include every target surface in `seed_docs.py`.

### DU-4 Fact plan: `data_understanding/fact_plan.py` ✅ done
Output: `fact_plans.jsonl`, one plan per target (`D101`…). Each plan has `facts` (attr, category, DI/QI, suggested text, true value, and `exact` for the ones the checks compare: age, birth year, children, address), `names` (forms that must appear), `side_characters`, and `identifiers` (case number, РНОКПП, employer, email, phone). The event is always one of the facts; 1–5 more are drawn by genre weights, so `n_qi` runs from 2 to 6.

Per target, sample:
- 2–6 QIs to reveal, weighted by genre (court: birth year, address, family status, claim; news: age, village, occupation, award; forum: age, city, job, dismissal). The spread of QI counts gives a spread of k.
- The exact surface wording from population values ("34-річна" = doc_year − birth_year; "трьох дітей").
- Required name forms: ≥1 oblique case; court docs get the surname-first full name and initials; news gets first name + patronymic; some docs get a diminutive or vocative.
- Side characters (judge, lawyer, relative, boss) with invented names.
**Accept:** plans are JSON, deterministic, and cover all genres.

### DU-5 Generation: `data_understanding/generate.py` and `docs/prompts/generate_v2.md` ✅ done
`llm.py` is the client (env/.env settings, disk cache, throttle and backoff for OpenRouter's free tier). `generate.py` builds the prompt from the plan and two seed docs of the same genre, parses the reply, runs basic checks (validator, every planned attr tagged for E1, identifiers tagged, name forms present), and retries twice with the error list. `bakeoff.py` compares models on the same 10 plans (4 court, 3 news, 3 forum). Running it for real waits on an endpoint and on DU-6, since the bake-off should use the full checks.
- OpenAI-compatible client (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`), so the same code works with vLLM on vast.ai or any API.
- Prompt: genre, the profile, the fact plan, the tag syntax, 2 seed docs as few-shot examples. "Include exactly these facts; tag every mention of every person."
- Cache every response on disk keyed by (target, plan hash, prompt version, model).
- Parse → checks (DU-6) → regenerate up to 2 times → drop and log.

### DU-6 Automatic checks: `data_understanding/checks.py` ✅ done
1. `validate_gold` (offsets, fields, leftover tags, owners).
2. Fact-plan coverage: every planned fact has a span with that `attr` owned by E1.
3. **Untagged names:** every form from DU-3 (target plus side characters' tagged surfaces) that appears outside a span → fail.
4. Fact consistency: stated age matches doc_year − birth_year (±1); the number of children matches.
5. Sanity: length within genre range; the target is mentioned ≥3 times.
Output a per-doc pass/fail report. **Accept:** all 5 seed docs pass; hand-broken copies fail.
Done: `checks.py DIR` prints the report and writes `check_report.jsonl`; `generate.py` uses `check_doc` for its retries. Word limits are loose (court 80–800, news and forum 50–600) because the seed docs are short. Known limit: surnames that are also common words (Білий, Надія, Віра) can give a false "untagged name" at the start of a sentence; the retry usually fixes it, otherwise read the doc.

### DU-7 Sample and full corpus ✅ done
- Sample: 30 docs (10 per genre) → `data/sample/` (`population.csv`, `gold_docs.jsonl`, plus `gold_conditions` output as `masked_docs.jsonl`).
- Full: about 150 docs → `data/full/`.
- **Picking the LLM:** generate the same 10 plans with each candidate model; pick the one with the highest DU-6 pass rate, then read 3 docs per model for naturalness.

Result: Gemma 4 31B (`google/gemma-4-31B-it`, vLLM on one A100 80GB), prompt v2. No full bake-off: it was the only model on the GPU, and its pass rate was high enough. Sample: 30/30 passed (22 on the first try). Full: 147/150 passed (102 on the first try, 206 calls, 12 minutes); three court docs were dropped after three attempts (misplaced tag fields, one missing initials form). The full corpus is 50 news, 50 forum and 47 court docs.

v1 → v2, after reading the first three docs:
- Required oblique forms are only ones unique to their case (Марії is gen/dat/loc, so it is never asked for; Марією is), and each comes with a hint about where that case fits. The model used to copy the plan's case label onto a form in a different case.
- Organisations get attr=settlement/oblast only when their name contains the person's place; a check now enforces it.
- A new check rejects a name tag holding several parts ("Віталій Артемович" as one span). It was the most common retry reason (38 of 206 attempts).
- Forum authors mention themselves through an introduction, a quoted address or a signature, not in the third person.

First k-anonymity on the full corpus (`uniqueness.py data/full`): with everything masked, median k = 1054 (only gender visible); with only direct identifiers masked, 90% of documents have k = 1; with registry-style masking, 88%; with everything masked except one oblique name mention, 35% (median k = 26).

## Validation and metrics

### DU-8 Manual check of about 20 docs (stratified by genre), protocol in `docs/manual_check.md`
For each doc check that:
- nothing personal is left untagged
- the DI/QI labels are sensible
- the case labels are right
- the text reads like its genre
Report error rates in the Data section.

### DU-9 Recall metrics: `data_understanding/recall.py`
- Mention-level and entity-level recall, using the official open-mention rule (a mention is open if any of its words is less than half masked). Ignore labels.
- Splits: DI vs QI, category, `case` (nom vs oblique), `name_part`.
- Person-level "fully protected" via `owner`.
- Input: any `masked_docs.jsonl` with offsets; no lemma matching needed.

### DU-10 Uniqueness: `data_understanding/uniqueness.py` ✅
Handles leaked name parts, gender always exposed, settlement → oblast and settlement type, and age ±1.

### DU-11 Official test set → gold format (evaluation only, never tuning)

### DU-12 Writing: Data, Ethics and entity-metrics sections
