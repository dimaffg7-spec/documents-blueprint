"""Реквизиты контрагента: контрольные суммы, распознавание из текста, база.

Три вещи, которые экономят больше всего времени в реальной работе:

1. КОНТРОЛЬНЫЕ СУММЫ. ИНН, ОГРН и банковские счета самопроверяемы — в них
   зашита контрольная цифра. Одна функция ловит опечатку до того, как документ
   уйдёт клиенту. Это не «валидация ради валидации»: неверный счёт в договоре =
   деньги ушли не туда.

2. РАСПОЗНАВАНИЕ ИЗ ТЕКСТА. Контрагент присылает карточку предприятия — оператор
   вставляет её текст, поля заполняются сами. Парсер ДЕТЕРМИНИРОВАННЫЙ: обычные
   регулярки, без LLM. Причина — в docs/07-pdn-i-bezopasnost.md: в юридическом
   документе нельзя допустить, чтобы цифру «дорисовала» языковая модель.

3. БАЗА КОНТРАГЕНТОВ. Обычный markdown-файл: раздел `## Название` + строки
   `- Метка: значение`. Читается человеком, правится руками, версионируется
   в git (если в нём нет банковских счетов — см. .gitignore).
"""
import re
from pathlib import Path

BASE = Path(__file__).parent
CONTRACTORS_PATH = BASE / "config" / "contractors.md"
CONTRACTORS_EXAMPLE = BASE / "config" / "contractors.example.md"

# Словарь полей: ключ контекста ↔ человеческая метка.
# ЭТО ЯДРО ВСЕЙ СИСТЕМЫ. Один и тот же ключ используется в форме, в шаблоне
# .docx, в базе контрагентов и в парсере. Разъедутся имена — начнётся ад
# переименований. Добавляешь поле — добавляешь его ЗДЕСЬ, одной строкой.
FIELD_LABELS = [
    ("customer_name", "Наименование"),
    ("customer_inn_kpp", "ИНН/КПП"),
    ("customer_ogrn", "ОГРН"),
    ("customer_legal_addr", "Юр. адрес"),
    ("customer_postal_addr", "Почтовый адрес"),
    ("customer_rs", "Расчётный счёт"),
    ("customer_bank", "Банк"),
    ("customer_ks", "Корр. счёт"),
    ("customer_bik", "БИК"),
    ("customer_phone", "Телефон"),
    ("signer_clause", "В лице"),
    ("signer_basis", "Действует на основании"),
    ("signer_role_nom", "Должность для подписи"),
    ("signer_short", "Подпись"),
]
LABEL2FIELD = {label: field for field, label in FIELD_LABELS}


def digits(s):
    return "".join(c for c in str(s or "") if c.isdigit())


# ------------------------------------------------------------ контрольные суммы

def inn_ok(inn):
    """Контрольная сумма ИНН (10 цифр — юрлицо, 12 — ИП/физлицо).

    Возвращает True/False, либо None если судить нельзя (другая длина —
    например, поле ещё не заполнено). None ≠ False: не пугаем оператора
    ошибкой там, где просто нет данных.
    """
    inn = digits(inn)

    def ctrl(weights):
        return sum(weights[i] * int(inn[i]) for i in range(len(weights))) % 11 % 10

    if len(inn) == 10:
        return ctrl([2, 4, 10, 3, 5, 9, 4, 6, 8]) == int(inn[9])
    if len(inn) == 12:
        return (ctrl([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == int(inn[10])
                and ctrl([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == int(inn[11]))
    return None


def ogrn_ok(value):
    """ОГРН (13 цифр) / ОГРНИП (15 цифр): остаток от деления числа без последней
    цифры на 11 (для ОГРНИП — на 13), младший разряд остатка = контрольная цифра."""
    o = digits(value)
    if len(o) == 13:
        return int(o[:12]) % 11 % 10 == int(o[12])
    if len(o) == 15:
        return int(o[:14]) % 13 % 10 == int(o[14])
    return None


def account_ok(account, bik, kind="rs"):
    """Ключевание банковского счёта по БИК (алгоритм ЦБ РФ).

    kind='rs' — расчётный счёт (проверяется по 3 последним цифрам БИК),
    kind='ks' — корреспондентский (по цифрам 5-6 БИК с префиксом '0').

    Это самая полезная проверка из трёх: опечатка в 20-значном счёте глазами
    не ловится вообще, а цена ошибки — платёж, ушедший в никуда.
    """
    acc, b = digits(account), digits(bik)
    if len(acc) != 20 or len(b) != 9:
        return None
    prefix = "0" + b[4:6] if kind == "ks" else b[6:9]
    s = prefix + acc  # 23 цифры
    weights = [7, 1, 3]
    return sum((weights[i % 3] * int(s[i])) % 10 for i in range(23)) % 10 == 0


def check_requisites(data):
    """Все проверки разом → список человеческих предупреждений.

    ПРЕДУПРЕЖДЕНИЯ, не ошибки: бывают легальные исключения (счёт в казначействе,
    иностранный контрагент). Оператор должен увидеть красный флаг и решить сам,
    а не упереться в стену.
    """
    warnings = []
    inn = (data.get("customer_inn_kpp") or "").split("/")[0]
    if inn_ok(inn) is False:
        warnings.append("ИНН: контрольная сумма не сходится — вероятна опечатка.")
    if ogrn_ok(data.get("customer_ogrn")) is False:
        warnings.append("ОГРН: контрольная сумма не сходится.")
    bik = data.get("customer_bik")
    if account_ok(data.get("customer_rs"), bik, "rs") is False:
        warnings.append("Расчётный счёт не сходится с БИК — проверь обе цифры.")
    if account_ok(data.get("customer_ks"), bik, "ks") is False:
        warnings.append("Корр. счёт не сходится с БИК — проверь обе цифры.")
    return warnings


# ------------------------------------------------------------ распознавание

def _after(text, *labels):
    """Значение после метки: 'ИНН: 0000000000' → '0000000000'.

    Метки перечисляются вариантами написания — реальные карточки пишут
    'Юридический адрес', 'Юр.адрес', 'Адрес юридический' и ещё десятком способов.
    """
    for label in labels:
        m = re.search(r"(?:{})\s*[:№-]?\s*(.+)".format(label), text, re.IGNORECASE)
        if m:
            value = m.group(1).strip().strip(",;")
            if value:
                return value
    return ""


def _digit_field(text, label_pattern, length, starts=None):
    """Числовое поле фиксированной длины рядом с меткой.

    Длина и префикс — вторая линия защиты от путаницы: расчётный счёт начинается
    с '40', корреспондентский — с '301'. Без этого карточка, где оба счёта идут
    подряд, регулярно записывается в одно поле дважды.

    Метка оборачивается в (?:...) обязательно. Без скобок альтернатива `A|B|C`
    склеивается с остатком выражения как `A` ИЛИ `B` ИЛИ `C[^\\d]...`: совпадёт
    голая первая метка, группы не будет, и поле молча останется пустым.
    """
    # Хвост: первая цифра + ещё (length-1) знаков, с запасом на пробелы внутри
    # номера («4070 0000 0000 …»). Минимум считается от length-1, а не от length:
    # иначе 20-значный счёт в САМОМ КОНЦЕ текста, без пробела после, не совпадает —
    # и поле молча остаётся пустым ровно в половине реальных карточек.
    pattern = r"(?:{})[^\d]{{0,40}}(\d[\d\s]{{{},{}}})".format(
        label_pattern, length - 1, length + 9
    )
    for m in re.finditer(pattern, text, re.IGNORECASE):
        value = digits(m.group(1))[:length]
        if len(value) == length and (not starts or value.startswith(starts)):
            return value
    return ""


def _unwrap_quotes(value):
    """Снимает кавычки, В КОТОРЫЕ ОБЁРНУТА ВСЯ строка, и только их.

    Наивный strip(' "«»') откусывает закрывающую кавычку у «ООО "Ромашка"» —
    получается 'ООО «Ромашка' и такой огрызок уезжает в договор. Проверяем
    именно пару: открывающая в начале И закрывающая в конце.
    """
    v = str(value or "").strip()
    for left, right in (('"', '"'), ("'", "'"), ("«", "»")):
        while len(v) > 1 and v.startswith(left) and v.endswith(right):
            v = v[1:-1].strip()
    return v


def parse_requisites(text):
    """Текст карточки предприятия → словарь полей.

    Работает по меткам, а не по позициям: карточки у всех свои, но слова
    'ИНН', 'БИК', 'Расчётный счёт' в них одинаковые.
    """
    text = str(text or "")
    data = {}

    name = _after(text, r"Полное наименование", r"Наименование организации",
                  r"Наименование", r"Организация")
    if name:
        data["customer_name"] = _unwrap_quotes(name)

    inn = _digit_field(text, r"ИНН", 10) or _digit_field(text, r"ИНН", 12)
    kpp = _digit_field(text, r"КПП", 9)
    if inn:
        data["customer_inn_kpp"] = "{}/{}".format(inn, kpp) if kpp else inn

    ogrn = _digit_field(text, r"ОГРНИП", 15) or _digit_field(text, r"ОГРН", 13)
    if ogrn:
        data["customer_ogrn"] = ogrn

    legal = _after(text, r"Юридический адрес", r"Юр\.?\s*адрес", r"Адрес места нахождения")
    if legal:
        data["customer_legal_addr"] = legal
    postal = _after(text, r"Почтовый адрес", r"Фактический адрес", r"Факт\.?\s*адрес")
    if postal:
        data["customer_postal_addr"] = postal

    bik = _digit_field(text, r"БИК", 9)
    if bik:
        data["customer_bik"] = bik
    rs = _digit_field(text, r"Расчётный счёт|Расчетный счёт|Расчетный счет|р/с|Р/С|Счёт получателя", 20, starts="40")
    if rs:
        data["customer_rs"] = rs
    ks = _digit_field(text, r"Корреспондентский счёт|Корреспондентский счет|Корр\.?\s*счёт|Корр\.?\s*счет|к/с|К/С", 20, starts="301")
    if ks:
        data["customer_ks"] = ks
    bank = _after(text, r"Наименование банка", r"Банк получателя", r"Банк")
    if bank:
        data["customer_bank"] = bank

    phone = _after(text, r"Телефон", r"Тел\.?")
    if phone:
        data["customer_phone"] = phone

    return data


# ------------------------------------------------------------ база контрагентов

def load_contractors():
    """Читает config/contractors.md → список словарей.

    Формат намеренно примитивный — markdown, который читает человек:

        ## ООО «Ромашка»
        - ИНН/КПП: 0000000000/000000000
        - Юр. адрес: ...
        - Алиасы: Ромашка, Romashka

    Почему не база данных: контрагентов у небольшой практики десятки, а не
    тысячи. Файл открывается, ищется глазами, правится и коммитится. База
    появится тогда, когда файл перестанет помещаться в голову — не раньше.
    """
    path = CONTRACTORS_PATH if CONTRACTORS_PATH.exists() else CONTRACTORS_EXAMPLE
    if not path.exists():
        return []
    out, cur = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if cur:
                out.append(cur)
            cur = {"customer_name": line[3:].strip()}
        elif cur is not None:
            m = re.match(r"\s*[-*]\s*(.+?):\s*(.+)", line)
            if m:
                label, value = m.group(1).strip(), m.group(2).strip()
                if label in LABEL2FIELD:
                    cur[LABEL2FIELD[label]] = value
                elif label == "Алиасы":
                    cur["_aliases"] = value
    if cur:
        out.append(cur)
    return out


def find_contractor(query):
    """Поиск контрагента по названию или алиасу. Пустой запрос → пусто."""
    q = (query or "").lower().strip()
    if not q:
        return {}
    for info in load_contractors():
        haystack = (info.get("customer_name", "") + " " + info.get("_aliases", "")).lower()
        if q in haystack or any(w in haystack for w in q.split() if len(w) > 3):
            return {k: v for k, v in info.items() if not k.startswith("_")}
    return {}
