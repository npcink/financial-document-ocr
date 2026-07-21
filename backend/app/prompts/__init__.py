"""LLM 提示词模板管理"""

from typing import List

TEMPLATES = {
    "invoice": {
        "name": "增值税发票",
        "description": "增值税普通发票/专用发票",
        "default_fields": [
            "发票号码", "发票代码", "开票日期",
            "购买方名称", "购买方纳税人识别号",
            "销售方名称", "销售方纳税人识别号",
            "金额合计", "税额", "价税合计",
            "货物或应税劳务名称", "规格型号", "单位", "数量", "单价",
        ],
    },
    "receipt": {
        "name": "收据",
        "description": "收款收据",
        "default_fields": [
            "收据编号", "日期",
            "收款单位", "付款单位",
            "金额大写", "金额小写",
            "收款事由", "经办人",
        ],
    },
    "bank_receipt": {
        "name": "银行回单",
        "description": "银行交易回执",
        "default_fields": [
            "银行名称", "交易日期", "交易时间",
            "付款方账号", "付款方名称",
            "收款方账号", "收款方名称",
            "交易金额", "交易类型", "交易流水号",
            "摘要", "余额",
        ],
    },
    "transaction_list": {
        "name": "账单流水",
        "description": "手机账单/钱包流水列表",
        "default_fields": [
            "交易类型", "交易对象", "交易金额", "交易日期", "时间戳",
            "原始时间文本", "日期推断来源",
        ],
    },
    "subscription_record": {
        "name": "订购记录",
        "description": "套餐/会员订购记录",
        "default_fields": [
            "产品名称", "订购状态", "订购时间", "有效期开始", "有效期结束",
            "退订时间", "月费", "计费周期",
        ],
    },
    "general": {
        "name": "通用票据",
        "description": "其他类型票据",
        "default_fields": [
            "日期", "金额", "主体名称", "编号", "摘要",
        ],
    },
}


def get_default_fields(template_type: str) -> List[str]:
    """获取指定模板类型的默认字段列表"""
    template = TEMPLATES.get(template_type, TEMPLATES["general"])
    return list(template["default_fields"])


def get_prompt(
    document_type: str,
    template_type: str,
    requirement: str,
    ocr_text: str,
) -> str:
    """根据票据类型、模板类型和用户需求构造 LLM 提取 Prompt"""
    template = TEMPLATES.get(template_type, TEMPLATES["general"])
    default_fields = template["default_fields"]

    if requirement.strip():
        fields_desc = requirement.strip()
    else:
        fields_desc = "、".join(default_fields)

    truncated = ocr_text[:8000] if len(ocr_text) > 8000 else ocr_text

    return f"""你是一个专业的票据信息提取助手。请从以下 OCR 识别的文档内容中提取关键字段信息。

文档类型: {template.get("name", "通用票据")}
需要提取的字段: {fields_desc}

注意：OCR 文本已经过预处理（去除噪声、规范化字段名称、修复常见识别错误），但仍可能存在少量误差。

OCR 识别文本:
---
{truncated}
---

请输出 JSON，格式如下:

```json
{{
  "fields": {{
    "字段名1": {{"value": "提取的值", "confidence": 0.95}},
    "字段名2": {{"value": "提取的值", "confidence": 0.88}}
  }},
  "confidence": 0.92
}}
```

    要求:
1. 每个字段需包含 value (提取的值) 和 confidence (置信度 0-1)
2. confidence 表示你认为该字段提取准确的可信度
3. 如果某个字段无法从文本中找到，value 设为空字符串，confidence 为 0
4. 金额字段请保留数字和小数点格式，不要添加其他文字
5. 日期字段统一为 YYYY-MM-DD 格式
6. 整体 confidence 是所有字段置信度的平均值
7. 字段名用纯名称，如"编号"不是"提取编号"
8. 只输出 JSON，不要其他内容。"""
