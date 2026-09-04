"""Веб-сервис конструктора документов.

Слой HTTP и только он: принял форму — позвал домен — отдал файл. Никакой
бизнес-логики здесь нет специально. Так её можно тестировать без сервера,
а сам сервис потом заменить на CLI, на бота или на кнопку в CRM, не переписывая
ни одной формулы.

Запуск:  ./run.sh   (или: uvicorn app:app --reload --port 8000)
Открыть: http://127.0.0.1:8000

Сервис слушает 127.0.0.1 — только эта машина. Так и задумано: внутри ходят
персональные данные и банковские реквизиты, наружу им не надо. Выставлять
в интернет — отдельное решение с авторизацией, см. docs/07-pdn-i-bezopasnost.md.
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

import numbering
from catalog import load_closing_types, load_doc_types, load_supplier, supplier_is_example
from context import build_context, date_compact
from invoice import build_invoice_context, qr_png_bytes
from render import docx_to_pdf, render_docx
from requisites import check_requisites, find_contractor, parse_requisites
from validate import check_document

BASE = Path(__file__).parent
app = FastAPI(title="Конструктор документов")


async def form_dict(request):
    """Форма → обычный словарь. Списки (несколько значений одного имени)
    склеиваются переводом строки — так их ждёт build_services."""
    raw = await request.form()
    out = {}
    for key in raw.keys():
        values = raw.getlist(key)
        out[key] = "\n".join(values) if len(values) > 1 else values[0]
    return out


@app.get("/", response_class=HTMLResponse)
def index():
    html = (BASE / "templates" / "form.html").read_text(encoding="utf-8")
    types = load_doc_types()
    options = "".join(
        '<option value="{}">{}</option>'.format(key, cfg.get("label", key))
        for key, cfg in types.items()
    )
    banner = ""
    if supplier_is_example():
        banner = (
            '<div class="warn">Реквизиты берутся из <b>supplier.example.yaml</b> (нули). '
            'Скопируй его в <code>config/supplier.yaml</code> и впиши свои.</div>'
        )
    return html.replace("<!--DOC_TYPES-->", options).replace("<!--BANNER-->", banner)


@app.get("/doc-type/{key}")
def doc_type_info(key):
    """Дефолты типа — форма подставляет их при переключении."""
    types = load_doc_types()
    cfg = types.get(key)
    if not cfg:
        return JSONResponse({"_error": "Неизвестный тип документа"}, status_code=404)
    return {
        "label": cfg.get("label", key),
        "subject_default": cfg.get("subject_default", ""),
        "services_default": cfg.get("services_default", []),
        "form_sections": cfg.get("form_sections", []),
    }


@app.get("/next-number")
def next_number(date=""):
    """Следующий номер БЕЗ расхода (peek). Расходуется только при генерации."""
    try:
        return {"number": numbering.peek(date_compact(date))}
    except ValueError as e:
        return JSONResponse({"_error": str(e)}, status_code=400)


@app.get("/contractor")
def contractor(q=""):
    """Подстановка контрагента из базы config/contractors.md."""
    return find_contractor(q) or {}


@app.post("/recognize")
async def recognize(request: Request):
    """Текст карточки предприятия → поля формы + предупреждения по контрольным
    суммам. Разбор детерминированный, наружу ничего не уходит."""
    form = await form_dict(request)
    data = parse_requisites(form.get("text", ""))
    return {"fields": data, "warnings": check_requisites(data)}


@app.post("/check")
async def check(request: Request):
    """Проверка РЕЗУЛЬТАТА: собираем документ во временный файл и смотрим его.
    Номер при этом не расходуется — проверка не должна тратить нумерацию."""
    form = await form_dict(request)
    try:
        # Номер подставляем как при генерации, но НЕ фиксируем: проверка не
        # должна расходовать нумерацию, иначе каждый прогон оставляет дыру.
        if not (form.get("num") or "").strip():
            form["num"] = numbering.peek(date_compact(form.get("doc_date", "")))
        ctx = build_context(form, load_supplier())
        template = load_doc_types()[form.get("doc_type", "services")]["template"]
        path = render_docx(template, ctx, "_check.docx")
    except (ValueError, KeyError) as e:
        return {"errors": [str(e)], "warnings": []}
    return check_document(path, form)


@app.post("/generate")
async def generate(request: Request):
    """Договор. Номер расходуется ТОЛЬКО после успешной сборки файла (commit)."""
    form = await form_dict(request)
    try:
        supplier = load_supplier()
        number = (form.get("num") or "").strip() or numbering.peek(date_compact(form.get("doc_date", "")))
        form["num"] = number
        ctx = build_context(form, supplier)
        template = load_doc_types()[form.get("doc_type", "services")]["template"]
        path = render_docx(template, ctx, "dogovor_{}.docx".format(number))
    except (ValueError, KeyError) as e:
        return JSONResponse({"_error": str(e)}, status_code=400)
    numbering.commit(number)
    return FileResponse(path, filename=path.name)


@app.post("/akt")
async def akt(request: Request):
    """Закрывающий документ по тому же контексту, что и договор."""
    form = await form_dict(request)
    try:
        ctx = build_context(form, load_supplier())
        template = load_closing_types()["akt"]["template"]
        path = render_docx(template, ctx, "akt_{}.docx".format(ctx["num"] or "bez-nomera"))
    except (ValueError, KeyError) as e:
        return JSONResponse({"_error": str(e)}, status_code=400)
    return FileResponse(path, filename=path.name)


@app.post("/invoice")
async def invoice(request: Request):
    """Счёт: .docx, а при установленном LibreOffice — сразу PDF (его удобнее
    отправлять клиенту и в нём корректно виден QR)."""
    form = await form_dict(request)
    try:
        supplier = load_supplier()
        number = (form.get("invoice_num") or "").strip() or numbering.peek(
            date_compact(form.get("doc_date", ""))
        )
        ctx = build_invoice_context(
            form, supplier, number,
            contract_number=(form.get("num") or "").strip() or None,
            contract_date=(form.get("doc_date") or "").strip() or None,
        )
        path = render_docx(
            load_closing_types()["invoice"]["template"], ctx,
            "schet_{}.docx".format(number),
            images={"qr": (qr_png_bytes(ctx["qr_payload"]), 35)},
        )
    except (ValueError, KeyError) as e:
        return JSONResponse({"_error": str(e)}, status_code=400)
    numbering.commit(number)
    pdf = docx_to_pdf(path)
    target = pdf or path
    return FileResponse(target, filename=target.name)

