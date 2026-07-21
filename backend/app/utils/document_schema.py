import re
from typing import Any, Optional


DOCUMENT_SCHEMAS = {
    "bank_receipt": {
        "name": "银行回单",
        "required": ["交易金额", "交易日期"],
        "recommended": ["付款方账号", "收款方账号", "交易流水号"],
        "order": [
            "电子回单号码", "付款方户名", "付款方名称", "付款方账号", "付款方开户行",
            "收款方户名", "收款方名称", "收款方账号", "收款方开户行",
            "交易金额", "原始金额文本", "金额类型", "金额大写", "摘要", "用途", "业务种类", "业务产品种类",
            "交易流水号", "时间戳", "交易日期", "支付方式", "当前状态",
            "收款方备注", "记账网点", "记账柜员", "验证码", "备注",
        ],
        "types": {
            "交易金额": "amount",
            "金额大写": "text",
            "交易日期": "date",
            "时间戳": "datetime",
            "付款方账号": "bank_account",
            "收款方账号": "bank_account",
            "交易流水号": "identifier",
        },
        "aliases": {
            "电子回单号": "电子回单号码",
            "回单编号": "电子回单号码",
            "回单号码": "电子回单号码",
            "付款人户名": "付款方户名",
            "付款人名称": "付款方户名",
            "付款方名称": "付款方户名",
            "付款人账号": "付款方账号",
            "付款账号": "付款方账号",
            "付款人开户银行": "付款方开户行",
            "付款方开户银行": "付款方开户行",
            "收款人户名": "收款方户名",
            "收款人名称": "收款方户名",
            "收款方名称": "收款方户名",
            "收款人账号": "收款方账号",
            "收款账号": "收款方账号",
            "收款人开户银行": "收款方开户行",
            "收款方开户银行": "收款方开户行",
            "金额": "交易金额",
            "付款金额": "交易金额",
            "转账金额": "交易金额",
            "大写金额": "金额大写",
            "金额大写": "金额大写",
            "流水号": "交易流水号",
            "交易流水": "交易流水号",
            "转账单号": "交易流水号",
            "转帐单号": "交易流水号",
            "交易单号": "交易流水号",
            "支付单号": "交易流水号",
            "交易时间": "时间戳",
            "转账时间": "时间戳",
            "转帐时间": "时间戳",
            "支付时间": "时间戳",
            "日期": "交易日期",
            "支付日期": "交易日期",
            "记账日期": "交易日期",
            "交易状态": "当前状态",
            "状态": "当前状态",
            "附言": "备注",
            "备注信息": "备注",
        },
    },
    "invoice": {
        "name": "增值税发票",
        "required": ["发票号码", "开票日期", "价税合计"],
        "recommended": ["购买方名称", "销售方名称"],
        "order": [
            "发票代码", "发票号码", "开票日期", "购买方名称", "购买方纳税人识别号",
            "销售方名称", "销售方纳税人识别号", "金额合计", "税额", "价税合计",
            "价税合计小写", "价税合计大写", "备注",
        ],
        "types": {
            "发票代码": "identifier",
            "发票号码": "identifier",
            "开票日期": "date",
            "金额合计": "amount",
            "税额": "amount",
            "价税合计": "amount",
            "价税合计小写": "amount",
        },
        "aliases": {
            "电子发票号码": "发票号码",
            "电子发票代码": "发票代码",
            "购方名称": "购买方名称",
            "销方名称": "销售方名称",
            "购买方税号": "购买方纳税人识别号",
            "销售方税号": "销售方纳税人识别号",
            "合计金额": "金额合计",
            "小写金额": "价税合计小写",
            "大写金额": "价税合计大写",
        },
    },
    "receipt": {
        "name": "收据",
        "required": ["金额小写"],
        "recommended": ["日期", "付款单位", "收款单位"],
        "order": [
            "收据编号", "日期", "付款单位", "收款单位", "项目", "摘要",
            "金额小写", "原始金额文本", "金额类型", "金额大写", "经办人", "备注",
        ],
        "types": {
            "日期": "date",
            "金额小写": "amount",
        },
        "aliases": {
            "收据号码": "收据编号",
            "收款事由": "摘要",
            "金额": "金额小写",
            "交易金额": "金额小写",
            "实付金额": "金额小写",
            "支付金额": "金额小写",
            "订单金额": "金额小写",
            "小写金额": "金额小写",
            "大写金额": "金额大写",
            "支付日期": "日期",
            "交易日期": "日期",
        },
    },
    "transaction_list": {
        "name": "账单流水",
        "required": ["交易金额"],
        "recommended": ["交易类型", "交易对象", "交易日期"],
        "order": [
            "交易类型", "交易对象", "交易金额", "原始金额文本", "金额类型", "交易日期", "时间戳",
            "原始时间文本", "日期推断来源", "原始文本", "备注",
        ],
        "types": {
            "交易金额": "amount",
            "交易日期": "date",
            "时间戳": "datetime",
        },
        "aliases": {
            "标题": "交易类型",
            "名称": "交易类型",
            "商户": "交易对象",
            "商户名称": "交易对象",
            "摘要": "交易对象",
            "金额": "交易金额",
            "日期": "交易日期",
            "交易时间": "时间戳",
            "时间": "时间戳",
        },
    },
    "subscription_record": {
        "name": "订购记录",
        "required": ["产品名称"],
        "recommended": ["订购时间", "有效期开始", "有效期结束", "月费"],
        "order": [
            "产品名称", "订购状态", "订购时间", "有效期开始", "有效期结束",
            "退订时间", "月费", "原始金额文本", "金额类型", "计费周期", "原始文本", "备注",
        ],
        "types": {
            "订购时间": "date",
            "有效期开始": "date",
            "有效期结束": "date",
            "退订时间": "date",
            "月费": "amount",
        },
        "aliases": {
            "套餐名称": "产品名称",
            "商品名称": "产品名称",
            "状态": "订购状态",
            "有效期限开始": "有效期开始",
            "有效期限结束": "有效期结束",
            "有效期至": "有效期结束",
            "金额": "月费",
            "费用": "月费",
            "月租": "月费",
        },
    },
}


def schema_for(doc_type: str) -> dict:
    return DOCUMENT_SCHEMAS.get(doc_type or "", {})


def document_type_label(doc_type: str) -> str:
    schema = schema_for(doc_type)
    if schema.get("name"):
        return schema["name"]
    return {
        "unknown": "其他待确认",
        "general": "其他待确认",
    }.get(doc_type or "", doc_type or "其他待确认")


def canonical_field_name(field_name: str, doc_type: str = "") -> str:
    name = (field_name or "").strip()
    if not name:
        return name

    suffix = ""
    suffix_match = re.match(r"^(.*?)([_-]\d+)$", name)
    if suffix_match:
        name = suffix_match.group(1)
        suffix = suffix_match.group(2)

    schema = schema_for(doc_type)
    aliases = schema.get("aliases", {})
    if name in aliases:
        return f"{aliases[name]}{suffix}"

    compact = re.sub(r"\s+", "", name)
    for alias, canonical in aliases.items():
        if re.sub(r"\s+", "", alias) == compact:
            return f"{canonical}{suffix}"

    return f"{name}{suffix}"


def ordered_columns_for(doc_type: str, all_fields: set[str], custom_columns: Optional[list[str]] = None) -> list[str]:
    schema = schema_for(doc_type)

    if custom_columns:
        from app.utils.ocr_preprocessor import normalize_single_field_name

        columns = []
        for column in custom_columns:
            normalized = canonical_field_name(normalize_single_field_name(column), doc_type)
            if (normalized in all_fields or normalized in schema.get("order", [])) and normalized not in columns:
                columns.append(normalized)
        if schema:
            columns.extend([field for field in schema.get("order", []) if field not in columns])
        else:
            columns.extend(sorted(all_fields - set(columns)))
        return columns

    order = schema.get("order", [])
    if order:
        return list(order)

    columns = [field for field in order if field in all_fields]
    columns.extend(sorted(all_fields - set(columns)))
    return columns


def field_type(field_name: str, doc_type: str = "") -> str:
    return schema_for(doc_type).get("types", {}).get(field_name, "text")


def validate_schema_fields(fields: dict, doc_type: str = "") -> dict:
    schema = schema_for(doc_type)
    if not schema:
        return {"missing_required": [], "missing_recommended": [], "type_errors": [], "needs_review": []}

    present = {
        key for key, value in fields.items()
        if _field_has_value(value)
    }
    missing_required = [field for field in schema.get("required", []) if field not in present]
    missing_recommended = [field for field in schema.get("recommended", []) if field not in present]

    type_errors = []
    for field_name, field_data in fields.items():
        expected_type = field_type(field_name, doc_type)
        if expected_type == "text":
            continue
        value = _field_value(field_data)
        if value is None or str(value).strip() == "":
            continue
        if not _matches_type(str(value).strip(), expected_type):
            type_errors.append(field_name)

    return {
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "type_errors": type_errors,
        "needs_review": sorted(set(missing_required + missing_recommended + type_errors)),
    }


def _field_has_value(field_data: Any) -> bool:
    value = _field_value(field_data)
    return value is not None and str(value).strip() != ""


def _field_value(field_data: Any) -> Any:
    if isinstance(field_data, dict) and "value" in field_data:
        return field_data.get("value")
    return field_data


def _matches_type(value: str, expected_type: str) -> bool:
    if expected_type == "amount":
        cleaned = value.replace("¥", "").replace("￥", "").replace("元", "").replace(",", "").strip()
        return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned))
    if expected_type == "date":
        return bool(re.search(r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}", value))
    if expected_type == "datetime":
        return bool(re.search(r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}", value) or re.search(r"\d{1,2}[:：]\d{1,2}", value))
    if expected_type == "bank_account":
        digits = re.sub(r"\D", "", value)
        return 8 <= len(digits) <= 30
    if expected_type == "identifier":
        compact = re.sub(r"\s", "", value)
        return len(compact) >= 4
    return True
