"""防雷接地接口：装置台账、按复测周期排程的复测队列、复测登记、浪涌模块更换与周期重排。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.lightningprot import (
    RESISTANCE_LIMIT,
    STATUS_FAIL,
    STATUS_PASS,
    LightningprotService,
)

router = APIRouter(prefix="/api/lightningprot", tags=["防雷接地"])

service = LightningprotService()

LIST_FIELDS = ["装置编号", "所属站点", "接地电阻", "防雷模块", "浪涌保护", "上次测试", "测试人员", "下次复测日", "装置状态"]
STATUSES = [STATUS_PASS, STATUS_FAIL]


@router.get("/retest-queue")
def retest_queue(site: str | None = Query(default=None, description="按所属站点过滤")) -> dict[str, Any]:
    """复测队列：按站点列出下次复测日，超标单独成区，超期/临期依次靠前。"""
    return service.retest_queue(site=site)


@router.get("/retest-settings")
def get_retest_settings() -> dict[str, Any]:
    """读取当前复测周期、临期提醒窗口与接地电阻合格线。"""
    return service.get_settings()


@router.put("/retest-settings", response_model=ActionResult)
def update_retest_settings(payload: EntryPayload) -> ActionResult:
    """调整复测周期后，已有装置的下次复测日按新周期逐台重排。"""
    settings_view, message = service.reschedule(payload.values.get("cycle_months"))
    if settings_view is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=settings_view)


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按装置编号检索"),
    site: str | None = Query(default=None, description="按所属站点检索"),
    status: str | None = Query(default=None, description="合格、电阻超标"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """装置台账：状态与待处理标记均由测试记录推导，和复测队列同一口径。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, site=site, status_filter=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出防雷装置台账：与复测队列结论同源，不会导出两个样。"""
    items = service.all_entries()
    return {
        "module": "lightningprot",
        "total": len(items),
        "resistance_limit": RESISTANCE_LIMIT,
        "items": [
            {key: row.get(key) for key in LIST_FIELDS + ["cycle_months", "status", "pending", "abnormal"]}
            for row in items
        ],
    }


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单台防雷装置明细与历次测试记录；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"防雷装置 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一台防雷装置，初次接地电阻读数同时生成首条测试记录与下次复测日。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"校验未通过：{'、'.join(missing)}")
    return ActionResult(ok=True, message="防雷装置已登记，已按复测周期排入日程", entry=entry)


@router.post("/{entry_id}/retest", response_model=ActionResult)
def register_retest(entry_id: int, payload: EntryPayload) -> ActionResult:
    """登记一次复测结果：合格则按周期重排并退出复测队列，仍超标则留队整改。"""
    entry, message = service.register_retest(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/spd-replacement", response_model=ActionResult)
def replace_spd(entry_id: int, payload: EntryPayload) -> ActionResult:
    """登记浪涌保护模块更换及更换后测试：测试人员、测试日期随更换记录同步更新。"""
    entry, message = service.replace_spd(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
