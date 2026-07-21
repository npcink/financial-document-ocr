import re
from typing import Tuple

RULES = {
    "invoice": [
        (r"发票号码", 1.5),
        (r"发票代码", 1.5),
        (r"增值税", 1.2),
        (r"价税合计", 1.2),
        (r"购买方名称", 1.0),
        (r"销售方名称", 1.0),
        (r"纳税人识别号", 1.0),
        (r"税额", 0.8),
    ],
    "receipt": [
        (r"收据", 1.5),
        (r"收款", 1.2),
        (r"今收到", 1.5),
        (r"付款单位", 1.0),
        (r"收款单位", 1.0),
    ],
    "bank_receipt": [
        (r"银行", 1.0),
        (r"账号", 1.2),
        (r"交易流水", 1.5),
        (r"转账", 1.0),
        (r"开户行", 1.5),
        (r"付款方账号", 1.2),
        (r"收款方账号", 1.2),
        (r"电子回单", 2.0),
        (r"网银", 1.5),
    ],
    "transaction_list": [
        (r"\d{1,2}[-/]\d{1,2}\s+\d{1,2}[:：]\d{1,2}", 2.0),
        (r"[+-]?\d+(?:\.\d{2})", 1.2),
        (r"充值|消费|付款|退款|转入|转出", 1.2),
    ],
    "subscription_record": [
        (r"订购时间", 2.0),
        (r"有效期限", 2.0),
        (r"退订时间|退订|已退订|即将失效", 1.2),
        (r"元[／/]月|元/月|月包|套餐|会员", 1.2),
    ],
}


def pre_classify(text: str, threshold: float = 0.7) -> Tuple[str, float]:
    best_type = "unknown"
    best_score = 0.0

    for doc_type, patterns in RULES.items():
        if not patterns:
            continue

        weighted_sum = 0.0
        max_possible = sum(w for _, w in patterns)
        for pat, weight in patterns:
            if re.search(pat, text):
                weighted_sum += weight

        score = weighted_sum / max_possible if max_possible > 0 else 0.0
        if score > best_score:
            best_score = score
            best_type = doc_type

    if best_score >= threshold:
        return best_type, best_score

    return "unknown", 0.0
