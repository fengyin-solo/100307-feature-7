"""防雷接地业务规则：装置台账、接地电阻测试记录与按复测周期排程的复测队列。

台账与复测队列共用一套派生口径（_sync_entry / queue_item）：
- 装置状态、待处理标记只由「最近一次测试结果 + 下次复测日」推导，不存在第二份结论；
- 复测登记、浪涌保护模块更换都是在测试记录上追加一条，再重排下次复测日；
- 复测周期调整后，按新周期从各装置上次测试日逐台重排。
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "lightningprot"

REQUIRED_FIELDS = ["装置编号", "所属站点", "接地电阻"]

# 合格退出队列后，到期前多少天进入「临近复测」提醒
WARN_DAYS = 30
# 通信站工作接地电阻合格线（欧姆）：测试读数大于该值即判定电阻超标
RESISTANCE_LIMIT = 10.0
DEFAULT_CYCLE_MONTHS = 12
MIN_CYCLE_MONTHS = 1
MAX_CYCLE_MONTHS = 60

# 台账装置状态：只保留「合格 / 电阻超标」两态，由最近一次测试推导
STATUS_PASS = "合格"
STATUS_FAIL = "电阻超标"

SOURCE_INIT = "初次登记"
SOURCE_RETEST = "复测"
SOURCE_REPLACE = "浪涌模块更换"

# 复测队列分层：电阻超标单独成区并排在最前，超期次之，临期再次
TIER_FAIL = "电阻超标"
TIER_OVERDUE = "已超期"
TIER_DUE_SOON = "临近复测"
TIER_ORDER = [TIER_FAIL, TIER_OVERDUE, TIER_DUE_SOON]
TIER_RANK = {tier: index for index, tier in enumerate(TIER_ORDER)}

# 内存态的全局复测口径：周期可在「周期设置」里调整，调整后逐台重排
settings: dict[str, Any] = {"cycle_months": DEFAULT_CYCLE_MONTHS, "warn_days": WARN_DAYS}


def today() -> date:
    return date.today()


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_resistance(value: Any) -> float | None:
    """接地电阻允许写成 4.2、「4.2Ω」之类的字符串，取不出来视为未读数。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    digits: list[str] = []
    for char in str(value).strip():
        if char.isdigit() or char == ".":
            digits.append(char)
        elif digits:
            break
    if not digits:
        return None
    try:
        return float("".join(digits))
    except ValueError:
        return None


def format_resistance(text: Any) -> str:
    """统一成「填写的数值+Ω」的展示口径：保留 4.0 这类原始精度，只补/不重复单位。"""
    if parse_resistance(text) is None:
        return str(text or "")
    normalized = str(text).strip()
    while normalized.endswith("Ω"):
        normalized = normalized[:-1].strip()
    return f"{normalized}Ω"


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    # 1月31日加一个月落到2月末，而不是溢出到3月
    last_day = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last_day))


def latest_test(entry: dict[str, Any]) -> dict[str, Any] | None:
    records = entry.get("tests") or []
    return records[-1] if records else None


def latest_failed(entry: dict[str, Any]) -> dict[str, Any] | None:
    """最近一次不合格测试——超目标注的就是「哪一次测超的」。"""
    for record in reversed(entry.get("tests") or []):
        if not record.get("passed"):
            return record
    return None


def queue_tier(entry: dict[str, Any], as_of: date | None = None) -> str | None:
    """推导装置当前在复测队列里的分层；不在队列返回 None（复测合格即退出）。"""
    as_of = as_of or today()
    newest = latest_test(entry)
    if newest is None:
        return None
    if not newest.get("passed"):
        return TIER_FAIL
    due = parse_date(entry.get("下次复测日"))
    if due is None:
        return None
    if due < as_of:
        return TIER_OVERDUE
    if due <= as_of + timedelta(days=settings["warn_days"]):
        return TIER_DUE_SOON
    return None


def _sync_entry(entry: dict[str, Any], as_of: date | None = None) -> dict[str, Any]:
    """台账与队列共用的派生口径：只认测试记录和复测排程，不允许各写各的结论。"""
    as_of = as_of or today()
    newest = latest_test(entry)
    if newest is None:
        entry["装置状态"] = STATUS_PASS
    else:
        entry["装置状态"] = STATUS_PASS if newest.get("passed") else STATUS_FAIL
        entry["接地电阻"] = newest.get("resistance_text", entry.get("接地电阻", ""))
        entry["上次测试"] = newest.get("date", "")
        entry["测试人员"] = newest.get("tester", "")
    entry["status"] = entry["装置状态"]
    tier = queue_tier(entry, as_of)
    entry["pending"] = tier is not None
    entry["abnormal"] = entry["装置状态"] == STATUS_FAIL
    entry["_tier"] = tier
    return entry


def _append_test(
    entry: dict[str, Any],
    *,
    test_date: date,
    resistance_text: str,
    tester: str,
    source: str,
    spd: str | None = None,
    module_desc: str | None = None,
) -> dict[str, Any]:
    resistance = parse_resistance(resistance_text)
    passed = resistance is not None and resistance <= RESISTANCE_LIMIT
    record: dict[str, Any] = {
        "date": test_date.isoformat(),
        "resistance": resistance,
        "resistance_text": format_resistance(resistance_text),
        "tester": tester,
        "source": source,
        "passed": passed,
    }
    entry.setdefault("tests", []).append(record)
    if spd is not None:
        entry["浪涌保护"] = spd
    if module_desc is not None:
        entry["防雷模块"] = module_desc
    # 任何一次测试（含模块更换后的测试）都以当日为基准、按当前周期重排
    entry["下次复测日"] = add_months(test_date, int(entry.get("cycle_months", settings["cycle_months"]))).isoformat()
    return record


def _view(entry: dict[str, Any]) -> dict[str, Any]:
    """台账列表/明细行：去掉内部字段，附带最近一次超标测试的编号便于核对。"""
    failed = latest_failed(entry)
    tests = entry.get("tests") or []
    return {
        key: entry.get(key)
        for key in [
            "id", "装置编号", "所属站点", "接地电阻", "防雷模块", "浪涌保护",
            "上次测试", "测试人员", "下次复测日", "cycle_months", "装置状态",
            "status", "pending", "abnormal",
        ]
    } | {
        "超期天数": _overdue_days(entry),
        "超标次数": sum(1 for record in tests if not record.get("passed")),
        "最近超标日期": failed.get("date") if failed else None,
    }


def _overdue_days(entry: dict[str, Any], as_of: date | None = None) -> int | None:
    as_of = as_of or today()
    due = parse_date(entry.get("下次复测日"))
    if due is None or due >= as_of:
        return None
    return (as_of - due).days


class LightningprotService:
    # ---------- 装置台账 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        site: str | None = None,
        status_filter: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [_sync_entry(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("装置编号", ""))]
        if site:
            rows = [row for row in rows if site in str(row.get("所属站点", ""))]
        if status_filter:
            rows = [row for row in rows if row.get("status") == status_filter]
        rows.sort(key=lambda row: str(row.get("装置编号", "")))
        total = len(rows)
        start = max(page - 1, 0) * size
        # _sync_entry 顺带把派生状态写回仓库行，保证概览的 pending/abnormal 也是同口径
        return [_view(row) for row in rows[start:start + size]], total

    def all_entries(self) -> list[dict[str, Any]]:
        return [_sync_entry(row) for row in store.rows(MODULE)]

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        _sync_entry(entry)
        view = _view(entry)
        view["tests"] = entry.get("tests") or []
        return view

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        resistance_text = str(values.get("接地电阻")).strip()
        if parse_resistance(resistance_text) is None:
            return None, ["接地电阻需填写数值，例如 4.2 或 4.2Ω"]
        test_day = parse_date(values.get("测试日期")) or today()
        tester = str(values.get("测试人员") or "").strip()
        if not tester:
            return None, ["测试人员"]
        rows = store.rows(MODULE)
        code = str(values.get("装置编号")).strip()
        if any(str(row.get("装置编号")) == code for row in rows):
            return None, [f"装置编号 {code} 已存在"]

        cycle = self._clean_cycle(values.get("复测周期(月)")) or settings["cycle_months"]
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "装置编号": code,
            "所属站点": str(values.get("所属站点")).strip(),
            "防雷模块": str(values.get("防雷模块") or "").strip(),
            "浪涌保护": str(values.get("浪涌保护") or "").strip(),
            "cycle_months": cycle,
            "tests": [],
        }
        _append_test(
            entry,
            test_date=test_day,
            resistance_text=resistance_text,
            tester=tester,
            source=SOURCE_INIT,
        )
        rows.append(entry)
        _sync_entry(entry)
        return _view(entry), []

    # ---------- 复测队列 ----------
    def queue_item(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        _sync_entry(entry)
        tier = entry.get("_tier")
        if tier is None:
            return None
        newest = latest_test(entry)
        failed = latest_failed(entry)
        tests = entry.get("tests") or []
        return {
            "id": entry["id"],
            "装置编号": entry.get("装置编号"),
            "所属站点": entry.get("所属站点"),
            "防雷模块": entry.get("防雷模块"),
            "浪涌保护": entry.get("浪涌保护"),
            "接地电阻": newest.get("resistance_text") if newest else entry.get("接地电阻"),
            "上次测试": newest.get("date") if newest else None,
            "测试人员": newest.get("tester") if newest else None,
            "下次复测日": entry.get("下次复测日"),
            "装置状态": entry.get("装置状态"),
            "queue_tier": tier,
            "超期天数": _overdue_days(entry),
            # 超标装置单独标注「哪一次测超的」：第几次测、谁测的、读数多少
            "超标测试序号": tests.index(failed) + 1 if failed else None,
            "超标测试次数": len(tests) if failed else None,
            "超标日期": failed.get("date") if failed else None,
            "超标读数": failed.get("resistance_text") if failed else None,
            "超标测试人员": failed.get("tester") if failed else None,
        }

    def retest_queue(self, site: str | None = None) -> dict[str, Any]:
        """按站点分组给出复测队列；站点顺序、站内顺序都按紧迫度（超标 > 超期 > 临期）排。"""
        entries = [store.find(MODULE, int(row["id"])) for row in store.rows(MODULE)]
        entries = [entry for entry in entries if entry is not None]
        items = [self.queue_item(entry) for entry in entries]
        items = [item for item in items if item is not None]
        if site:
            items = [item for item in items if site in str(item.get("所属站点", ""))]

        def urgency(item: dict[str, Any]) -> tuple[int, str, int]:
            return (TIER_RANK[item["queue_tier"]], str(item.get("下次复测日") or ""), int(item["id"]))

        items.sort(key=urgency)
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            groups.setdefault(str(item["所属站点"]), []).append(item)

        site_groups = [
            {
                "所属站点": site_name,
                "items": site_items,
                "超标": sum(1 for item in site_items if item["queue_tier"] == TIER_FAIL),
                "超期": sum(1 for item in site_items if item["queue_tier"] == TIER_OVERDUE),
                "临期": sum(1 for item in site_items if item["queue_tier"] == TIER_DUE_SOON),
            }
            for site_name, site_items in sorted(
                groups.items(), key=lambda pair: urgency(pair[1][0])
            )
        ]
        counts = {tier: sum(1 for item in items if item["queue_tier"] == tier) for tier in TIER_ORDER}
        return {
            "as_of": today().isoformat(),
            "cycle_months": settings["cycle_months"],
            "warn_days": settings["warn_days"],
            "resistance_limit": RESISTANCE_LIMIT,
            "total": len(items),
            "counts": counts,
            "site_groups": site_groups,
        }

    # ---------- 复测登记 ----------
    def register_retest(
        self,
        entry_id: int,
        values: dict[str, Any],
        *,
        source: str = SOURCE_RETEST,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"防雷装置 {entry_id} 不存在或已归档"
        resistance_text, tester, test_day, error = self._clean_measurement(values)
        if error:
            return None, error
        record = _append_test(
            entry,
            test_date=test_day,
            resistance_text=resistance_text,
            tester=tester,
            source=source,
            spd=values.get("浪涌保护") if source == SOURCE_REPLACE else None,
            module_desc=values.get("防雷模块") if source == SOURCE_REPLACE else None,
        )
        _sync_entry(entry)
        shown = format_resistance(resistance_text)
        if record["passed"]:
            message = (
                f"{entry['装置编号']} 复测合格（接地电阻 {shown}），已按周期重排至 "
                f"{entry['下次复测日']}，本轮退出复测队列"
            )
        else:
            message = (
                f"{entry['装置编号']} 复测仍超标（接地电阻 {shown} > "
                f"{RESISTANCE_LIMIT:g}Ω），继续留在复测队列，请整改后再测"
            )
        return _view(entry), message

    # ---------- 浪涌保护模块更换 ----------
    def replace_spd(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"防雷装置 {entry_id} 不存在或已归档"
        spd = str(values.get("浪涌保护") or "").strip()
        if not spd:
            return None, "请登记更换后的浪涌保护模块型号"
        view, message = self.register_retest(entry_id, values, source=SOURCE_REPLACE)
        if view is None:
            return None, message
        return view, (
            f"{entry['装置编号']} 浪涌保护模块已更换为 {spd}，测试人员/测试日期随更换后测试同步更新；{message}"
        )

    # ---------- 复测周期 ----------
    def get_settings(self) -> dict[str, Any]:
        return {
            "cycle_months": settings["cycle_months"],
            "warn_days": settings["warn_days"],
            "resistance_limit": RESISTANCE_LIMIT,
            "rescheduled_devices": len(store.rows(MODULE)),
        }

    def reschedule(self, cycle_months: Any) -> tuple[dict[str, Any] | None, str]:
        cycle = self._clean_cycle(cycle_months)
        if cycle is None:
            return None, f"复测周期需为 {MIN_CYCLE_MONTHS}-{MAX_CYCLE_MONTHS} 之间的整数月"
        old_cycle = int(settings["cycle_months"])
        if cycle == old_cycle:
            return self.get_settings(), f"复测周期本就是 {old_cycle} 个月，无需重排"
        settings["cycle_months"] = cycle

        changed: list[dict[str, Any]] = []
        for entry in store.rows(MODULE):
            entry["cycle_months"] = cycle
            before = entry.get("下次复测日")
            base = parse_date(entry.get("上次测试"))
            newest = latest_test(entry)
            if newest:
                base = parse_date(newest.get("date")) or base
            if base is not None:
                entry["下次复测日"] = add_months(base, cycle).isoformat()
            _sync_entry(entry)
            if before != entry.get("下次复测日"):
                changed.append({"装置编号": entry.get("装置编号"), "旧日期": before, "新日期": entry.get("下次复测日")})
        return self.get_settings(), f"复测周期已由 {old_cycle} 个月调整为 {cycle} 个月，{len(changed)} 台装置按新周期重排"

    # ---------- 共用校验 ----------
    def _clean_measurement(self, values: dict[str, Any]) -> tuple[str, str, date, str | None]:
        resistance_text = str(values.get("接地电阻") or "").strip()
        if parse_resistance(resistance_text) is None:
            return "", "", today(), "接地电阻需填写数值，例如 4.2 或 4.2Ω"
        tester = str(values.get("测试人员") or "").strip()
        if not tester:
            return "", "", today(), "请填写本次测试人员"
        test_day = parse_date(values.get("测试日期"))
        if test_day is None:
            return "", "", today(), "测试日期格式应为 YYYY-MM-DD"
        return resistance_text, tester, test_day, None

    @staticmethod
    def _clean_cycle(value: Any) -> int | None:
        try:
            cycle = int(value)
        except (TypeError, ValueError):
            return None
        if not MIN_CYCLE_MONTHS <= cycle <= MAX_CYCLE_MONTHS:
            return None
        return cycle


# 启动时把种子数据按统一派生口径对齐（状态、待处理标记、下次复测日一并算好）
def _sync_seed() -> None:
    for row in store.rows(MODULE):
        row.setdefault("cycle_months", settings["cycle_months"])
        row.setdefault("tests", [])
        _sync_entry(row)


_sync_seed()
