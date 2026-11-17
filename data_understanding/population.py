"""Synthetic population (2,000 people) and the list of document targets.

Usage: python data_understanding/population.py [OUT_DIR]   (default data/full)
Writes population.csv and targets.csv.
"""
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from seed_tools import POP_COLUMNS, TARGETS  # noqa: E402

N_PEOPLE = 2000
SEED = 2024
COLUMNS = POP_COLUMNS + ["surname_type"]

# name: (patronymic m, patronymic f, diminutives)
MALE = {
    "Андрій": ("Андрійович", "Андріївна", ["Андрійко"]),
    "Олександр": ("Олександрович", "Олександрівна", ["Сашко", "Олесь"]),
    "Тарас": ("Тарасович", "Тарасівна", ["Тарасик"]),
    "Іван": ("Іванович", "Іванівна", ["Івась", "Іванко"]),
    "Петро": ("Петрович", "Петрівна", ["Петрик"]),
    "Микола": ("Миколайович", "Миколаївна", ["Миколка"]),
    "Василь": ("Васильович", "Василівна", ["Василько"]),
    "Олег": ("Олегович", "Олегівна", ["Олежко"]),
    "Роман": ("Романович", "Романівна", ["Ромко"]),
    "Ігор": ("Ігорович", "Ігорівна", ["Ігорко"]),
    "Дмитро": ("Дмитрович", "Дмитрівна", ["Дмитрик", "Митько"]),
    "Сергій": ("Сергійович", "Сергіївна", ["Сергійко"]),
    "Юрій": ("Юрійович", "Юріївна", ["Юрко"]),
    "Михайло": ("Михайлович", "Михайлівна", ["Михась", "Михайлик"]),
    "Богдан": ("Богданович", "Богданівна", ["Богданчик"]),
    "Володимир": ("Володимирович", "Володимирівна", ["Володя"]),
    "Віктор": ("Вікторович", "Вікторівна", ["Вітя"]),
    "Степан": ("Степанович", "Степанівна", ["Степанко"]),
    "Григорій": ("Григорович", "Григорівна", ["Гриць", "Грицько"]),
    "Павло": ("Павлович", "Павлівна", ["Павлик"]),
    "Віталій": ("Віталійович", "Віталіївна", ["Віталік"]),
    "Максим": ("Максимович", "Максимівна", ["Максимко"]),
    "Євген": ("Євгенович", "Євгенівна", ["Женя"]),
    "Анатолій": ("Анатолійович", "Анатоліївна", ["Толік"]),
    "Ярослав": ("Ярославович", "Ярославівна", ["Ярко", "Славко"]),
    "Остап": ("Остапович", "Остапівна", ["Остапко"]),
    "Назар": ("Назарович", "Назарівна", ["Назарко"]),
    "Денис": ("Денисович", "Денисівна", ["Дениско"]),
    "Артем": ("Артемович", "Артемівна", ["Артемко"]),
    "Вадим": ("Вадимович", "Вадимівна", ["Вадик"]),
}
FEMALE = {
    "Оксана": ["Оксанка"], "Ірина": ["Іринка"], "Наталія": ["Наталка"], "Олена": ["Оленка"],
    "Галина": ["Галя", "Галинка"], "Марія": ["Марійка"], "Тетяна": ["Таня", "Тетянка"],
    "Юлія": ["Юля"], "Світлана": ["Світланка"], "Ольга": ["Оля"], "Людмила": ["Люда"],
    "Валентина": ["Валя"], "Надія": ["Надійка"], "Любов": ["Люба"],
    "Катерина": ["Катруся", "Катя"], "Ганна": ["Ганнуся", "Ганя"], "Христина": ["Христя"],
    "Софія": ["Софійка"], "Віра": ["Віруся"], "Лариса": ["Ларисонька"], "Інна": ["Інночка"],
    "Алла": ["Аллочка"], "Вікторія": ["Віка"], "Мар’яна": ["Мар’янка"], "Уляна": ["Уля"],
    "Зоряна": ["Зоряночка"], "Дарина": ["Даринка"], "Ніна": ["Ніночка"],
    "Тамара": ["Тамарочка"], "Лілія": ["Ліля"],
}
DIMINUTIVES = {**{n: d for n, (_, _, d) in MALE.items()}, **FEMALE}

# Common real surnames, roughly most frequent first.
REAL_SURNAMES = """
Шевченко Коваленко Бондаренко Ткаченко Кравченко Ковальчук Бойко Олійник Шевчук Поліщук
Мельник Савченко Петренко Марченко Руденко Бойчук Литвиненко Мельничук Савчук Кравчук
Павленко Гончаренко Кузьменко Левченко Лисенко Харченко Демченко Іваненко Яковенко Онищенко
Захарченко Юрченко Карпенко Пономаренко Тищенко Зінченко Власенко Нестеренко Дорошенко
Федоренко Романенко Гриценко Кириленко Остапенко Прокопенко Сидоренко Мирошниченко
Кучеренко Клименко Максименко Науменко Опанасенко Лук’яненко Хоменко Гордієнко Сергієнко
Андрієнко Тарасенко Дмитренко Степаненко Василенко Гаврилюк Данилюк Мартинюк Романюк
Ковалюк Стасюк Тимчук Онищук Олексюк Панчук Остапчук Вакарчук Марчук Климчук Пилипчук
Петрук Іванчук Семенюк Федорчук Степанюк Юрчук Гуменюк Бондарчук Ничипорук Яремчук
Лук’янчук Дмитрук Процюк Сидорук Василюк Демчук Зінчук Карпюк Ковальський Яворський
Вишневський Левицький Грабовський Островський Білецький Вербицький Козловський
Барановський Савицький Дубинський Кравецький Зборовський Малиновський Зелінський Луцький
Глинський Ярошинський Підгірський Маковецький Ружицький Білий Чорний Сивий Рудий Довгий
Кривий Гладкий Зелений Заболотний Задорожний Підгорний Нагірний Лозовий Дубовий Береговий
Бережний Кошовий Гайовий Петришин Іванишин Стефанишин Михайлишин Яцишин Гнатишин Федишин
Василишин Романишин Дмитришин Павлишин Тимишин Костишин
""".split()
# Бойко, Олійник and Мельник fit no suffix type; they stay as "other".

# Invented stems; each one gives a surname of every suffix type.
STEMS = """
Терн Глод Ожин Калин Ясен Барвін Горобин Верес Ліщин Вербен Шипшин Полин Осокор Ковил
Чагар Комиш Бузин Ялин Лелеч Синиц Осот Ряст Чебрен Вишен Дерен Межир Лозин Очерет
Жолуд Сміл Кужел Бескид Запіл Борщан Ковтун Пасік Ратан Сулим Тетер Удол Хмелин Чорнот
""".split()


def surname_type(surname):
    s = surname
    if s.endswith(("енко", "єнко")):
        return "enko"
    if s.endswith(("ський", "цький", "ська", "цька")):
        return "skyi"
    if s.endswith("ишин"):
        return "yshyn"
    if s.endswith(("чук", "юк", "ук")):
        return "chuk"
    if s.endswith(("ий", "а")):
        return "adj"
    return "other"


def female_surname(male):
    return male[:-2] + "а" if male.endswith("ий") else male


def constructed_surnames():
    out = []
    for stem in STEMS:
        chuk = "ук" if stem[-1] in "чщ" else "юк"
        out += [stem + chuk, stem + "енко", stem + "івський", stem + "овий", stem + "ишин"]
    real = set(REAL_SURNAMES)
    return [s for s in out if s not in real]


# oblast: (weight, city, towns, villages)
OBLASTS = {
    "Харківська": (1.5, "Харків", ["Чугуїв", "Ізюм", "Лозова"],
                   ["Безлюдівка", "Коротич", "Липці", "Слатине", "Руська Лозова", "Циркуни",
                    "Черкаська Лозова", "Пересічна", "Малинівка", "Бабаї", "Тернова",
                    "Вільхівка", "Гракове", "Шестакове"]),
    "Одеська": (1.4, "Одеса", ["Балта", "Ізмаїл", "Подільськ"],
                ["Великодолинське", "Фонтанка", "Крижанівка", "Нерубайське", "Усатове", "Маяки",
                 "Петрівка", "Дачне", "Красносілка", "Вигода", "Нова Долина", "Мізікевича",
                 "Санжійка", "Шабо"]),
    "Львівська": (1.4, "Львів", ["Стрий", "Дрогобич", "Самбір"],
                  ["Підбуж", "Сокільники", "Зимна Вода", "Оброшине", "Солонка", "Давидів",
                   "Лапаївка", "Наварія", "Муроване", "Підберізці", "Дуліби", "Ямельниця",
                   "Тейсарів", "Кавське"]),
    "Полтавська": (1.0, "Полтава", ["Лубни", "Миргород", "Гадяч"],
                   ["Вербівка", "Мгар", "Шишаки", "Білики", "Великі Сорочинці", "Ковалівка",
                    "Гоголеве", "Кротенки", "Михайлики", "Петрівка", "Абазівка", "Терешки",
                    "Мачухи", "Засулля"]),
    "Вінницька": (1.0, "Вінниця", ["Тульчин", "Жмеринка", "Гайсин"],
                  ["Сосонка", "Агрономічне", "Стадниця", "Писарівка", "Якушинці",
                   "Лука-Мелешківська", "Гавришівка", "Зарванці", "Тютюнники", "Бохоники",
                   "Щітки", "Медвідка", "Лаврівка", "Корделівка"]),
    "Житомирська": (0.8, "Житомир", ["Бердичів", "Коростень", "Звягель"],
                    ["Глибочиця", "Тетерівка", "Станишівка", "Вереси", "Березина", "Корчак",
                     "Псище", "Головенка", "Кодня", "Сінгури", "Озерянка", "Буки", "Пряжів",
                     "Левків"]),
    "Чернігівська": (0.7, "Чернігів", ["Ніжин", "Прилуки", "Мена"],
                     ["Киїнка", "Количівка", "Новоселівка", "Пакуль", "Халявин", "Терехівка",
                      "Анисів", "Жавинка", "Кувечичі", "Рашківка", "Шестовиця", "Вознесенське",
                      "Ковпита", "Сновянка"]),
}
SIZE = {"city": 30, "town": 5, "village": 1.5}


def settlements():
    rows = []
    for oblast, (weight, city, towns, villages) in OBLASTS.items():
        places = [(city, "city")] + [(t, "town") for t in towns] + [(v, "village") for v in villages]
        total = sum(SIZE[t] for _, t in places)
        rows += [(oblast, name, t, weight * SIZE[t] / total) for name, t in places]
    return rows


OCCUPATIONS = ["вчитель хімії", "вчитель початкових класів", "водій вантажівки",
               "медична сестра", "фермер", "агроном", "програміст", "бухгалтер", "продавець",
               "інженер", "лікар", "юрист", "електрик", "кухар", "перукар", "економіст",
               "будівельник", "слюсар", "тракторист", "охоронець", "листоноша", "психолог"]
FEMALE_ONLY = {"медична сестра"}

EVENT_GENRE = {"court_wage_claim": "court", "court_loan_claim": "court",
               "award_teacher_of_year": "news", "grant_farm": "news", "dismissal": "forum"}
TARGETS_PER_EVENT = {"court_wage_claim": 25, "court_loan_claim": 25,
                     "award_teacher_of_year": 25, "grant_farm": 25, "dismissal": 50}


def event_fits(event, occupation):
    if event == "award_teacher_of_year":
        return occupation.startswith("вчитель")
    if event == "grant_farm":
        return occupation == "фермер"
    if event == "dismissal":
        return occupation != "фермер"
    return True


class Generator:
    def __init__(self, seed=SEED):
        self.rng = random.Random(seed)
        self.real = REAL_SURNAMES
        self.real_weights = [1 / (i + 10) for i in range(len(self.real))]
        self.made_up = constructed_surnames()
        self.places = settlements()
        self.used_names = {(t["first_name"], t["patronymic"], t["surname"]) for t in TARGETS}

    def surname(self, gender):
        if self.rng.random() < 0.3:
            male = self.rng.choice(self.made_up)
        else:
            male = self.rng.choices(self.real, self.real_weights)[0]
        return male if gender == "M" else female_surname(male)

    def name(self, gender):
        while True:
            first = self.rng.choice(list(MALE if gender == "M" else FEMALE))
            father = MALE[self.rng.choice(list(MALE))]
            patronymic = father[0] if gender == "M" else father[1]
            key = (first, patronymic, self.surname(gender))
            if key not in self.used_names:
                self.used_names.add(key)
                return key

    def person(self, gender=None, birth_year=None, oblast=None, occupation=None):
        rng = self.rng
        gender = gender or ("F" if rng.random() < 0.52 else "M")
        first, patronymic, surname = self.name(gender)
        places = [p for p in self.places if oblast is None or p[0] == oblast]
        oblast, settlement, stype, _ = rng.choices(places, [p[3] for p in places])[0]
        if occupation is None:
            options = [o for o in OCCUPATIONS if gender == "F" or o not in FEMALE_ONLY]
            occupation = rng.choice(options)
        family = rng.choices(["married", "single", "divorced", "widowed"], [5, 3, 2, 1])[0]
        children = 0 if family == "single" and rng.random() < 0.8 else rng.randint(0, 3)
        event = ""
        if rng.random() < 0.1:
            fitting = [e for e in EVENT_GENRE if event_fits(e, occupation)]
            event = f"{rng.choice(fitting)}_{rng.randint(2018, 2024)}"
        return dict(person_id="", first_name=first, patronymic=patronymic, surname=surname,
                    gender=gender, birth_year=birth_year or rng.randint(1960, 2002),
                    oblast=oblast, settlement=settlement, settlement_type=stype,
                    occupation=occupation, family_status=family, children=children,
                    event=event, surname_type=surname_type(surname))


def make_population(n=N_PEOPLE, seed=SEED):
    """Return (people, targets). Seed people P0001-P0008 come first, unchanged."""
    gen = Generator(seed)
    rng = gen.rng
    n_targets = sum(TARGETS_PER_EVENT.values())
    n_lookalikes = [rng.randint(1, 3) for _ in range(n_targets)]
    base = [gen.person() for _ in range(n - len(TARGETS) - sum(n_lookalikes))]

    targets, free = [], list(range(len(base)))
    for event, count in TARGETS_PER_EVENT.items():
        fitting = [i for i in free if event_fits(event, base[i]["occupation"])]
        for i in rng.sample(fitting, count):
            free.remove(i)
            base[i]["event"] = f"{event}_{rng.randint(2018, 2024)}"
            targets.append(base[i])

    lookalikes = {}
    for t, k in zip(targets, n_lookalikes):
        lookalikes[id(t)] = [gen.person(t["gender"], t["birth_year"], t["oblast"], t["occupation"])
                             for _ in range(k)]
    others = base + [p for group in lookalikes.values() for p in group]
    rng.shuffle(others)

    people = [dict(t, surname_type=surname_type(t["surname"])) for t in TARGETS] + others
    for i, p in enumerate(people):
        p["person_id"] = f"P{i + 1:04d}"

    target_rows = [{"person_id": t["person_id"], "genre": EVENT_GENRE[t["event"].rsplit("_", 1)[0]],
                    "event": t["event"],
                    "lookalikes": " ".join(p["person_id"] for p in lookalikes[id(t)])}
                   for t in targets]
    target_rows.sort(key=lambda r: r["person_id"])
    return people, target_rows


def write(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    people, targets = make_population()
    with open(out_dir / "population.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(people)
    with open(out_dir / "targets.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["person_id", "genre", "event", "lookalikes"])
        w.writeheader()
        w.writerows(targets)
    return people, targets


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/full")
    people, targets = write(out)
    surnames = {p["surname"] for p in people}
    print(f"{len(people)} people, {len(surnames)} surnames, {len(targets)} targets -> {out}")
