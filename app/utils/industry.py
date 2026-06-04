"""
申万行业分类映射 —— 处理2021年底行业分类改版（28→31个一级行业）。

新旧两套映射，回测时按时间自动切换。
"""

from datetime import date
from functools import lru_cache

from app.utils.calendar import SHENWAN_RECLASSIFICATION_DATE

# ============================================================================
# 申万一级行业分类
# ============================================================================

# 旧版（2021年底前）：28个一级行业
SHENWAN_OLD_28 = {
    "801010": "农林牧渔",
    "801020": "采掘",
    "801030": "化工",
    "801040": "钢铁",
    "801050": "有色金属",
    "801080": "电子",
    "801110": "家用电器",
    "801120": "食品饮料",
    "801130": "纺织服装",
    "801140": "轻工制造",
    "801150": "医药生物",
    "801160": "公用事业",
    "801170": "交通运输",
    "801180": "房地产",
    "801200": "商业贸易",
    "801210": "休闲服务",
    "801230": "综合",
    "801710": "建筑材料",
    "801720": "建筑装饰",
    "801730": "电气设备",
    "801740": "国防军工",
    "801750": "计算机",
    "801760": "传媒",
    "801770": "通信",
    "801780": "银行",
    "801790": "非银金融",
    "801880": "汽车",
    "801890": "机械设备",
}

# 新版（2022年起）：31个一级行业
SHENWAN_NEW_31 = {
    "801010": "农林牧渔",
    "801020": "基础化工",       # 原"化工"拆分+重命名
    "801030": "石油石化",       # 新增（从采掘+化工拆分）
    "801040": "钢铁",
    "801050": "有色金属",
    "801080": "电子",
    "801110": "家用电器",
    "801120": "食品饮料",
    "801130": "纺织服饰",       # 原"纺织服装"重命名
    "801140": "轻工制造",
    "801150": "医药生物",
    "801160": "公用事业",
    "801170": "交通运输",
    "801180": "房地产",
    "801200": "商贸零售",       # 原"商业贸易"重命名
    "801210": "社会服务",       # 原"休闲服务"重命名+调整
    "801230": "综合",
    "801710": "建筑材料",
    "801720": "建筑装饰",
    "801730": "电力设备",       # 原"电气设备"重命名
    "801740": "国防军工",
    "801750": "计算机",
    "801760": "传媒",
    "801770": "通信",
    "801780": "银行",
    "801790": "非银金融",
    "801880": "汽车",
    "801890": "机械设备",
    # 2022年新增3个一级行业：
    "801960": "环保",           # 新增（从公用事业拆分）
    "801970": "美容护理",       # 新增（从化工+医药拆分）
    "801980": "煤炭",           # 新增（从采掘拆分）
}

# 旧→新映射（用于旧数据转换）
OLD_TO_NEW_MAPPING = {
    "采掘": ["煤炭", "石油石化"],
    "化工": ["基础化工", "石油石化", "美容护理"],
    "商业贸易": ["商贸零售"],
    "休闲服务": ["社会服务"],
    "电气设备": ["电力设备"],
    "纺织服装": ["纺织服饰"],
    "公用事业": ["公用事业", "环保"],
}


# ============================================================================
# 行业分类获取
# ============================================================================

def get_industry_classification(d: date) -> dict[str, str]:
    """
    根据日期返回正确的行业分类标准。

    2022-01-01 之前：28个一级行业（旧版）
    2022-01-01 起  ：31个一级行业（新版）
    """
    if d < SHENWAN_RECLASSIFICATION_DATE:
        return SHENWAN_OLD_28
    return SHENWAN_NEW_31


def get_industry_name(code: str, d: date) -> str | None:
    """根据行业代码和日期返回行业名称"""
    classification = get_industry_classification(d)
    return classification.get(code)


def get_all_industry_codes(d: date) -> list[str]:
    """获取某日期的所有行业代码"""
    return list(get_industry_classification(d).keys())


def get_industry_count(d: date) -> int:
    """获取某日期的行业数量"""
    return len(get_industry_classification(d))


# ============================================================================
# 跨版本兼容的行业映射
# ============================================================================

@lru_cache(maxsize=256)
def normalize_industry(stock_industry_code: str, stock_date: date, target_date: date) -> str:
    """
    将某只股票在某日期的行业分类，映射到目标日期的行业分类标准。

    用于解决：一只股票2021年是"化工"行业，2022年变成了"基础化工"，
    在回测中跨2022年前后需要统一处理。

    Args:
        stock_industry_code: 股票在某日期的行业代码
        stock_date: 该行业分类对应的日期
        target_date: 需要映射到的目标日期

    Returns:
        目标日期标准下的行业代码
    """
    # 如果两边是同一种分类标准，直接返回
    if (stock_date < SHENWAN_RECLASSIFICATION_DATE) == \
       (target_date < SHENWAN_RECLASSIFICATION_DATE):
        return stock_industry_code

    # 跨版本映射：旧→新
    if stock_date < SHENWAN_RECLASSIFICATION_DATE:
        old_name = SHENWAN_OLD_28.get(stock_industry_code, "")
        if old_name in OLD_TO_NEW_MAPPING:
            # 取第一个映射（近似的，精确映射需要个股级别数据）
            new_names = OLD_TO_NEW_MAPPING[old_name]
            # 反向查找新代码
            for code, name in SHENWAN_NEW_31.items():
                if name == new_names[0]:
                    return code
        return stock_industry_code  # 无法映射的保持原样

    # 跨版本映射：新→旧（较少用到）
    new_name = SHENWAN_NEW_31.get(stock_industry_code, "")
    for old_name, mapped_new in OLD_TO_NEW_MAPPING.items():
        if new_name in mapped_new:
            for code, name in SHENWAN_OLD_28.items():
                if name == old_name:
                    return code
    return stock_industry_code
