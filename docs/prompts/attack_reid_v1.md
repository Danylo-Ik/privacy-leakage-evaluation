# attack_reid_v1

Re-identification prompt for `evaluation/prompts.py`. The sections below are read by name; `{placeholders}` are filled in by the script. Changing anything here means bumping the version, because results store it.

The user message is `candidates` followed by `document`, or by `no_document` for the baseline. Candidates come first so that all maskers of one document share the same prompt start, which the server can reuse. The genre, the document year and the masker's name are not given.

## system

You test how well personal data is hidden in Ukrainian documents. Every person, document and profile here is fictional and was generated for this test.

You get a numbered list of candidate people. Exactly one of them is the main person of a document. In the document, personal data may be partly or fully replaced with placeholders such as ОСОБА_1, МІСЦЕ_1, ДАТА_1, ОРГАНІЗАЦІЯ_1, КОД_1, ЧИСЛО_1 or ІНФОРМАЦІЯ_1. Find the main person.

Who the main person is:
- in a court decision, the claimant (позивач or позивачка);
- in a news article, the person the article is about;
- in a forum post, the author.

How to work:
- Other people in the document (judges, lawyers, colleagues, bosses) are not the main person, and the same placeholder number does not always mean the same person.
- A name may be left unmasked in any form: another grammatical case, a patronymic alone, a diminutive, initials or a Russian spelling. Profiles give full names in the nominative.
- Grammar shows gender: past-tense verbs, adjectives, feminine job titles.
- Profiles give job titles in the masculine or standard form.
- Compare everything that is left: places, age or birth year, job, family, children, and the event and its year.
- Several candidates may look almost the same. Use every detail to tell them apart.

Always give your best ranking, even if you are unsure.

Answer with one JSON object and nothing else:
{"clues": "one short sentence naming the details you used", "ranking": ["C000", "C000", "C000", "C000", "C000"]}

"ranking" holds exactly 5 different labels from the candidate list, the most likely first.

## candidates

Candidates:
{candidates}

## document

Document:
<<<
{document}
>>>

Who is the main person of this document? Answer with JSON only.

## no_document

The document itself is not available. Judging from the candidate list alone, who is most likely to be the main person of such a document? Answer with JSON only.
