"""鼓风机组接口：维护鼓风机组，覆盖启用机组、登记维护、停用机组等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.blower import (
    LIST_FIELDS,
    STATUS_ORDER,
    BlowerService,
)

router = APIRouter(prefix="/api/blower", tags=["鼓风机组"])

service = BlowerService()

STATUSES = STATUS_ORDER


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按机组编号检索"),
    status: str | None = Query(default=None, description="待启用、运行中、维护中、已停用"),
    机组编号: str | None = Query(default=None, description="按机组编号模糊检索"),
    机组型号: str | None = Query(default=None, description="按机组型号模糊检索"),
    额定风量: str | None = Query(default=None, description="按额定风量模糊检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按机组编号、型号、额定风量与状态过滤鼓风机组列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"机组状态只支持：{'、'.join(STATUSES)}")
    filters = {
        "机组编号": 机组编号 or "",
        "机组型号": 机组型号 or "",
        "额定风量": 额定风量 or "",
    }
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        filters=filters,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, Any]:
    """统计卡片：运行机组、维护中机组数量与今日供风量，口径与列表状态筛选一致。"""
    return service.stats()


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条鼓风机组明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"鼓风机组 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条鼓风机组，缺字段或机组编号重复时说明原因而不是静默丢弃。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="鼓风机组已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条鼓风机组执行启用机组、登记维护、停用机组；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出鼓风机组清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "blower", "total": total, "items": items}
