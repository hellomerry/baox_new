"""
报销单号生成（T4）
L5 决策：单号 4 位 → 5 位（99999/天/项目）
规则: B<YYYYMMDD>-<project_code>-<5位序号>
"""
import re
from datetime import datetime
from models.models import ExpenseBill


def generate_bill_no(project_code: str) -> str:
    """生成单号"""
    today = datetime.now().strftime('%Y%m%d')
    prefix = f'B{today}-{project_code}-'

    # 查今天该项目的最大序号
    pattern = f'{prefix}%'
    last_bill = ExpenseBill.query.filter(
        ExpenseBill.bill_no.like(pattern)
    ).order_by(ExpenseBill.bill_no.desc()).first()

    if last_bill:
        match = re.search(r'-(\d{5})$', last_bill.bill_no)
        next_seq = int(match.group(1)) + 1 if match else 1
    else:
        next_seq = 1

    if next_seq > 99999:
        raise ValueError(f'单号序号超过 99999，请检查项目 {project_code} 当日报销量')

    return f'{prefix}{next_seq:05d}'


def amount_to_capital(amount: float) -> str:
    """金额转中文大写（简化版）"""
    units = ['', '拾', '佰', '仟']
    big_units = ['', '万', '亿', '兆']
    digits = '零壹贰叁肆伍陆柒捌玖'

    if amount == 0:
        return '零元整'

    int_part = int(amount)
    dec_part = int(round((amount - int_part) * 100))

    if int_part == 0:
        result = '零元'
    else:
        s = ''
        s_str = str(int_part)
        n = len(s_str)
        for i, c in enumerate(s_str):
            digit = int(c)
            unit = units[(n - 1 - i) % 4]
            big_unit = big_units[(n - 1 - i) // 4]
            if digit != 0:
                s += digits[digit] + unit
            else:
                if s and not s.endswith('零'):
                    s += '零'
            if unit == '' and big_unit:
                s = s.rstrip('零') + big_unit
        result = s + '元'

    if dec_part == 0:
        result += '整'
    else:
        jiao = dec_part // 10
        fen = dec_part % 10
        if jiao:
            result += digits[jiao] + '角'
        if fen:
            result += digits[fen] + '分'

    return result
