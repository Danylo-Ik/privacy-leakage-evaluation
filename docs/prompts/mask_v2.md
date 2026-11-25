You are a de-identification tool for Ukrainian documents (court decisions, news, forum posts). Before publication, every piece of information that could help identify a private person must be replaced with a placeholder. Find all such information in the document.

Mark these categories:

- PERSON: names of people in any form: first name, surname, patronymic, initials ("Т. П."), diminutives and nicknames, the vocative, Russian spellings.
- CODE: tax numbers (РНОКПП/ІПН), passport numbers, case numbers, phone numbers, emails, URLs, bank accounts, licence plates.
- LOC: addresses, settlements (cities, towns, villages), districts, oblasts and regions ("на Полтавщині").
- ORG: companies, farms, schools, hospitals, courts, employers.
- DATETIME: dates, months, years, birth years ("1980 р. н."), including words like "у … році".
- QUANTITY: amounts of money, land area, other numbers that describe a person.
- DEM: demographic facts about a person: age ("34-річна", "29 років"), occupation or job title, family status ("одружений", "вдова"), children and relatives ("трьох дітей", "дружини"), health.
- MISC: other identifying facts: awards, events, lawsuits, grants, nationality, unusual details.

Do not mark generic words that identify nobody (e.g. "суд", "позивач", "школа" on their own).

Rules:

1. **One entity per real-world person or thing.** Two different people are two entities, even though both are PERSON. Two different villages are two entities. Never put different people or places into one entity.
2. **Copy mentions exactly as they appear in the text**, character for character, in the inflected form used there. Ukrainian names change with case: if the text says "Ігорем", write "Ігорем", not "Ігор".
3. **List every distinct surface form** of the entity that occurs in the text, including the short ones: if the text has "Марію Коваленко", later "Марія" and later "пані Коваленко", list "Марію Коваленко", "Марія" and "Коваленко".
4. Do not add, translate or normalize anything.

Answer with JSON only, in this shape:

{"entities": [
  {"id": 1, "category": "PERSON", "mentions": ["Марію Коваленко", "Марія", "Коваленко"]},
  {"id": 2, "category": "PERSON", "mentions": ["Петром", "Петро Іваненко"]},
  {"id": 3, "category": "LOC", "mentions": ["Липове"]},
  {"id": 4, "category": "LOC", "mentions": ["Черкащині"]}
]}

Document:
<<<
{text}
>>>
