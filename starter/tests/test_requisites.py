"""Контрольные суммы и распознавание реквизитов.

Эти тесты дешёвые и очень окупаемые: алгоритмы контрольных сумм легко списать
с ошибкой в одном весе, и тогда валидатор будет молча пропускать опечатки —
худший вид поломки, потому что он выглядит как работающий.

Запуск:  python -m pytest tests -q     (или: python tests/test_requisites.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from requisites import (account_ok, check_requisites, find_contractor, inn_ok,
                        ogrn_ok, parse_requisites)

BIK = "040000000"
# Второй БИК — с ненулевыми разрядами. Он нужен, чтобы проверка «расчётный
# против корреспондентского» вообще имела смысл: у БИК из одних нулей оба
# префикса ключевания совпадают ('000'), и различие типов не проявляется.
BIK2 = "041234567"


def test_inn():
    assert inn_ok("0000000000") is True          # 10 цифр, сумма сходится
    assert inn_ok("0000000001") is False         # подменили контрольную цифру
    assert inn_ok("000000000000") is True        # 12 цифр (ИП/физлицо)
    assert inn_ok("123") is None                 # судить нельзя — не ошибка


def test_ogrn():
    assert ogrn_ok("0000000000000") is True
    assert ogrn_ok("0000000000001") is False
    assert ogrn_ok("000000000000000") is True    # ОГРНИП, 15 цифр
    assert ogrn_ok("") is None


def test_accounts():
    assert account_ok("40700000000000000001", BIK, "rs") is True
    assert account_ok("40700000000000000002", BIK, "rs") is False
    assert account_ok("30100000000000000006", BIK, "ks") is True
    assert account_ok("123", BIK, "rs") is None

    # Тип счёта — не формальность: ключевание расчётного и корреспондентского
    # идёт по РАЗНЫМ разрядам БИК. Верный расчётный счёт, проверенный как
    # корреспондентский, не сходится — и наоборот.
    assert account_ok("40700000000000000009", BIK2, "rs") is True
    assert account_ok("30100000000000000001", BIK2, "ks") is True
    assert account_ok("40700000000000000009", BIK2, "ks") is False
    assert account_ok("30100000000000000001", BIK2, "rs") is False


def test_parse_card():
    text = """
    Полное наименование: Общество с ограниченной ответственностью «Ромашка»
    ИНН 0000000000  КПП 000000000
    ОГРН: 0000000000000
    Юридический адрес: 000000, г. Город, ул. Улица, д. 1
    Банк получателя: АО «Банк»
    БИК: 040000000
    Расчётный счёт: 40700000000000000001
    Корреспондентский счёт: 30100000000000000006
    """
    data = parse_requisites(text)
    assert data["customer_inn_kpp"] == "0000000000/000000000"
    assert data["customer_ogrn"] == "0000000000000"
    assert data["customer_rs"] == "40700000000000000001"
    # Главная ловушка карточек: два 20-значных счёта подряд. Различаются
    # по префиксу (40… против 301…), иначе один затирает другой.
    assert data["customer_ks"] == "30100000000000000006"
    assert data["customer_bik"] == "040000000"
    assert check_requisites(data) == []


def test_name_keeps_closing_quote():
    """Наивная чистка кавычек откусывает закрывающую «»: в договор уезжает
    'ООО «Ромашка' — брак, который замечают уже на подписании."""
    data = parse_requisites('Наименование: ООО «Ромашка»')
    assert data["customer_name"] == "ООО «Ромашка»"
    assert parse_requisites('Наименование: «ООО Ромашка»')["customer_name"] == "ООО Ромашка"
    assert parse_requisites('Наименование: ООО "Ромашка"')["customer_name"] == 'ООО "Ромашка"'


def test_parse_catches_typo():
    data = parse_requisites("ИНН 0000000001\nБИК 040000000\nРасчётный счёт: 40700000000000000002")
    warnings = check_requisites(data)
    assert any("ИНН" in w for w in warnings)
    assert any("асчётный счёт" in w for w in warnings)


def test_contractor_base():
    found = find_contractor("Ромашка")
    assert found.get("customer_name", "").startswith("ООО")
    assert find_contractor("") == {}
    assert find_contractor("несуществующая организация") == {}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok:", name)
    print("все проверки реквизитов пройдены")
