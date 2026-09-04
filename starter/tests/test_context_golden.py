"""Golden-тест контекста документа.

Приём простой и очень сильный: фиксируем ЭТАЛОННЫЙ результат build_context для
известного набора входных данных. Дальше любой рефактор доказывает свою
безопасность сам — если контекст изменился хоть в одном поле, тест краснеет.

Именно этот тест позволяет спокойно переписывать сборку документов: без него
единственный способ проверить, что ничего не поехало, — открывать десяток
.docx глазами и сравнивать по памяти.

Когда изменение НАМЕРЕННОЕ (поправили формулировку) — эталон обновляется руками
и правка видна в diff. Это фича: изменение текста документа обязано быть заметным.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from context import build_context, date_forms, money_full, split_prepay

SUPPLIER = {
    "name_full": "ООО «Пример»", "name_short": "ООО «Пример»",
    "inn": "0000000000", "kpp": "000000000", "ogrn": "0000000000000",
    "address": "000000, г. Город", "bank": "АО «Банк»",
    "rs": "40700000000000000001", "ks": "30100000000000000006", "bik": "040000000",
    "email": "mail@example.com", "phone": "+7 000 000-00-00",
    "signer_clause": "в лице директора", "signer_basis": "Устава",
    "signer_role_nom": "Директор", "signer_short": "Фамилия И.О.",
    "vat_note": "НДС не облагается",
}

FORM = {
    "doc_type": "services",
    "num": "20260904001",
    "doc_date": "2026-09-04",
    "date_from": "2026-09-10",
    "customer_name": "ООО «Ромашка»",
    "customer_inn_kpp": "0000000000/000000000",
    "customer_legal_addr": "000000, г. Город, ул. Улица, д. 1",
    "total": "100000",
    "prepay_percent": "30",
    "subject": "услуги по обучению",
    "services_text": "первый пункт\nвторой пункт\n",
}

GOLDEN = {
    "num": "20260904001",
    "doc_date_q": "«04» сентября 2026 г.",
    "doc_date_long": "04 сентября 2026 года",
    "subject": "услуги по обучению",
    "subject_cap": "Услуги по обучению",
    "services": ["- первый пункт;", "- второй пункт."],
    # NBSP (\u00a0), а не обычный пробел: разделитель тысяч обязан быть
    # неразрывным, иначе Word разрывает число между строками («100» в конце
    # строки, «000» в начале следующей). В юридическом документе это брак.
    "total_num": "100\u00a0000",
    "total_full": "100\u00a0000 (сто тысяч) рублей 00 копеек",
    "prepay_full": "30\u00a0000 (тридцать тысяч) рублей 00 копеек",
    "remainder_full": "70\u00a0000 (семьдесят тысяч) рублей 00 копеек",
    "term_service": "10 сентября 2026 года",
    "term_deadline": "24 сентября 2026 года",
}


def test_golden_context():
    ctx = build_context(FORM, SUPPLIER)
    for key, expected in GOLDEN.items():
        assert ctx[key] == expected, "поле {}: ожидалось {!r}, получено {!r}".format(
            key, expected, ctx[key]
        )


def test_prepay_sums_match_total():
    """Инвариант: аванс + остаток == сумма договора. Всегда, при любом проценте.
    Если считать каждую часть отдельным округлением, на некоторых суммах
    появляется расхождение в рубль — и его находит бухгалтерия клиента."""
    for total in (1, 7, 999, 100000, 333333):
        for pct in range(0, 101):
            prepay, remainder = split_prepay(total, pct)
            assert prepay + remainder == total


def test_bad_date_is_loud():
    """Некорректная дата обязана падать с внятной ошибкой, а не подставлять
    «декабря» из отрицательного индекса месяца."""
    for bad in ("2026-00-15", "2026-13-01", "2026-02-30", "", "вчера"):
        try:
            date_forms(bad)
        except ValueError:
            continue
        raise AssertionError("дата {!r} прошла без ошибки".format(bad))


def test_money_words():
    assert money_full(1) == "1 (один) рублей 00 копеек"
    assert money_full(1500) == "1\u00a0500 (одна тысяча пятьсот) рублей 00 копеек"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok:", name)
    print("golden-тест контекста пройден")
