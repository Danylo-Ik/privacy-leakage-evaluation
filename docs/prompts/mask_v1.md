You are a de-identification tool for Ukrainian documents (court decisions, news, forum posts). Before publication, every piece of information that could help identify a private person must be replaced with a placeholder. Find all such information in the document.

Mark these categories:

- PERSON: names of people in any form: first name, surname, patronymic, initials ("Т. П."), diminutives and nicknames, the vocative, Russian spellings. Ukrainian names inflect: "Коваленко", "Коваленка", "Коваленкові" are the same person, and every inflected form must be marked.
- CODE: tax numbers (РНОКПП/ІПН), passport numbers, case numbers, phone numbers, emails, URLs, bank accounts, licence plates.
- LOC: addresses, settlements (cities, towns, villages), districts, oblasts and regions ("на Полтавщині").
- ORG: companies, farms, schools, hospitals, courts, employers.
- DATETIME: dates, months, years, birth years ("1980 р. н.").
- QUANTITY: amounts of money, land area, other numbers that describe a person.
- DEM: demographic facts about a person: age ("34-річна", "29 років"), occupation or job title, family status ("одружений", "вдова"), children and relatives ("трьох дітей", "дружини"), health.
- MISC: other identifying facts: awards, events, lawsuits, grants, nationality, unusual details.

Do not mark generic words that identify nobody (e.g. "суд", "позивач", "школа" on their own).

Group mentions by the real-world thing they refer to: all forms of one person's name go in one entity; the same village mentioned twice is one entity.

Copy every mention **exactly** as it appears in the text, character for character, in its inflected form. List each distinct surface form once per entity; every occurrence of it will be masked. Do not add or translate anything.

Answer with JSON only, in this shape:

{"entities": [{"category": "PERSON", "mentions": ["Марію Коваленко", "Марія", "Коваленко"]}, {"category": "LOC", "mentions": ["Липове"]}]}

Document:
<<<
{text}
>>>
