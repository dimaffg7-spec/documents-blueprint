"""Сквозная нумерация документов: ГГГГММДДNNN, посуточный сброс.

Формат читается человеком (видно дату) и сортируется как строка. Три цифры
в хвосте — 999 документов в день; больше в ручном режиме не бывает, а расширять
формат задним числом нельзя: уже выданные номера не переписываются.

ГЛАВНОЕ ПРАВИЛО — PEEK / COMMIT.

  peek()   — узнать следующий номер, НЕ тратя его;
  commit() — зафиксировать, только когда файл реально собран.

Почему так. Если инкрементить счётчик до рендера, каждый сбой (упал конвертер,
оператор закрыл вкладку) оставляет ДЫРУ в нумерации. Для счетов и актов дыра —
это вопрос от бухгалтерии «а где документ №...?», на который нет ответа.
Инкремент только после успеха.

Хранилище здесь — файл, потому что это локальный однопользовательский сервис.
Как только операторов становится больше одного, файл заменяется на таблицу в БД
с блокировкой на дату — см. docs/04-schet-i-numeraciya.md, там разобран этот
переход и почему @unique + retry недостаточно без блокировки.
"""
from pathlib import Path

BASE = Path(__file__).parent
COUNTER_PATH = BASE / "data" / "counter.txt"
MAX_DAILY_SEQ = 999


def _read():
    """Файл хранит одну строку 'ГГГГММДД:seq'."""
    if not COUNTER_PATH.exists():
        return "", 0
    raw = COUNTER_PATH.read_text(encoding="utf-8").strip()
    if ":" not in raw:
        return "", 0
    date_part, seq_part = raw.split(":", 1)
    try:
        return date_part, int(seq_part)
    except ValueError:
        return "", 0


def peek(date_compact):
    """Следующий номер за дату — БЕЗ расхода. Ровно эту строку показываем
    оператору в форме и печатаем в документ."""
    stored_date, seq = _read()
    next_seq = seq + 1 if stored_date == date_compact else 1
    if next_seq > MAX_DAILY_SEQ:
        raise ValueError(
            "Исчерпан суточный лимит номеров ({}/день) за {}. "
            "Похоже на ошибку — проверь счётчик.".format(MAX_DAILY_SEQ, date_compact)
        )
    return "{}{:03d}".format(date_compact, next_seq)


def commit(number):
    """Зафиксировать израсходованный номер. Вызывается ТОЛЬКО после того, как
    документ успешно собран и отдан."""
    date_compact, seq = number[:8], int(number[8:])
    COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    COUNTER_PATH.write_text("{}:{}".format(date_compact, seq), encoding="utf-8")
