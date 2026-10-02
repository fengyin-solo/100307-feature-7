"""防雷接地接口：装置台账、复测队列、复测登记、浪涌模块更换与复测周期配置。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.lightningprot import LightningprotService

router = APIRouter(prefix="/api/lightningprot", tags=["防雷接地"])

service = LightningprotService()

LIST_FIELDS = ["装置编号", "所属站点", "接地电阻", "防雷模块", "浪涌保护", "上次测试", "测试人员", "装置状态"]
STATUSES = ["合格", "电阻超标", "模块劣化", "已更换"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按装置编号检索"),
    site: str | None = Query(default=None, description="按所属站点检索"),
    status: str | None = Query(default=None, description="合格、电阻超标、模块劣化、已更换"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按装置编号、站点与状态过滤防雷接地列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, site=site, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/retest-queue")
def retest_queue(
    site: str | None = Query(default=None, description="按站点过滤"),
    state: str | None = Query(default=None, description="电阻超标、已超期、即将到期、模块劣化、已安排"),
) -> dict[str, Any]:
    """复测队列：按站点分组列出下次复测日，超期/超标优先，附统计口径与当前周期配置。"""
    return service.queue_overview(site=site, state=state)


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    """读取复测周期、到期预警天数与接地电阻限值。"""
    return service.get_settings()


@router.put("/settings", response_model=ActionResult)
def update_settings(payload: EntryPayload) -> ActionResult:
    """调整复测周期；保存后已有装置的下次复测日全部按新口径重排。"""
    settings, message = service.update_settings(payload.values)
    if settings is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="复测周期已调整，全部装置的下次复测日已重排", entry=settings)


@router.post("/{entry_id}/tests", response_model=ActionResult)
def record_test(entry_id: int, payload: EntryPayload) -> ActionResult:
    """登记一次接地电阻复测；合格后装置退出复测队列并顺延下次复测日。"""
    values = dict(payload.values)
    values.setdefault("remark", payload.remark)
    entry, message = service.record_test(entry_id, values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/replace-spd", response_model=ActionResult)
def replace_spd(entry_id: int, payload: EntryPayload) -> ActionResult:
    """更换浪涌保护模块并登记更换后测试；测试人员、测试日期随更换同步更新。"""
    values = dict(payload.values)
    values.setdefault("reason", payload.remark or "")
    entry, message = service.replace_spd(entry_id, values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出防雷接地清单：返回当前全量数据（含下次复测日与队列状态）。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "lightningprot", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条防雷装置明细（含测试/更换历史）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"防雷装置 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条防雷装置，缺字段时说明原因而不是静默丢弃。"""
    values = dict(payload.values)
    values.setdefault("remark", payload.remark)
    entry, missing = service.create_entry(values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="防雷装置已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """兼容旧动作入口（记录劣化）；登记超标、安排更换请改用复测登记与模块更换。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
