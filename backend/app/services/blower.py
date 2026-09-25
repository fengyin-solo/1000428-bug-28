"""鼓风机组业务规则：状态流转、字段校验、筛选口径与统计口径都收在这里。"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

# 只认「数字开头、可带小数点和单位」的填报值，避免从「鼓风机组样例2」这类文本里抠出数字。
_NUMBER_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)")

MODULE = "blower"
REQUIRED_FIELDS = ["机组编号", "机组型号", "额定风量"]
OPTIONAL_FIELDS = ["出口压力", "运行时长", "维护周期", "所属单元"]
LIST_FIELDS = [
    "机组编号",
    "机组型号",
    "额定风量",
    "出口压力",
    "运行时长",
    "维护周期",
    "所属单元",
]
STATUS_ORDER = ["待启用", "运行中", "维护中", "已停用"]
ACTION_RULES = {"启用机组": "运行中", "登记维护": "维护中", "停用机组": "已停用"}
NEGATIVE_ACTIONS = ["停用机组"]

# 列表里「机组状态」列直接展示内部流转状态，保证卡片统计、状态筛选、列表三处口径一致。
FILTER_FIELD_MAP = {
    "机组编号": "机组编号",
    "机组型号": "机组型号",
    "额定风量": "额定风量",
}


def _clean(value: Any) -> str | None:
    """登记时统一清洗：空白串视为未填，列表里以 null 呈现并走明确空态。"""
    text = str(value or "").strip()
    return text or None


def _to_number(value: Any) -> float | None:
    """把「1200m³/h」这类带单位的填报值尽量解析成数字，解析不出来就当未填。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = _NUMBER_RE.match(text)
    if not match:
        return None
    return float(match.group(1))


def serialize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """对外输出结构：补齐全部展示列（缺的给 null），机组状态以内部 status 为准。"""
    result: dict[str, Any] = {"id": entry["id"]}
    for field in LIST_FIELDS:
        result[field] = entry.get(field)
    result["机组状态"] = entry.get("status")
    result["status"] = entry.get("status")
    result["pending"] = entry.get("pending", False)
    result["abnormal"] = entry.get("abnormal", False)
    return result


class BlowerService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        filters: dict[str, str] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        keyword = (keyword or "").strip()
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("机组编号", ""))]
        status = (status or "").strip()
        if status:
            rows = [row for row in rows if row.get("status") == status]
        for field, term in (filters or {}).items():
            term = (term or "").strip()
            if not term:
                continue
            column = FILTER_FIELD_MAP.get(field, field)
            rows = [row for row in rows if term in str(row.get(column) or "")]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [serialize_entry(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return serialize_entry(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}，请补齐后重新提交"
        code = str(values.get("机组编号")).strip()
        if any(str(row.get("机组编号") or "").strip() == code for row in store.rows(MODULE)):
            return None, f"机组编号 {code} 已登记，重复提交会产生重复台账，请勿重复登记"
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            entry[field] = _clean(values.get(field))
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return serialize_entry(entry), ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"鼓风机组 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于鼓风机组可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if entry.get("status") == target:
            # 同一机组重复点「登记维护」等动作时幂等处理，不再产生重复记录/重复反馈。
            return serialize_entry(entry), f"鼓风机组已处于{target}状态，无需重复{action}"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return serialize_entry(entry), f"鼓风机组已{action}"

    def stats(self) -> dict[str, int | float | None]:
        """统计卡片口径：运行/维护中按内部 status 计数，与列表状态筛选结果一致。

        今日供风量取运行中机组额定风量之和；所有运行机组都没填可解析的额定风量时给 None，
        由前端展示「暂无数据」空态，而不是用 0 冒充。
        """
        rows = store.rows(MODULE)
        running = [row for row in rows if row.get("status") == "运行中"]
        maintaining = [row for row in rows if row.get("status") == "维护中"]
        airflow_values = [value for value in (_to_number(row.get("额定风量")) for row in running) if value is not None]
        today_airflow: float | None = round(sum(airflow_values), 2) if airflow_values else None
        return {
            "运行机组": len(running),
            "维护中机组": len(maintaining),
            "今日供风量": today_airflow,
        }
