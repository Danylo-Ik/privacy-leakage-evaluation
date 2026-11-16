"""Seed documents in inline-tag form. E1 is the target. All people are fictional."""

SEED_DOCS = [
    {
        "doc_id": "D001", "person_id": "P0001", "genre": "news", "doc_year": 2024,
        "tagged": (
            "У селі [[Вербівка|LOC|QI|E2|nom|-|settlement]] на [[Полтавщині|LOC|QI|E3|loc|-|oblast]] "
            "привітали [[Оксану|PERSON|DI|E1|acc|first]] [[Вигаданчук|PERSON|DI|E1|acc|surname]] — "
            "єдину [[вчительку хімії|DEM|QI|E4|acc|-|occupation]] місцевої школи, яка "
            "[[у 2019 році|DATETIME|QI|E5|-|-|event]] перемогла в обласному конкурсі "
            "[[«Вчитель року»|MISC|QI|E6|-|-|event]]. [[34-річна|DEM|QI|E7|nom|-|birth_year]] "
            "педагогиня [[виховує трьох дітей|DEM|QI|E8|-|-|children]] разом із "
            "[[чоловіком|DEM|QI|E12|ins|-|family_status]] [[Ігорем|PERSON|DI|E9|ins|first]]. "
            "«Хімія — це не формули, а дива щодня», — каже [[Оксана|PERSON|DI|E1|nom|first]] "
            "[[Миколаївна|PERSON|DI|E1|nom|patronymic]]. Колеги з "
            "[[Лубенського району|LOC|QI|E10|gen|-|-|E1]] розповідають, що пані "
            "[[Вигаданчук|PERSON|DI|E1|nom|surname]] сама облаштувала шкільну лабораторію. "
            "Директорка школи [[Галина|PERSON|DI|E11|nom|first]] "
            "[[Сидоренко|PERSON|DI|E11|nom|surname]] називає [[Оксану|PERSON|DI|E1|acc|first]] "
            "«серцем школи»."
        ),
    },
    {
        "doc_id": "D002", "person_id": "P0002", "genre": "court", "doc_year": 2023,
        "tagged": (
            "Справа [[№ 640/9071/22|CODE|DI|E2]]\n\nРІШЕННЯ\nІМЕНЕМ УКРАЇНИ\n\n"
            "[[12 травня 2023 року|DATETIME|QI|E3]] "
            "[[Київський районний суд м. Харкова|ORG|QI|E4|nom|-|settlement]] у складі головуючого "
            "судді [[Петренко|PERSON|DI|E5|gen|surname]] [[Н. В.|PERSON|DI|E5|-|initials]], "
            "розглянувши у відкритому судовому засіданні цивільну справу за позовом "
            "[[Ковальчинського|PERSON|DI|E1|gen|surname]] [[Тараса|PERSON|DI|E1|gen|first]] "
            "[[Петровича|PERSON|DI|E1|gen|patronymic]] (РНОКПП [[3012345678|CODE|DI|E6|-|-|-|E1]]) до "
            "[[ТОВ «Вигадана Логістика»|ORG|QI|E7|gen|-|-|E1]] "
            "[[про стягнення заборгованості із заробітної плати|MISC|QI|E8|-|-|event]],\n\n"
            "ВСТАНОВИВ:\n\n"
            "Позивач, [[1978 року народження|DATETIME|QI|E9|-|-|birth_year]], з "
            "[[березня 2019 року|DATETIME|QI|E10|-|-|-|E1]] працював "
            "[[водієм вантажного автомобіля|DEM|QI|E11|ins|-|occupation]] у відповідача. "
            "[[Ковальчинський|PERSON|DI|E1|nom|surname]] [[Т. П.|PERSON|DI|E1|-|initials]] зазначив, "
            "що [[після розірвання шлюбу|DEM|QI|E12|-|-|family_status]] сам утримує "
            "[[неповнолітнього сина|DEM|QI|E13|acc|-|children]], а відповідач з "
            "[[вересня 2022 року|DATETIME|QI|E14|-|-|event]] не виплачує йому заробітну плату. "
            "Представниця відповідача [[Олена|PERSON|DI|E15|nom|first]] "
            "[[Сидорчук|PERSON|DI|E15|nom|surname]] позов не визнала. Суд надав слово "
            "[[Ковальчинському|PERSON|DI|E1|dat|surname]] [[Тарасові|PERSON|DI|E1|dat|first]], "
            "який підтримав позовні вимоги. Позивач зареєстрований за адресою: "
            "[[м. Харків, вул. Вигадана, буд. 7, кв. 12|LOC|DI|E16|-|-|settlement]].\n\n"
            "УХВАЛИВ:\n\n"
            "Позов задовольнити. Стягнути з [[ТОВ «Вигадана Логістика»|ORG|QI|E7|gen|-|-|E1]] на користь "
            "[[Ковальчинського|PERSON|DI|E1|gen|surname]] [[Тараса|PERSON|DI|E1|gen|first]] "
            "[[Петровича|PERSON|DI|E1|gen|patronymic]] заборгованість у розмірі "
            "[[48 600 грн|QUANTITY|QI|E17|-|-|-|E1]]."
        ),
    },
    {
        "doc_id": "D003", "person_id": "P0003", "genre": "court", "doc_year": 2023,
        "tagged": (
            "Справа [[№ 456/2210/23|CODE|DI|E2]]\n\nРІШЕННЯ\nІМЕНЕМ УКРАЇНИ\n\n"
            "[[3 жовтня 2023 року|DATETIME|QI|E3]] "
            "[[Стрийський міськрайонний суд Львівської області|ORG|QI|E4|nom|-|settlement]] "
            "розглянув цивільну справу за позовом [[Задорожненко|PERSON|DI|E1|gen|surname]] "
            "[[Ірини|PERSON|DI|E1|gen|first]] [[Олегівни|PERSON|DI|E1|gen|patronymic]] до "
            "[[Вигаданого|PERSON|DI|E5|gen|surname]] [[Остапа|PERSON|DI|E5|gen|first]] "
            "[[Романовича|PERSON|DI|E5|gen|patronymic]] "
            "[[про стягнення боргу за договором позики|MISC|QI|E6|-|-|event]].\n\n"
            "Позивачка, [[1985 р. н.|DATETIME|QI|E7|-|-|birth_year]], "
            "[[медична сестра|DEM|QI|E8|nom|-|occupation]] "
            "[[Стрийської центральної районної лікарні|ORG|QI|E9|gen|-|-|E1]], пояснила, що "
            "[[15 січня 2023 року|DATETIME|QI|E10|-|-|event]] передала відповідачеві "
            "[[30 000 грн|QUANTITY|QI|E11|-|-|-|E1]] на строк до [[1 червня 2023 року|DATETIME|QI|E12]], "
            "проте кошти не повернуто. [[Ірина|PERSON|DI|E1|nom|first]] "
            "[[Олегівна|PERSON|DI|E1|nom|patronymic]] також повідомила, що "
            "[[не перебуває у шлюбі|DEM|QI|E13|-|-|family_status]] і сама доглядає "
            "[[матір похилого віку|DEM|QI|E14|acc|-|-|E1]]. Відповідач "
            "[[Вигаданий|PERSON|DI|E5|nom|surname]] [[О. Р.|PERSON|DI|E5|-|initials]] у судове "
            "засідання не з'явився. Заслухавши пояснення [[Задорожненко|PERSON|DI|E1|gen|surname]] "
            "[[І. О.|PERSON|DI|E1|-|initials]], суд дійшов висновку, що позов підлягає задоволенню."
        ),
    },
    {
        "doc_id": "D004", "person_id": "P0004", "genre": "news", "doc_year": 2024,
        "tagged": (
            "Фермер із [[Сосонки|LOC|QI|E2|gen|-|settlement]] [[Андрій|PERSON|DI|E1|nom|first]] "
            "[[Ліщинчук|PERSON|DI|E1|nom|surname]] вирощує [[органічну гречку|MISC|QI|E3|acc|-|-|E1]] на "
            "[[120 гектарах|QUANTITY|QI|E4|loc|-|-|E1]] у [[Тульчинському районі|LOC|QI|E5|loc|-|-|E1]] на "
            "[[Вінниччині|LOC|QI|E6|loc|-|oblast]]. [[У 2021 році|DATETIME|QI|E7|-|-|event]] він "
            "отримав [[грант на розвиток фермерського господарства|MISC|QI|E8|acc|-|event]] і купив "
            "новий комбайн. «Без підтримки [[дружини|DEM|QI|E9|gen|-|family_status]] "
            "[[Наталії|PERSON|DI|E10|gen|first]] я б не впорався», — зізнається "
            "[[55-річний|DEM|QI|E11|nom|-|birth_year]] [[Андрій|PERSON|DI|E1|nom|first]] "
            "[[Васильович|PERSON|DI|E1|nom|patronymic]]. Односельці досі називають його "
            "[[Андрійком|PERSON|DI|E1|ins|diminutive]], хоча господарство "
            "[[ФГ «Ліщинчук і син»|ORG|DI|E12|nom|-|-|E1]] уже стало одним із найбільших у громаді. "
            "Разом із [[сином|DEM|QI|E13|ins|-|children]] [[Ліщинчук|PERSON|DI|E1|nom|surname]] "
            "планує відкрити власну крупорушку."
        ),
    },
    {
        "doc_id": "D005", "person_id": "P0005", "genre": "forum", "doc_year": 2024,
        "tagged": (
            "Всім привіт! Мене звати [[Сашко|PERSON|DI|E1|nom|diminutive]], мені "
            "[[29 років|DEM|QI|E2|-|-|birth_year]], я [[неодружений|DEM|QI|E3|nom|-|family_status]] "
            "і працював [[програмістом|DEM|QI|E4|ins|-|occupation]] в "
            "[[Одесі|LOC|QI|E5|loc|-|settlement]]. [[У березні 2024 року|DATETIME|QI|E6|-|-|event]] "
            "мене звільнили з компанії [[«Вигаданий Софт»|ORG|QI|E7|-|-|-|E1]] без жодної компенсації. "
            "Мій керівник [[Віктор|PERSON|DI|E8|nom|first]] [[Семенович|PERSON|DI|E8|nom|patronymic]] "
            "сказав мені прямо: «[[Олександре|PERSON|DI|E1|voc|first]], ти сам винен». Кадровичка "
            "навіть надіслала лист [[Щербанюку|PERSON|DI|E1|dat|surname]] "
            "[[О. І.|PERSON|DI|E1|-|initials]], а в старій трудовій книжці я досі записаний "
            "по-російськи: [[Щербанюк|PERSON|DI|E1|nom|surname]] "
            "[[Александр|PERSON|DI|E1|nom|first]] [[Игоревич|PERSON|DI|E1|nom|patronymic]]. Хто "
            "проходив через таке, підкажіть, куди звертатися? Пишіть на "
            "[[oleksandr.shcherbaniuk95@example.com|CODE|DI|E9|-|-|-|E1]] або телефонуйте "
            "[[+380 67 000 12 34|CODE|DI|E10|-|-|-|E1]]."
        ),
    },
]
