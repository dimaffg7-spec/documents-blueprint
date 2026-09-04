"""Чтение конфигов: типы документов и реквизиты своей стороны.

Отдельный тонкий модуль, чтобы «где лежат настройки» знал ровно один файл.
Когда конфиг читают из пяти мест, добавление шестого типа документа превращается
в археологию.
"""
from pathlib import Path

import yaml

BASE = Path(__file__).parent
DOC_TYPES_PATH = BASE / "config" / "doc_types.yaml"
SUPPLIER_PATH = BASE / "config" / "supplier.yaml"
SUPPLIER_EXAMPLE = BASE / "config" / "supplier.example.yaml"


def _load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_doc_types():
    return _load_yaml(DOC_TYPES_PATH).get("doc_types", {})


def load_closing_types():
    return _load_yaml(DOC_TYPES_PATH).get("closing_types", {})


def get_doc_type(key):
    types = load_doc_types()
    if key not in types:
        raise ValueError(
            "Неизвестный тип документа: {!r}. Доступные: {}".format(key, ", ".join(sorted(types)))
        )
    return types[key]


def load_supplier():
    """Свои реквизиты. Нет supplier.yaml — работаем на примере и громко об этом
    говорим: пустой блок реквизитов в договоре страшнее, чем нули из примера."""
    if SUPPLIER_PATH.exists():
        return _load_yaml(SUPPLIER_PATH)["supplier"]
    return _load_yaml(SUPPLIER_EXAMPLE)["supplier"]


def supplier_is_example():
    return not SUPPLIER_PATH.exists()
