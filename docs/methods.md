# Methods overview

Track: **Evaluating Privacy Leakage**. Question: if a masker hides most personal data but misses a little, is the document still protected?

## Problem

Public bodies publish documents (court decisions, news, registers) that name private people. Before publishing, personal data is replaced with codes, as the court registry (ЄДРСР) does with `ОСОБА_1`, `АДРЕСА_1`, `НОМЕР_1`, `ІНФОРМАЦІЯ_1`. The same person gets the same code throughout a document. We measure how well that protects people.

## Two kinds of identifiers

- **Direct (DI):** identify a person on their own: full name, РНОКПП, phone, home address, email.
- **Quasi (QI):** harmless alone, identifying in combination: village, occupation, birth year, number of children, an award, the date of a lawsuit.

So masking can fail in two ways:

1. **One missed mention.** A name appears 4 times and 3 are masked. Per mention that is 75%; for the person it is 0%.
2. **Names masked, QIs left in.** The person is worked out from the context.

Seed doc D001 (50-person seed population): with everything masked, k = 26 (only gender leaks). With registry-style masking (names and codes only), k = 1. With everything masked except one name mention in the accusative ("Оксану Вигаданчук"), k = 1.

## Why Ukrainian is harder

- 7 cases: Ковальчинський / Ковальчинського / Ковальчинському…; oblique forms leak most.
- Name formats: patronymics, surname-first court order, initials ("Т. П."), diminutives ("Андрійком", "Сашко"), the vocative ("Олександре"), Russian spellings in old records.
- Gender is in the grammar (педагогиня, позивачка, сама, пояснила), so it leaks even when every name is masked.

## Data (synthetic; see SCHEMA.md)

- `population.csv`: about 2,000 fictional people. It makes k computable ("how many people match what's exposed?") and supplies the attacker's candidate lists. Targets have deliberate look-alikes.
- `gold_docs.jsonl`: 120–150 court/news/forum texts, one target each, with every sensitive span labelled (category, DI/QI, entity, case, name part, attribute, owner).
- `masked_docs.jsonl`: masker output, with offsets in the original text.
- The official 240-decision test set is for evaluation only (never tuning). It has entity-level gold for names but no population.

Why synthetic: we run attacks, so no real people; and scoring an attack needs ground truth about who each doc is about and who else looks similar.

## Producing masked text (model training)

- **Systems:** rule-based (regex + every case form of a generic name list), NER model, zero-shot LLM. Their errors are natural.
- **Controlled conditions:** gold masking with deliberate holes, so we know exactly what leaked: `gold_full`, `gold_di_only`, `gold_edrsr_policy`, `gold_drop_p05…p40`, `gold_miss_one_oblique`, `gold_keep_patronymic`.

Systems show what happens in practice; conditions show why.

## Measuring leakage

1. **Mention-level recall:** share of gold mentions masked (the optimistic number).
2. **Entity-level recall:** share of entities with *every* mention masked. A mention counts as open if any of its words is less than half masked (the official rule). Official "deanonymization risk (by name)" = 1 − entity recall for persons. Split by DI/QI, `case` and `name_part`. Person-level "fully protected" = every span the person `owns` is masked.
3. **Uniqueness / k-anonymity:** count population members matching the exposed facts (leaked name parts count; gender counts as always exposed). Report % with k = 1 and median k. This is a database lookup, no LLM.
4. **LLM attacks:** re-identification (masked doc plus N = 10/100 candidate profiles with full names; top-1/top-5 vs chance 1/N and vs a no-document baseline) and attribute inference (gender, age bracket, oblast, occupation).

## Research questions

| RQ | In plain words | Inputs | Metric | Expected |
|---|---|---|---|---|
| RQ1 | Does mention-level scoring hide person-level failure? | 3 systems (+ official test set) | mention vs entity recall | yes, a large gap |
| RQ2 | How fast does risk grow as masking gets less complete? | drop-out, one oblique miss, patronymic kept | re-ID top-1, k | not linearly: one name leak almost fully identifies the person |
| RQ5 | With all names masked, how many stay unique? | `gold_edrsr_policy`, `gold_di_only` | % k = 1, re-ID | a large share |

Headline plot: mention recall (x) vs re-ID top-1 (y), one point per system/condition. Second result: a gender-leak table.
