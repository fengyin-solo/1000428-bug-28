"""鼓风机组业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "blower"
REQUIRED_FIELDS = ["机组编号", "机组型号", "额定风量"]
STATUS_ORDER = ["待启用", "运行中", "维护中", "已停用"]
ACTION_RULES = {"启用机组": "运行中", "登记维护": "维护中", "停用机组": "已停用"}
NEGATIVE_ACTIONS = ["停用机组"]


def _as_number(value: Any) -> float | None:
    """把能解析成数字的字段值转成 float，解析不了就当作没有数据。"""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


class BlowerService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        model: str | None = None,
        airflow: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("机组编号", ""))]
        if model:
            rows = [row for row in rows if model in str(row.get("机组型号", ""))]
        if airflow:
            rows = [row for row in rows if airflow in str(row.get("额定风量", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summary(self) -> list[dict[str, Any]]:
        """统计卡片口径：与列表共用同一份数据，保证卡片数字和列表对得上。"""
        rows = store.rows(MODULE)
        running = [row for row in rows if row.get("status") == "运行中"]
        maintaining = [row for row in rows if row.get("status") == "维护中"]
        supply = sum(
            value for row in running if (value := _as_number(row.get("额定风量"))) is not None
        )
        if supply == int(supply):
            supply = int(supply)
        return [
            {"label": "运行机组", "value": len(running)},
            {"label": "维护中机组", "value": len(maintaining)},
            {"label": "今日供风量", "value": supply},
        ]

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        errors: list[str] = []
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            errors.append(f"缺少必填字段：{'、'.join(missing)}")
            return None, errors
        code = str(values.get("机组编号")).strip()
        rows = store.rows(MODULE)
        if any(str(row.get("机组编号", "")).strip() == code for row in rows):
            errors.append(f"机组编号 {code} 已登记，请勿重复提交；如需变更请对原记录执行动作")
            return None, errors
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

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
            return None, f"机组已处于「{target}」，本次未重复{action}"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"鼓风机组已{action}"
