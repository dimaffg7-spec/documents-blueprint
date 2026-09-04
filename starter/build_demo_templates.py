"""Сборка ДЕМО-шаблонов .docx из кода.

Запусти один раз перед первым стартом:

    python build_demo_templates.py

Зачем шаблоны собираются скриптом, а не лежат готовыми файлами.

1. В репозиторий нельзя класть чужие договоры. Тело реального договора —
   документ конкретных сторон; выкладывать его наружу нельзя. Демо-текст ниже
   написан с нуля и юридической силы не имеет — он нужен, чтобы конвейер
   заработал в первую минуту.

2. Это ЖИВОЙ ПРИЁМ, а не костыль для демо. Когда придёт время подставить своё
   тело договора, править .docx руками нельзя: Word дробит текст на runs
   (иногда посимвольно), и `{{ customer_name }}`, набранный в редакторе,
   физически распадается на куски — подстановка его не увидит. Правильный путь
   описан в docs/02-shablon-docx.md: скрипт открывает эталон, находит текст
   ПО АБЗАЦАМ и переписывает абзац целиком, вместе с плейсхолдером.

3. force_font в конце — обязательный шаг. Абзацы, переписанные начисто,
   создают runs без явного шрифта, и Word берёт шрифт темы (Calibri). Документ
   при этом «проходит все тесты»: плейсхолдеров нет, поля на месте — просто он
   набран не тем шрифтом. Ловится только глазами.
"""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

BASE = Path(__file__).parent
TEMPLATES_DIR = BASE / "templates"
FONT = "Times New Roman"
FONT_SIZE = Pt(11)


def force_font(doc, name=FONT, size=FONT_SIZE):
    """Проставляет шрифт ВЕЗДЕ: параграфы, таблицы, колонтитулы.

    Без этого шага переписанные абзацы берут шрифт темы Office. Проверено
    на практике: баг живёт месяцами, потому что текстовые проверки его не видят.
    """
    def fix(paragraph):
        for run in paragraph.runs:
            run.font.name = name
            run.font.size = size

    for p in doc.paragraphs:
        fix(p)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    fix(p)
    for section in doc.sections:
        for part in (section.header, section.footer):
            for p in part.paragraphs:
                fix(p)


def para(doc, text, bold=False, align=None, space_after=6):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    return p


def requisites_table(doc):
    """Блок реквизитов сторон — две колонки.

    Ширины задаются на уровне таблицы. Для docx это важнее, чем кажется:
    при фиксированной раскладке рендерер (особенно LibreOffice) берёт ширины
    из грида таблицы, а не из отдельных ячеек. Зададите только ячейки —
    текст сожмётся «в столбик» и уедет на вторую страницу.
    """
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    left, right = table.rows[0].cells

    left.paragraphs[0].add_run("ИСПОЛНИТЕЛЬ").bold = True
    for line in (
        "{{ supplier_name_full }}",
        "ИНН {{ supplier_inn }} КПП {{ supplier_kpp }}",
        "ОГРН {{ supplier_ogrn }}",
        "Адрес: {{ supplier_address }}",
        "Банк: {{ supplier_bank }}",
        "Р/с {{ supplier_rs }}",
        "К/с {{ supplier_ks }}",
        "БИК {{ supplier_bik }}",
        "Тел.: {{ supplier_phone }}",
        "E-mail: {{ supplier_email }}",
        "",
        "{{ supplier_signer_role_nom }}",
        "_______________ / {{ supplier_signer_short }}",
    ):
        left.add_paragraph(line)

    right.paragraphs[0].add_run("ЗАКАЗЧИК").bold = True
    for line in (
        "{{ customer_name }}",
        "ИНН/КПП {{ customer_inn_kpp }}",
        "ОГРН {{ customer_ogrn }}",
        "Юр. адрес: {{ customer_legal_addr }}",
        "Почтовый адрес: {{ customer_postal_addr }}",
        "Банк: {{ customer_bank }}",
        "Р/с {{ customer_rs }}",
        "К/с {{ customer_ks }}",
        "БИК {{ customer_bik }}",
        "Тел.: {{ customer_phone }}",
        "",
        "{{ signer_role_nom }}",
        "_______________ / {{ signer_short }}",
    ):
        right.add_paragraph(line)
    return table


def build_contract(filename, kind_title):
    """Демо-тело договора. Заменяется на своё — см. docs/02-shablon-docx.md."""
    doc = Document()
    para(doc, "ДОГОВОР {{ doc_title }} № {{ num }}", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, "г. Город", align=WD_ALIGN_PARAGRAPH.LEFT, space_after=0)
    para(doc, "{{ doc_date_q }}", align=WD_ALIGN_PARAGRAPH.RIGHT)

    para(doc,
         "{{ supplier_name_full }}, {{ supplier_signer_clause }}, действующего на основании "
         "{{ supplier_signer_basis }}, именуемое в дальнейшем «Исполнитель», с одной стороны, и "
         "{{ customer_name }}, {{ signer_clause }}, действующего на основании {{ signer_basis }}, "
         "именуемое в дальнейшем «Заказчик», с другой стороны, заключили настоящий Договор "
         "о нижеследующем.")

    para(doc, "1. ПРЕДМЕТ ДОГОВОРА", bold=True)
    para(doc, "1.1. Исполнитель обязуется оказать {{ subject }}, а Заказчик — принять и оплатить их.")
    para(doc, "1.2. Услуги оказываются {{ format_line }}.")
    para(doc, "1.3. Состав услуг определён Приложением №1 к настоящему Договору.")

    para(doc, "2. СРОКИ", bold=True)
    para(doc, "2.1. Срок оказания услуг: {{ term_service }}.")
    para(doc, "2.2. Договор действует до {{ term_deadline }}, а в части расчётов — "
              "до полного исполнения обязательств.")

    para(doc, "3. ЦЕНА И ПОРЯДОК РАСЧЁТОВ", bold=True)
    para(doc, "3.1. Стоимость услуг составляет {{ total_full }}.")
    para(doc, "3.2. Аванс — {{ prepay_percent }}% от стоимости, что составляет {{ prepay_full }}; "
              "окончательный расчёт — {{ remainder_full }} после подписания закрывающего документа.")
    para(doc, "3.3. Закрывающий документ: {{ closing_doc }}.")

    para(doc, "4. РЕКВИЗИТЫ И ПОДПИСИ СТОРОН", bold=True)
    requisites_table(doc)

    doc.add_page_break()
    para(doc, "Приложение №1 к Договору № {{ num }} от {{ doc_date_q }}",
         align=WD_ALIGN_PARAGRAPH.RIGHT)
    para(doc, "СОСТАВ УСЛУГ", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, "{{ subject_cap }}, включая:")
    # Цикл по списку — единственная «логика», допустимая в шаблоне: она про
    # структуру документа, а не про бизнес-правила.
    #
    # Теги пишутся как {%p ... %} — это docxtpl-синтаксис «на уровне абзаца».
    # Обычный {% for %} внутри абзаца оставит после себя пустые строки, а перенос
    # \n внутри run в Word вообще не перенос — текст слипнется в одну строку.
    para(doc, "{%p for item in services %}")
    para(doc, "{{ item }}")
    para(doc, "{%p endfor %}")
    para(doc, "")
    requisites_table(doc)

    force_font(doc)
    out = TEMPLATES_DIR / filename
    doc.save(str(out))
    return out


def build_akt():
    doc = Document()
    para(doc, "АКТ оказанных услуг № {{ num }}", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, "к Договору № {{ num }} от {{ doc_date_q }}", align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, "{{ doc_date_q }}", align=WD_ALIGN_PARAGRAPH.RIGHT)
    para(doc, "Исполнитель {{ supplier_name_full }} оказал, а Заказчик {{ customer_name }} принял "
              "следующие услуги: {{ subject }}.")
    para(doc, "Стоимость оказанных услуг: {{ total_full }}. {{ vat_note }}.")
    para(doc, "Услуги оказаны в полном объёме и в срок. Стороны претензий не имеют.")
    # В акте НЕТ условий оплаты: акт фиксирует факт оказания, а не порядок расчётов.
    requisites_table(doc)
    force_font(doc)
    out = TEMPLATES_DIR / "akt.docx"
    doc.save(str(out))
    return out


def build_invoice():
    doc = Document()
    para(doc, "Счёт на оплату № {{ invoice_num }} от {{ invoice_date_q }}",
         bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)

    bank = doc.add_table(rows=4, cols=2)
    bank.style = "Table Grid"
    rows = [
        ("Банк получателя", "{{ supplier_bank }}"),
        ("БИК / К/с", "{{ supplier_bik }} / {{ supplier_ks }}"),
        ("Получатель", "{{ supplier_name_full }}, ИНН {{ supplier_inn }}"),
        ("Счёт получателя", "{{ supplier_rs }}"),
    ]
    for i, (label, value) in enumerate(rows):
        bank.rows[i].cells[0].paragraphs[0].add_run(label).bold = True
        bank.rows[i].cells[1].paragraphs[0].add_run(value)

    para(doc, "")
    para(doc, "Плательщик: {{ customer_name }}, ИНН/КПП {{ customer_inn_kpp }}, "
              "{{ customer_legal_addr }}")
    para(doc, "Основание: {{ osnovanie }}")

    items = doc.add_table(rows=2, cols=3)
    items.style = "Table Grid"
    for i, head in enumerate(("Наименование", "Кол-во", "Сумма, руб.")):
        items.rows[0].cells[i].paragraphs[0].add_run(head).bold = True
    items.rows[1].cells[0].paragraphs[0].add_run("{{ subject_cap }}")
    items.rows[1].cells[1].paragraphs[0].add_run("1")
    items.rows[1].cells[2].paragraphs[0].add_run("{{ invoice_total_num }}")

    para(doc, "Всего к оплате: {{ total_full }}. {{ vat_note }}.", bold=True)
    para(doc, "")
    # Платёжный QR по ГОСТ Р 56042. Плательщик наводит камеру банк-приложения
    # и платит по реквизитам — без эквайринга и без ручного ввода 20 цифр счёта.
    # Картинка приходит из кода объектом InlineImage (см. render.render_docx).
    para(doc, "Оплата сканированием:", bold=True)
    para(doc, "{{ qr }}")
    para(doc, "")
    para(doc, "{{ supplier_signer_role_nom }} _______________ / {{ supplier_signer_short }}")
    force_font(doc)
    out = TEMPLATES_DIR / "invoice.docx"
    doc.save(str(out))
    return out


def main():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    made = [
        build_contract("dogovor_services.docx", "оказания услуг"),
        build_contract("dogovor_supply.docx", "поставки"),
        build_akt(),
        build_invoice(),
    ]
    for path in made:
        print("собран:", path.relative_to(BASE))
    print("\nДемо-шаблоны готовы. Это ЗАГЛУШКИ без юридической силы —")
    print("подставь своё тело документа по docs/02-shablon-docx.md.")


if __name__ == "__main__":
    main()
