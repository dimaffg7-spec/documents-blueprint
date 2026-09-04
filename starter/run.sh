#!/usr/bin/env bash
# Запуск сервиса. Первый раз — создаст окружение и соберёт демо-шаблоны.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "→ создаю окружение"
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi

if [ ! -f config/supplier.yaml ]; then
  echo "→ реквизиты ещё не заданы: сервис пойдёт на примере с нулями."
  echo "  Настроить: .venv/bin/python setup.py"
fi

if [ ! -f templates/dogovor_services.docx ]; then
  echo "→ собираю демо-шаблоны"
  .venv/bin/python build_demo_templates.py
fi

# --reload обязателен при разработке: без него правки в .py не подхватываются,
# а HTML перечитывается — получается «кнопка есть, а ручка отдаёт 404».
# 127.0.0.1 — сервис виден только с этой машины. Внутри ходят ПДн.
echo "→ http://127.0.0.1:8000"
.venv/bin/uvicorn app:app --reload --host 127.0.0.1 --port 8000
