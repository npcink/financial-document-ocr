import re
from typing import Dict, List, Tuple, Optional

VALIDATION_PATTERNS = {
    'invoice_code': r'^\d{10}(?:\d{2})?$',
    'invoice_no': r'^\d{8}$',
    'invoice_no_20': r'^\d{20}$',
    'tax_id': r'^[A-Z0-9]{15}$|^[A-Z0-9]{18}$|^[A-Z0-9]{20}$',
    'amount': r'^-?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?$|^-?\d+(?:\.\d{1,2})?$',
    'cn_amount': r'^[人民币零壹贰叁肆伍陆柒捌玖拾佰仟万亿圆元角分整正]+$',
    'date_iso': r'^\d{4}-\d{2}-\d{2}$',
    'date_cn': r'^\d{4}年\d{1,2}月\d{1,2}日?$',
    'bank_account': r'^\d{10,25}$',
    'transaction_id': r'^[A-Za-z0-9_-]{8,80}$',
    'phone': r'^1[3-9]\d{9}$',
    'cipher': r'^[A-Z0-9]{80,120}$',
}

FIELD_VALIDATORS = {
    'invoice': {
        '发票代码': ('invoice_code',),
        '发票号码': ('invoice_no', 'invoice_no_20'),
        '购买方纳税人识别号': ('tax_id',),
        '销售方纳税人识别号': ('tax_id',),
        '开票日期': ('date_iso', 'date_cn'),
        '金额合计': ('amount',),
        '税额': ('amount',),
        '价税合计': ('amount',),
        '价税合计小写': ('amount',),
    },
    'receipt': {
        '日期': ('date_iso', 'date_cn'),
        '金额小写': ('amount',),
        '金额大写': ('cn_amount',),
    },
    'bank_receipt': {
        '交易日期': ('date_iso', 'date_cn'),
        '付款方账号': ('bank_account',),
        '收款方账号': ('bank_account',),
        '交易金额': ('amount',),
        '转账金额': ('amount',),
        '交易流水号': ('transaction_id',),
    },
    'transaction_list': {
        '交易日期': ('date_iso', 'date_cn'),
        '交易金额': ('amount',),
    },
    'subscription_record': {
        '订购时间': ('date_iso', 'date_cn'),
        '有效期开始': ('date_iso', 'date_cn'),
        '有效期结束': ('date_iso', 'date_cn'),
        '退订时间': ('date_iso', 'date_cn'),
        '月费': ('amount',),
    },
}


def validate_field_value(field_name: str, value: str, doc_type: str = '') -> Tuple[bool, str]:
    if not value or not str(value).strip():
        return True, 'empty'

    value = str(value).strip()

    validators = FIELD_VALIDATORS.get(doc_type, {})
    patterns = validators.get(field_name)

    if not patterns:
        return True, 'no_validator'

    for pattern_name in patterns:
        pattern = VALIDATION_PATTERNS.get(pattern_name)
        if pattern and re.match(pattern, value):
            return True, pattern_name

    return False, 'format_mismatch'


def try_auto_fix(field_name: str, value: str, doc_type: str = '') -> Tuple[str, bool]:
    if not value:
        return value, False

    original = str(value).strip()
    fixed = original

    if 'amount' in FIELD_VALIDATORS.get(doc_type, {}).get(field_name, ()):
        fixed = fixed.replace('¥', '').replace('元', '').replace(',', '').strip()
        fixed = re.sub(r'\s+', '', fixed)
        if re.match(r'^-?\d+\.\d{2}$', fixed):
            return fixed, True

    if 'invoice_code' in FIELD_VALIDATORS.get(doc_type, {}).get(field_name, ()):
        fixed = fixed.replace('O', '0').replace('o', '0').replace('I', '1').replace('l', '1')
        fixed = re.sub(r'\D', '', fixed)
        if re.match(r'^\d{10}(?:\d{2})?$', fixed):
            return fixed, True

    if 'invoice_no' in FIELD_VALIDATORS.get(doc_type, {}).get(field_name, ()):
        fixed = fixed.replace('O', '0').replace('o', '0').replace('I', '1').replace('l', '1')
        fixed = re.sub(r'\D', '', fixed)
        if re.match(r'^\d{8}$', fixed) or re.match(r'^\d{20}$', fixed):
            return fixed, True

    if 'tax_id' in FIELD_VALIDATORS.get(doc_type, {}).get(field_name, ()):
        fixed = fixed.replace('O', '0').replace('o', '0').replace('I', '1').replace('l', '1')
        fixed = re.sub(r'\s', '', fixed)
        if re.match(r'^[A-Z0-9]{15}$|^[A-Z0-9]{18}$|^[A-Z0-9]{20}$', fixed):
            return fixed, True

    if 'date_iso' in FIELD_VALIDATORS.get(doc_type, {}).get(field_name, ()):
        fixed = fixed.replace('/', '-').replace('.', '-')
        fixed = re.sub(r'(\d{4})-(\d{1,2})-(\d{1,2})', lambda m: f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}", fixed)
        if re.match(r'^\d{4}-\d{2}-\d{2}$', fixed):
            return fixed, True

    if 'bank_account' in FIELD_VALIDATORS.get(doc_type, {}).get(field_name, ()):
        fixed = re.sub(r'\D', '', fixed)
        if re.match(r'^\d{10,25}$', fixed):
            return fixed, True

    return original, False


def validate_llm_result(result: Dict, doc_type: str = '') -> Dict:
    if not result or not isinstance(result, dict):
        return {'valid': False, 'errors': ['invalid_result_structure'], 'fields': {}}

    fields = result.get('fields', {})
    if not fields:
        return {'valid': False, 'errors': ['no_fields'], 'fields': {}}

    validation_result = {
        'valid': True,
        'errors': [],
        'fields': {},
        'auto_fixed': {},
        'needs_review': [],
    }

    for field_name, field_data in fields.items():
        if not isinstance(field_data, dict):
            continue

        value = field_data.get('value', '')
        confidence = field_data.get('confidence', 1.0)

        is_valid, validator = validate_field_value(field_name, value, doc_type)

        if not is_valid:
            fixed_value, was_fixed = try_auto_fix(field_name, value, doc_type)
            if was_fixed:
                validation_result['auto_fixed'][field_name] = {
                    'original': value,
                    'fixed': fixed_value,
                }
                fields[field_name]['value'] = fixed_value
                validation_result['fields'][field_name] = {
                    'status': 'auto_fixed',
                    'original_value': value,
                    'fixed_value': fixed_value,
                    'confidence': confidence,
                }
            else:
                validation_result['valid'] = False
                validation_result['errors'].append(f"invalid_format: {field_name} = {value}")
                validation_result['fields'][field_name] = {
                    'status': 'invalid',
                    'value': value,
                    'expected': FIELD_VALIDATORS.get(doc_type, {}).get(field_name, []),
                }
                validation_result['needs_review'].append(field_name)
        else:
            validation_result['fields'][field_name] = {
                'status': 'valid',
                'value': value,
                'validator': validator,
            }

    return validation_result


def get_field_validation_hint(field_name: str, doc_type: str = '') -> Optional[str]:
    validators = FIELD_VALIDATORS.get(doc_type, {}).get(field_name)
    if not validators:
        return None

    hints = []
    for v in validators:
        if v == 'invoice_code':
            hints.append('10或12位数字')
        elif v == 'invoice_no':
            hints.append('8位数字')
        elif v == 'tax_id':
            hints.append('15/18/20位字母数字')
        elif v == 'amount':
            hints.append('数字格式，保留2位小数')
        elif v == 'cn_amount':
            hints.append('中文大写金额')
        elif v == 'date_iso':
            hints.append('YYYY-MM-DD格式')
        elif v == 'bank_account':
            hints.append('10-25位数字')
        elif v == 'transaction_id':
            hints.append('8-80位字母、数字、下划线或短横线')

    return '、'.join(hints) if hints else None
