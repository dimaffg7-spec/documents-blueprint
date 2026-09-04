"""Сборка КОНТЕКСТА документа — плоского словаря, который уезжает в шаблон.

Здесь нет ни HTTP, ни файлов, ни базы: чистые функции «данные формы → данные
документа». Именно поэтому их можно накрыть golden-тестом (tests/) и спокойно
рефакторить: тест докажет, что документ не поехал.

Главное правило слоя: в шаблон уезжают ГОТОВЫЕ СТРОКИ. Никакой логики внутри
.docx — ни условий, ни склонений, ни форматирования чисел. Шаблон только
подставляет. Всё, что «умное», живёт здесь, где это видно и тестируемо.
"""
import datetime as dt

from num2words import num2words

from catalog import get_doc_type

MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


# ---------------------------------------------------------------- числа и даты

def fmt_num(n):
    """400000 → '400 000'. Разделитель — неразрывный пробел, иначе Word рвёт
    число по строкам ('400' в конце строки, '000' в начале следующей)."""
    return "{:,}".format(int(n)).replace(",", " ")


def rub_words(n):
    """400000 → 'четыреста тысяч'. Слово «рублей» добавляет шаблон/вызывающий:
    падеж зависит от места в предложении, а num2words его не знает."""
    return num2words(int(n), lang="ru")


def money_full(n):
    """400000 → '400 000 (четыреста тысяч) рублей 00 копеек' — канон для сумм
    в договоре и счёте. Копейки прописью не пишем: в целых рублях их не бывает,
    а «00 копеек» цифрами — общепринятая форма."""
    return "{} ({}) рублей 00 копеек".format(fmt_num(n), rub_words(n))


def date_forms(iso):
    """'2026-06-09' → ('«09» июня 2026 г.', '09 июня 2026 года').

    Две формы, потому что в реальных документах встречаются обе, и «привести
    к одной» нельзя: тело договора — чужой эталон, его формулировки трогать
    не наше дело.

    Кривая дата = внятная ошибка, а не мусор в документе. Без явной проверки
    '2026-00-15' молча даёт MONTHS_GEN[-1] = «декабря» — и это уезжает клиенту.
    """
    try:
        y, m, d = (int(x) for x in str(iso).split("-"))
        dt.date(y, m, d)  # календарная валидация: месяц 1-12, день существует
    except (ValueError, TypeError):
        raise ValueError("Дата не заполнена или некорректна: {!r}".format(str(iso)))
    month = MONTHS_GEN[m - 1]
    return "«{:02d}» {} {} г.".format(d, month, y), "{:02d} {} {} года".format(d, month, y)


def date_compact(iso):
    """'2026-06-11' → '20260611' — префикс сквозного номера документа."""
    return (iso or "").replace("-", "")


def plus_days(iso, days):
    """Дата + N дней в ISO. Для сроков «действует не позднее чем через 14 дней»."""
    y, m, d = (int(x) for x in str(iso).split("-"))
    return (dt.date(y, m, d) + dt.timedelta(days=days)).isoformat()


# ---------------------------------------------------------------- суммы

def parse_total(form):
    """Сумма из формы: целое число рублей > 0.

    Договор, счёт или акт на ноль либо на минус — брак. HTML5-атрибут min
    обходится прямым POST, поэтому проверка обязана быть на сервере.
    """
    try:
        total = int(str(form.get("total", "")).strip())
    except (ValueError, TypeError):
        raise ValueError("Сумма указана некорректно — должно быть целое число рублей")
    if total <= 0:
        raise ValueError("Сумма должна быть больше нуля")
    return total


def split_prepay(total, percent):
    """Сумма → (аванс, остаток). Гарантия: аванс + остаток == сумма.

    Округление — БАНКОВСКОЕ (half-to-even), как round() в Python. Если считать
    half-up, аванс в счёте разойдётся на рубль с авансом, напечатанным в тексте
    договора, — и это заметит бухгалтерия клиента, а не ты.

    Остаток считается ВЫЧИТАНИЕМ, отдельно не округляется: иначе сумма двух
    счетов не сойдётся с суммой договора.
    """
    if not isinstance(percent, int) or not (0 <= percent <= 100):
        raise ValueError("Аванс — целый процент от 0 до 100")
    prepay = round(total * percent / 100)
    return prepay, total - prepay


# ---------------------------------------------------------------- контекст

def build_services(lines):
    """Список строк → пункты состава услуг: '- строка;', последний с точкой.

    Пустые строки выбрасываем: оператор жмёт Enter лишний раз, а в документе
    от этого появляется пустой пункт с прочерком.
    """
    items = [s.strip().rstrip(";.") for s in lines if s and s.strip()]
    if not items:
        return []
    out = ["- {};".format(x) for x in items[:-1]]
    out.append("- {}.".format(items[-1]))
    return out


def build_context(form, supplier):
    """Форма + реквизиты своей стороны → контекст шаблона.

    Диспетчер по типу документа: общая часть одна, различия — в дефолтах типа
    из doc_types.yaml. Новый тип НЕ требует новой ветки здесь, пока он
    укладывается в «предмет + состав + сроки + сумма».
    """
    doc_type_key = (form.get("doc_type") or "services").strip()
    dtype = get_doc_type(doc_type_key)

    total = parse_total(form)
    try:
        prepay_percent = int(str(form.get("prepay_percent") or "0").strip())
    except (ValueError, TypeError):
        raise ValueError("Аванс указан некорректно — целый процент от 0 до 100")
    prepay, remainder = split_prepay(total, prepay_percent)

    doc_date = (form.get("doc_date") or "").strip()
    date_q, date_long = date_forms(doc_date)

    # Срок оказания: либо одна дата, либо диапазон — зависит от секций типа.
    date_from = (form.get("date_from") or "").strip()
    date_to = (form.get("date_to") or "").strip()
    if date_to:
        term_service = "{} — {}".format(date_forms(date_from)[1], date_forms(date_to)[1])
        last_iso = date_to
    elif date_from:
        term_service = date_forms(date_from)[1]
        last_iso = date_from
    else:
        term_service = ""
        last_iso = doc_date

    # Номер документа: ГГГГММДД + порядковый за день. Выдаёт numbering.py —
    # сюда приходит готовым, чтобы контекст оставался чистой функцией.
    num = (form.get("num") or "").strip()

    subject = (form.get("subject") or "").strip() or dtype.get("subject_default", "")
    services_raw = (form.get("services_text") or "").splitlines()
    services = build_services(services_raw) or build_services(dtype.get("services_default", []))

    ctx = {
        # --- шапка документа
        "doc_title": dtype.get("contract_title", ""),
        "num": num,
        "doc_date_q": date_q,
        "doc_date_long": date_long,
        # --- стороны
        "supplier_name_full": supplier.get("name_full", ""),
        "supplier_name_short": supplier.get("name_short", ""),
        "supplier_inn": supplier.get("inn", ""),
        "supplier_kpp": supplier.get("kpp", ""),
        "supplier_ogrn": supplier.get("ogrn", ""),
        "supplier_address": supplier.get("address", ""),
        "supplier_bank": supplier.get("bank", ""),
        "supplier_rs": supplier.get("rs", ""),
        "supplier_ks": supplier.get("ks", ""),
        "supplier_bik": supplier.get("bik", ""),
        "supplier_email": supplier.get("email", ""),
        "supplier_phone": supplier.get("phone", ""),
        "supplier_signer_clause": supplier.get("signer_clause", ""),
        "supplier_signer_basis": supplier.get("signer_basis", ""),
        "supplier_signer_role_nom": supplier.get("signer_role_nom", ""),
        "supplier_signer_short": supplier.get("signer_short", ""),
        "vat_note": supplier.get("vat_note", ""),
        # --- контрагент (из формы, поля 1-в-1 со словарём requisites.py)
        "customer_name": (form.get("customer_name") or "").strip(),
        "customer_inn_kpp": (form.get("customer_inn_kpp") or "").strip(),
        "customer_ogrn": (form.get("customer_ogrn") or "").strip(),
        "customer_legal_addr": (form.get("customer_legal_addr") or "").strip(),
        "customer_postal_addr": (form.get("customer_postal_addr") or "").strip(),
        "customer_bank": (form.get("customer_bank") or "").strip(),
        "customer_rs": (form.get("customer_rs") or "").strip(),
        "customer_ks": (form.get("customer_ks") or "").strip(),
        "customer_bik": (form.get("customer_bik") or "").strip(),
        "customer_phone": (form.get("customer_phone") or "").strip(),
        "signer_clause": (form.get("signer_clause") or "").strip(),
        "signer_basis": (form.get("signer_basis") or "").strip(),
        "signer_role_nom": (form.get("signer_role_nom") or "").strip(),
        "signer_short": (form.get("signer_short") or "").strip(),
        # --- предмет и состав
        "subject": subject,
        "subject_cap": subject[:1].upper() + subject[1:] if subject else "",
        "format_line": dtype.get("format_line", ""),
        "services": services,
        # --- деньги
        "total_num": fmt_num(total),
        "total_words": rub_words(total),
        "total_full": money_full(total),
        "prepay_percent": str(prepay_percent),
        "prepay_full": money_full(prepay) if prepay else "",
        "remainder_full": money_full(remainder) if prepay else "",
        # --- сроки
        "term_service": term_service,
        "term_deadline": date_forms(plus_days(last_iso, 14))[1] if last_iso else "",
        # --- закрывающий документ
        "closing_doc": (form.get("closing_doc") or "Акт оказанных услуг").strip(),
    }
    return ctx
