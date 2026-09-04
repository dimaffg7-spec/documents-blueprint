"""Рендер: контекст → .docx (и опционально → PDF).

Тонкий слой. Вся «умная» работа сделана в context.py; здесь только подстановка
и конвертация. Это сознательно: подстановка — единственное место, где документ
физически собирается, и она должна быть скучной и предсказуемой.

autoescape=True обязателен: значения приходят от оператора, и амперсанд или
угловая скобка в названии организации без экранирования ломают XML документа —
файл просто не откроется.
"""
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage

BASE = Path(__file__).parent
TEMPLATES_DIR = BASE / "templates"
OUT_DIR = BASE / "out"


def render_docx(template_name, ctx, out_name, images=None):
    """Шаблон + контекст → путь к готовому .docx.

    images — {ключ шаблона: (png-байты, ширина в мм)}. Картинку нельзя просто
    положить в контекст строкой: docxtpl требует объект InlineImage, привязанный
    К КОНКРЕТНОМУ шаблону (изображение физически кладётся внутрь этого файла).
    Поэтому картинки собираются здесь, после открытия шаблона, а вызывающий код
    остаётся чистым и ничего не знает про docx.
    """
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        raise ValueError(
            "Нет шаблона {}. Собери демо-шаблоны: python build_demo_templates.py".format(template_name)
        )
    doc = DocxTemplate(str(template_path))
    ctx = dict(ctx)
    for key, (png, width_mm) in (images or {}).items():
        ctx[key] = InlineImage(doc, io.BytesIO(png), width=Mm(width_mm))
    doc.render(ctx, autoescape=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / out_name
    doc.save(str(out_path))
    return out_path


def _soffice_bin():
    """LibreOffice для конвертации в PDF. Ставится отдельно; без него сервис
    работает, просто отдаёт .docx."""
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    mac_path = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    return mac_path if Path(mac_path).exists() else None


def docx_to_pdf(docx_path):
    """.docx → .pdf через LibreOffice. None, если конвертер не установлен.

    Конвертация идёт во ВРЕМЕННОЙ папке с отдельным профилем: soffice отказывается
    запускать второй экземпляр с общим профилем, и параллельные запросы у него
    молча падают.
    """
    soffice = _soffice_bin()
    if not soffice:
        return None
    docx_path = Path(docx_path)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [soffice, "-env:UserInstallation=file://{}/profile".format(tmp),
             "--headless", "--convert-to", "pdf", "--outdir", tmp, str(docx_path)],
            check=True, capture_output=True, timeout=120,
        )
        produced = Path(tmp) / (docx_path.stem + ".pdf")
        if not produced.exists():
            return None
        target = OUT_DIR / produced.name
        shutil.copy(produced, target)
        return target
