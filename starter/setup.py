"""Первичная настройка: собрать реквизиты владельца инструмента.

Зачем отдельный шаг, а не «скопируй yaml и впиши руками».

Реквизиты владельца — единственные данные, которые печатаются в КАЖДОМ
документе и зашиваются в платёжный QR каждого счёта. Опечатка здесь тиражируется
молча и во все стороны сразу: в договоры, в счета, в код оплаты. Поэтому вводятся
они один раз и СРАЗУ проверяются контрольными суммами — это лучший момент поймать
ошибку, второго такого не будет.

Три режима:

    python setup.py              # диалог: спрашивает поле за полем
    python setup.py --json a.json  # из файла (так это делает AI-агент)
    python setup.py --check      # проверить уже заполненный supplier.yaml

Готовый файл — config/supplier.yaml — в .gitignore: он содержит расчётный счёт.
"""
import json
import sys
from pathlib import Path

import yaml

from requisites import account_ok, inn_ok, ogrn_ok

BASE = Path(__file__).parent
TARGET = BASE / "config" / "supplier.yaml"
EXAMPLE = BASE / "config" / "supplier.example.yaml"

# ключ · вопрос · обязательное · подсказка
FIELDS = [
    ("name_full", "Полное наименование (как в уставе / ЕГРИП)", True,
     'ООО «Ромашка» либо Индивидуальный предприниматель Иванов Иван Иванович'),
    ("name_short", "Краткое наименование", True, 'ООО «Ромашка» / ИП Иванов И.И.'),
    ("inn", "ИНН", True, "10 цифр у юрлица, 12 у ИП"),
    ("kpp", "КПП", False, "у ИП нет — оставь пустым"),
    ("ogrn", "ОГРН / ОГРНИП", False, "13 или 15 цифр"),
    ("address", "Юридический адрес", True, "с индексом"),
    ("bank", "Банк", True, 'АО «Банк»'),
    ("rs", "Расчётный счёт", True, "20 цифр, начинается с 40"),
    ("ks", "Корреспондентский счёт", True, "20 цифр, начинается с 301"),
    ("bik", "БИК", True, "9 цифр"),
    ("email", "E-mail", False, "печатается в реквизитах"),
    ("phone", "Телефон", False, ""),
    ("signer_clause", "«В лице ...» — родительный падеж", True,
     "в лице генерального директора Иванова Ивана Ивановича"),
    ("signer_basis", "Действует на основании (род. падеж)", True,
     "Устава / Листа записи ЕГРИП"),
    ("signer_role_nom", "Должность для строки подписи (им. падеж)", True,
     "Генеральный директор"),
    ("signer_short", "Подпись (Фамилия И.О.)", True, "Иванов И.И."),
    ("vat_note", "Отметка об НДС", False,
     "«НДС не облагается» либо «В том числе НДС 20%»"),
]


def validate(data):
    """Контрольные суммы своих же реквизитов. Возвращает список замечаний.

    Не блокируем: бывают счета в казначействе и прочие законные исключения.
    Но говорим громко — потому что дальше это уедет в каждый документ.
    """
    problems = []
    if inn_ok(data.get("inn")) is False:
        problems.append("ИНН: контрольная сумма не сходится.")
    if data.get("ogrn") and ogrn_ok(data.get("ogrn")) is False:
        problems.append("ОГРН: контрольная сумма не сходится.")
    bik = data.get("bik")
    if account_ok(data.get("rs"), bik, "rs") is False:
        problems.append("Расчётный счёт не сходится с БИК.")
    if account_ok(data.get("ks"), bik, "ks") is False:
        problems.append("Корр. счёт не сходится с БИК.")
    for key, question, required, _ in FIELDS:
        if required and not str(data.get(key) or "").strip():
            problems.append("Не заполнено обязательное поле: {}.".format(question))
    return problems


def ask():
    print("Настройка реквизитов. Они попадут в каждый документ и в QR каждого счёта.")
    print("Пустой ответ на необязательный вопрос — пропустить.\n")
    data = {}
    for key, question, required, hint in FIELDS:
        prompt = "{}{}".format(question, " ({})".format(hint) if hint else "")
        while True:
            value = input("{}\n> ".format(prompt)).strip()
            if value or not required:
                data[key] = value
                break
            print("Это поле обязательно.\n")
        print()
    return data


def write(data, force=False):
    if TARGET.exists() and not force:
        print("Файл {} уже есть.".format(TARGET.relative_to(BASE)))
        print("Перезаписать — запусти с --force (старый посмотри глазами: там счёт).")
        return 1
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    # allow_unicode — иначе кириллица уедет в \u-последовательности и файл
    # перестанет читаться человеком, а его смысл именно в том, чтобы читаться.
    TARGET.write_text(
        yaml.safe_dump({"supplier": data}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print("Записано: {}".format(TARGET.relative_to(BASE)))
    return 0


def report(problems, where):
    if problems:
        print("\nЗамечания по {}:".format(where))
        for p in problems:
            print("  ⚠ {}".format(p))
        print("\nЭто предупреждения, не запрет. Но проверь: реквизиты печатаются")
        print("в каждом документе, а расчётный счёт — ещё и в платёжном QR.")
    else:
        print("\nПроверка пройдена: контрольные суммы сходятся, обязательные поля на месте.")


def main():
    args = sys.argv[1:]

    if "--check" in args:
        if not TARGET.exists():
            print("Нет {}. Запусти `python setup.py`.".format(TARGET.relative_to(BASE)))
            return 1
        data = yaml.safe_load(TARGET.read_text(encoding="utf-8"))["supplier"]
        report(validate(data), TARGET.name)
        return 0

    if "--json" in args:
        # Режим для AI-агента: он расспросил владельца в чате и сложил ответы
        # в JSON. Ключи — те же, что в FIELDS.
        path = Path(args[args.index("--json") + 1])
        data = json.loads(path.read_text(encoding="utf-8"))
        data = data.get("supplier", data)
    else:
        data = ask()

    problems = validate(data)
    report(problems, "введённым реквизитам")
    code = write(data, force="--force" in args)
    if code == 0:
        print("\nДальше: положи свой договор в references/ и прочитай его —")
        print("  python read_etalon.py references/<файл>.docx")
    return code


if __name__ == "__main__":
    sys.exit(main())
