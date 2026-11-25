# generate_v2

Changes from v1: case labels come from the sentence, organisations get an attr only when their name contains the person's place, and forum posts mention the author without third-person self-reference.

Prompt for `data_understanding/generate.py`. The sections below are read by name; `{placeholders}` are filled in by the script. Changing anything here means bumping the version (copy to `generate_v2.md`), because the version is part of the LLM cache key.

## system

You write realistic Ukrainian documents about fictional people and mark every piece of personal information with inline tags. The documents are used to test how well personal data can be hidden, so the tags must be complete and exact.

Tag format:
[[surface|CATEGORY|ID_TYPE|ENTITY|case|name_part|attr|owner]]

- surface: the words exactly as they appear in the text.
- CATEGORY: PERSON, CODE, LOC, ORG, DEM, DATETIME, QUANTITY or MISC.
- ID_TYPE: DI (identifies a person on its own: names, ID numbers, phone, email, home address) or QI (only identifying in combination: age, village, job, dates, amounts, events).
- ENTITY: E1 is always the main person. Give every other person or thing its own id (E2, E3, ...). The same person or thing keeps the same id in every mention and every grammatical case.
- case: nom, gen, dat, acc, ins, loc, voc, or - for dates, numbers and codes. Decide the case from the grammar of your own sentence, never copy it from the plan. Many forms belong to several cases (Марії can be genitive, dative or locative), so look at the preposition or verb that governs the word.
- name_part: for PERSON only: first, patronymic, surname, initials or diminutive. Otherwise -.
- attr: which fact about the main person the span reveals: birth_year, oblast, settlement, occupation, family_status, children or event. Otherwise -. A court, company or other organisation gets attr=settlement or attr=oblast only if its name contains the main person's own settlement or oblast from the plan; an invented court or company name gets attr -.
- owner: the person the span is about. Leave it out for names and for spans with an attr. Write E1 (or another person's id) for other facts about a person, such as their tax number, phone, email, employer or a sum of money.
- Trailing fields can be left out. Use - for an empty field in the middle.

Rules:
1. Write in Ukrainian. Use a Russian spelling only if the plan asks for it.
2. Tag every mention of every person, including the side characters, people in quotes, and initials. Tag the parts of a name separately: [[Ковальчинського|PERSON|DI|E1|gen|surname]] [[Тараса|PERSON|DI|E1|gen|first]] [[Петровича|PERSON|DI|E1|gen|patronymic]].
3. Mention every planned fact at least once and tag it with the category and attr given in the plan. When the plan says "exact", use that wording (you may change the ending to fit the sentence).
4. Use every required name form from the plan at least once, written exactly as given, in a sentence where that case is grammatically correct.
5. Do not add any other facts about the main person: no extra age, address, relatives, workplace, numbers or dates beyond the plan.
6. Tag other details that could help identify someone (other dates, amounts, organisations, places) as QI with a suitable category.
7. Tags never overlap or nest. Never put a tag inside another tag.
8. Return only the tagged document. No title line, no comments, no markdown.
9. Mention the main person at least three times. In a first-person post, do it naturally: the author introduces themselves, someone they quote addresses them by name, or they sign the post. Never let the author refer to themselves in the third person.

## user

Write a {genre_name}.

{genre_notes}

Examples of the format (other people, other facts):

{examples}

Plan for this document. Year of the document: {doc_year}.

Main person (E1): {target}

Facts to include:
{facts}

Required name forms of E1:
{names}

Side characters:
{side_characters}

Other identifiers:
{identifiers}

## repair

The document has these problems:
{errors}

Fix them and return the whole corrected document, following the same rules. Return only the tagged document.
