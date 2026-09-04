"""Счёт на оплату: контекст + платёжный QR-код по ГОСТ Р 56042.

Счёт — подмножество договора: те же стороны, тот же предмет, та же сумма плюс
основание («по договору №… от …»). Поэтому контекст переиспользуется целиком,
а не собирается заново: разойдутся — клиент получит счёт на сумму, которой нет
в договоре.

QR по ГОСТ Р 56042 — это ОБЫЧНЫЙ ПЕРЕВОД ПО РЕКВИЗИТАМ, который банк-приложение
считывает камерой. Не эквайринг, не платёжный шлюз: денег через тебя не проходит,
подключать ничего не нужно. Клиент наводит камеру и платит на твой счёт.
"""
import io

import qrcode

from context import build_context, date_forms, fmt_num, parse_total


def _qr_safe(value):
    """Чистит поле от разделителя ГОСТ '|' и переносов: они ломают структуру
    payload, и сканер банка читает мусор."""
    return str(value or "").replace("|", " ").replace("\n", " ").replace("\r", " ").strip()


def qr_purpose(number, iso_date, total_rubles, vat_note):
    """Назначение платежа для QR.

    Держим строку КОРОТКОЙ и без типографики. Банковские приложения подсвечивают
    поле красным на «ёлочках» и «ё», а строку длиннее ~210 символов молча режут.
    Полное основание (реквизиты договора, ссылка на оферту) остаётся в ТЕЛЕ счёта,
    где его читает человек, — в QR идёт то, что гарантированно проходит сканер.
    """
    y, m, d = str(iso_date).split("-")
    tail = " {}".format(vat_note).rstrip() if vat_note else ""
    return "Платеж по счету № {} от {}.{}.{}.{} - {}.00 руб.".format(
        number, d, m, y[2:], tail, total_rubles
    )


def build_qr_payload(supplier, total_rubles, purpose):
    """Платёжный QR по ГОСТ Р 56042.

    ST00012 — служебный заголовок: ST0001 = формат, последняя цифра = кодировка
    (2 = UTF-8). Сумма передаётся В КОПЕЙКАХ целым числом: рубли с точкой часть
    приложений не принимает.
    """
    fields = [
        "ST00012",
        "Name=" + _qr_safe(supplier.get("name_full")),
        "PersonalAcc=" + _qr_safe(supplier.get("rs")),
        "BankName=" + _qr_safe(supplier.get("bank")),
        "BIC=" + _qr_safe(supplier.get("bik")),
        "CorrespAcc=" + _qr_safe(supplier.get("ks")),
        "PayeeINN=" + _qr_safe(supplier.get("inn")),
        "Sum=" + str(int(total_rubles) * 100),
        "Purpose=" + _qr_safe(purpose),
    ]
    kpp = _qr_safe(supplier.get("kpp"))
    if kpp:
        fields.append("KPP=" + kpp)
    return "|".join(fields)


def qr_png_bytes(payload):
    """QR как PNG в память — вставляется в документ без временного файла."""
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_invoice_context(form, supplier, number, contract_number=None, contract_date=None):
    """Контекст счёта = контекст договора + номер, основание и QR."""
    ctx = build_context(form, supplier)
    total = parse_total(form)
    iso_date = (form.get("doc_date") or "").strip()

    ctx["invoice_num"] = number
    ctx["invoice_date_q"] = date_forms(iso_date)[0]
    ctx["invoice_total_num"] = fmt_num(total)

    if contract_number:
        basis = "Договор № {}".format(contract_number)
        if contract_date:
            basis += " от {}".format(date_forms(contract_date)[1])
        ctx["osnovanie"] = basis
    else:
        # Счёт без договора — тоже законный документ. Основанием служит
        # назначение платежа; при работе по оферте здесь печатается ссылка на неё.
        ctx["osnovanie"] = (form.get("osnovanie") or "").strip() or "Без договора"

    ctx["qr_payload"] = build_qr_payload(
        supplier, total, qr_purpose(number, iso_date, total, supplier.get("vat_note", ""))
    )
    return ctx
