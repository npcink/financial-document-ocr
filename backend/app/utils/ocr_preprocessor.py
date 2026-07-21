import re
from typing import Dict, List, Tuple

NOISE_CHARS = r'[*+=|─━┄┅┆┇┊┋┌┐└┘├┤┬┴┼▁▂▃▄▅▆▇█░▒▓■□▪▫▬▭▮▯'

FIELD_NAME_MAPPING: List[Tuple[str, str]] = [
    (r'发[票標]代码?', '发票代码'),
    (r'发[票標]号码?', '发票号码'),
    (r'电子发票代码?', '发票代码'),
    (r'电子发票号码?', '发票号码'),
    (r'纳税人识别号|统一社会信用代码|税号', '纳税人识别号'),
    (r'购[买方]纳税人识别号', '购买方纳税人识别号'),
    (r'销[售方]纳税人识别号', '销售方纳税人识别号'),
    (r'购买方名称', '购买方名称'),
    (r'销售方名称', '销售方名称'),
    (r'购方名称', '购买方名称'),
    (r'销方名称', '销售方名称'),
    (r'价税合计\s*[（(]大写[)）]', '价税合计大写'),
    (r'价税合计\s*[（(]小写[)）]', '价税合计小写'),
    (r'价税合计大写', '价税合计大写'),
    (r'价税合计小写', '价税合计小写'),
    (r'价税合计', '价税合计'),
    (r'合\s*计\s*金\s*额', '合计金额'),
    (r'金额合计', '金额合计'),
    (r'合\s*计', '合计'),
    (r'小写', '小写金额'),
    (r'大写', '大写金额'),
    (r'税\s*额', '税额'),
    (r'税\s*款', '税额'),
    (r'开[票標]日期', '开票日期'),
    (r'日\s*期', '日期'),
    (r'开户行及账\s*号', '开户行及账号'),
    (r'开户行', '开户行'),
    (r'付\s*款\s*人\s*户?\s*名', '付款人户名'),
    (r'收\s*款\s*人\s*户?\s*名', '收款人户名'),
    (r'付\s*款\s*人\s*账\s*号', '付款人账号'),
    (r'收\s*款\s*人\s*账\s*号', '收款人账号'),
    (r'付\s*款\s*人\s*开户银行', '付款人开户银行'),
    (r'收\s*款\s*人\s*开户银行', '收款人开户银行'),
    (r'付\s*款\s*方\s*账\s*号', '付款方账号'),
    (r'收\s*款\s*方\s*账\s*号', '收款方账号'),
    (r'付\s*款\s*账号', '付款方账号'),
    (r'收\s*款\s*账号', '收款方账号'),
    (r'交易流水\s*号?', '交易流水号'),
    (r'转\s*账\s*单\s*号', '交易流水号'),
    (r'交\s*易\s*单\s*号', '交易流水号'),
    (r'支\s*付\s*单\s*号', '交易流水号'),
    (r'流水\s*号?', '流水号'),
    (r'交\s*易\s*金\s*额', '交易金额'),
    (r'实\s*付\s*金\s*额', '交易金额'),
    (r'支\s*付\s*金\s*额', '交易金额'),
    (r'转\s*账\s*金\s*额', '转账金额'),
    (r'金\s*额', '金额'),
    (r'付\s*款\s*方\s*名\s*称', '付款方名称'),
    (r'收\s*款\s*方\s*名\s*称', '收款方名称'),
    (r'转\s*账\s*时\s*间', '转账时间'),
    (r'交\s*易\s*时\s*间', '交易时间'),
    (r'支\s*付\s*时\s*间', '支付时间'),
    (r'支\s*付\s*日\s*期', '支付日期'),
    (r'当\s*前\s*状\s*态', '当前状态'),
    (r'交\s*易\s*状\s*态', '交易状态'),
    (r'收\s*款\s*方\s*备\s*注', '收款方备注'),
    (r'支\s*付\s*方\s*式', '支付方式'),
    (r'银\s*行\s*账\s*号', '银行账号'),
    (r'账\s*号', '账号'),
    (r'收据编\s*号', '收据编号'),
    (r'收\s*据\s*NO', '收据编号'),
    (r'收\s*款\s*单\s*位', '收款单位'),
    (r'付\s*款\s*单\s*位', '付款单位'),
    (r'收\s*款\s*事\s*由', '收款事由'),
    (r'经\s*办\s*人', '经办人'),
    (r'今\s*收\s*到', '今收到'),
]

DIGIT_FIX_PATTERNS = [
    (r'(\d)[Oo](?=\d{3,})', r'\g<1>0'),
    (r'(\d)[lLI](?=\d)', r'\g<1>1'),
    (r'\b[Oo](\d{7,}\b)', r'0\g<1>'),
    (r'(\d{7,})[Oo]\b', r'\g<1>0'),
]

AMOUNT_FIX_PATTERNS = [
    (r'(\d)[\s,]+(\d{3})', r'\1\2'),
    (r'(\d)\s+\.(\d)', r'\1.\2'),
    (r'(\d+\.\d{2})\.+\d*', r'\1'),
]

DATE_FIX_PATTERNS = [
    (r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?', r'\1年\2月\3日'),
]


def remove_ocr_noise(text: str) -> str:
    for char in NOISE_CHARS:
        text = text.replace(char, '')
    text = re.sub(r'[+_=|]{2,}', '', text)
    return text


def normalize_whitespace(text: str) -> str:
    text = text.replace('\t', ' ')
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r' +$', '', text, flags=re.MULTILINE)
    return text


def normalize_field_names(text: str) -> str:
    for pattern, standard_name in FIELD_NAME_MAPPING:
        text = re.sub(pattern, standard_name, text)
    return text


def normalize_single_field_name(field_name: str) -> str:
    suffix = ""
    base_name = field_name
    suffix_match = re.match(r"^(.*?)([_-]\d+)$", field_name)
    if suffix_match:
        base_name = suffix_match.group(1)
        suffix = suffix_match.group(2)

    for pattern, standard_name in FIELD_NAME_MAPPING:
        if re.search(pattern, base_name):
            return f"{standard_name}{suffix}"
    return field_name


def fix_common_ocr_errors(text: str) -> str:
    for pattern, replacement in DIGIT_FIX_PATTERNS:
        text = re.sub(pattern, replacement, text)
    for pattern, replacement in AMOUNT_FIX_PATTERNS:
        text = re.sub(pattern, replacement, text)
    for pattern, replacement in DATE_FIX_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


def remove_page_noise(text: str) -> str:
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        line = line.strip()
        if re.match(r'^\d{1,3}$', line):
            continue
        if re.match(r'^第\s*\d+\s*页', line):
            continue
        if re.match(r'^Page\s+\d+', line, re.IGNORECASE):
            continue
        if re.match(r'^[^\w\u4e00-\u9fff]+$', line):
            continue
        if line:
            cleaned.append(line)
    return '\n'.join(cleaned)


def merge_broken_lines(text: str) -> str:
    lines = text.split('\n')
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if (
            i + 1 < len(lines)
            and line
            and not re.search(r'[。，；：！？、]$', line)
            and len(line) < 50
        ):
            next_line = lines[i + 1].strip()
            if next_line and len(next_line) < 50 and not re.match(r'^[A-Z\d]', next_line):
                line = line + next_line
                i += 2
                merged.append(line)
                continue
        merged.append(line)
        i += 1
    return '\n'.join(merged)


def handle_cipher_text(text: str) -> str:
    def merge_cipher(match: re.Match) -> str:
        cipher = match.group(0)
        return re.sub(r'[\s\n]+', '', cipher)

    text = re.sub(
        r'([A-Z0-9]{20,}(?:\s*[\n\r]+\s*[A-Z0-9]{20,}){2,})',
        merge_cipher,
        text
    )
    return text


def preprocess_ocr_text(text: str) -> Tuple[str, Dict[str, List[str]]]:
    if not text:
        return "", {}

    logs: Dict[str, List[str]] = {
        'noise_removed': [],
        'field_normalized': [],
        'digit_fixed': [],
        'amount_fixed': [],
        'date_fixed': [],
    }

    original = text
    text = remove_ocr_noise(text)
    if text != original:
        logs['noise_removed'].append(f"removed_noise: {len(original)} -> {len(text)} chars")

    text = normalize_whitespace(text)

    original = text
    text = normalize_field_names(text)
    if text != original:
        logs['field_normalized'].append("field_names_normalized")

    original = text
    text = fix_common_ocr_errors(text)
    if text != original:
        logs['digit_fixed'].append("fixed_digit_errors")

    amount_original = text
    for pattern, replacement in AMOUNT_FIX_PATTERNS:
        text = re.sub(pattern, replacement, text)
    if text != amount_original:
        logs['amount_fixed'].append("fixed_amount_format")

    date_original = text
    for pattern, replacement in DATE_FIX_PATTERNS:
        text = re.sub(pattern, replacement, text)
    if text != date_original:
        logs['date_fixed'].append("fixed_date_format")

    text = handle_cipher_text(text)
    text = remove_page_noise(text)
    text = merge_broken_lines(text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text, logs


def quick_preprocess(text: str) -> str:
    cleaned, _ = preprocess_ocr_text(text)
    return cleaned
