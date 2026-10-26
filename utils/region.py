"""
地区档解析（主线④：职务等级×地区标准交叉计算）
- 目的地（自由文本城市名）→ 地区档 tier1 / tier2 / tier3
- 内置默认映射；财务可通过 sys_config（key=region_tier_map_json）覆盖
- 未匹配的目的地按 tier3（其他地区）处理
"""
import json

TIER_NAMES = {
    'tier1': '一类地区（直辖市）',
    'tier2': '二类地区（省会/计划单列市）',
    'tier3': '三类地区（其他）',
}

# 默认映射（关键词包含匹配，按 tier1 → tier2 顺序优先命中）
DEFAULT_REGION_MAP = {
    'tier1': ['北京', '上海', '天津', '重庆'],
    'tier2': [
        '广州', '深圳', '杭州', '南京', '武汉', '成都', '西安', '长沙', '郑州',
        '济南', '沈阳', '哈尔滨', '长春', '石家庄', '太原', '合肥', '南昌',
        '福州', '昆明', '贵阳', '兰州', '西宁', '海口', '南宁', '呼和浩特',
        '银川', '乌鲁木齐', '拉萨', '南京', '青岛', '大连', '宁波', '厦门',
    ],
}


def _custom_map() -> dict:
    """读取 sys_config 覆盖映射（{tier: [关键词...]}），无则空"""
    try:
        from models.models import SysConfig
        cfg = SysConfig.query.filter_by(config_key='region_tier_map_json').first()
        if cfg:
            data = json.loads(cfg.config_value)
            if isinstance(data, dict):
                return {str(k): [str(x) for x in v if x] for k, v in data.items() if isinstance(v, list)}
    except Exception:
        pass
    return {}


def resolve_region_tier(destination: str) -> str:
    """目的地 → 地区档；自定义映射按档覆盖内置默认，未命中 → tier3"""
    if not destination:
        return 'tier3'

    custom = _custom_map()
    for tier in ('tier1', 'tier2'):
        keywords = custom.get(tier) or DEFAULT_REGION_MAP.get(tier, [])
        for kw in keywords:
            if kw and kw in destination:
                return tier
    return 'tier3'


def tier_display(tier) -> str:
    """档位显示名（NULL → 通用）"""
    if not tier:
        return '通用（不限地区）'
    return TIER_NAMES.get(tier, tier)
