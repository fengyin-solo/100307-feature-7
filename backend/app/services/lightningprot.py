"""防雷接地业务规则：复测周期、下次复测日、复测队列与测试历史都在这里统一推导。

口径约定（台账与复测队列共用同一套序列化结果，避免两处结论不一致）：
- 下次复测日 = 最近一次测试日期 + 复测周期（月）；还没有测试记录时按登记日起算。
- 电阻是否超标：以最近一次测试阻值与电阻限值比较；历史记录保留当时结论。
- 复测合格后装置从复测队列退出；超期、即将到期、电阻超标或模块劣化则留在队列。
- 浪涌保护模块更换时同步更新测试人员与测试日期，并以更换后复测结果重排下次复测日。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "lightningprot"
META_KEY = "lightningprot_settings"
REQUIRED_FIELDS = ["装置编号", "所属站点"]
STATUS_ORDER = ["合格", "电阻超标", "模块劣化", "已更换"]

# 队列状态及排序优先级：电阻超标永远最靠前，然后是已超期、即将到期、模块劣化，
# 未到复测日的合格装置退出队列。
QUEUE_STATES = ["电阻超标", "已超期", "模块劣化·已超期", "即将到期", "模块劣化", "已安排"]
STATE_RANK = {name: idx for idx, name in enumerate(QUEUE_STATES)}
DEFAULT_SETTINGS = {"cycle_months": 12, "warn_days": 30, "resistance_limit": 10.0}


def _today() -> date:
    return date.today()


def _parse_date(value: Any) -> date | None:
    """宽松解析测试/更换日期，只接受 YYYY-MM-DD。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _add_months(day: date, months: int) -> date:
    """按自然月顺延，落在大月月末（如 1/31 + 1 月）时收到当月最后一天。"""
    year = day.year + (day.month - 1 + months) // 12
    month = (day.month - 1 + months) % 12 + 1
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = next_month_first.fromordinal(next_month_first.toordinal() - 1).day
    return date(year, month, min(day.day, last_day))


def _parse_resistance(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class LightningprotService:
    def __init__(self) -> None:
        if store.get_meta(META_KEY) is None:
            store.set_meta(META_KEY, dict(DEFAULT_SETTINGS))
        # 启动时按种子数据重算一遍派生状态，保证 status/pending/abnormal 与推导结论一致。
        for entry in store.rows(MODULE):
            self._recompute(entry)

    # ---- 配置：复测周期调整后，所有装置的下次复测日统一重排 ----
    def get_settings(self) -> dict[str, Any]:
        return dict(store.get_meta(META_KEY) or DEFAULT_SETTINGS)

    def update_settings(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        current = self.get_settings()
        try:
            cycle = int(values.get("cycle_months", current["cycle_months"]))
            warn_days = int(values.get("warn_days", current["warn_days"]))
            limit = float(values.get("resistance_limit", current["resistance_limit"]))
        except (TypeError, ValueError):
            return None, "复测周期、预警天数、电阻限值都必须是数字"
        if not 1 <= cycle <= 60:
            return None, "复测周期需在 1～60 个月之间"
        if not 0 <= warn_days <= 365:
            return None, "到期预警天数需在 0～365 天之间"
        if not 0 < limit <= 1000:
            return None, "接地电阻限值需在 0～1000Ω 之间"
        settings = {"cycle_months": cycle, "warn_days": warn_days, "resistance_limit": limit}
        store.set_meta(META_KEY, settings)
        # 周期/限值变了，全部装置按新口径重算。
        for entry in store.rows(MODULE):
            self._recompute(entry)
        return settings, ""

    # ---- 台账/队列共用的结论推导 ----
    @staticmethod
    def _latest_test(entry: dict[str, Any]) -> dict[str, Any] | None:
        tests = entry.get("tests") or []
        return tests[-1] if tests else None

    @staticmethod
    def _latest_replacement(entry: dict[str, Any]) -> dict[str, Any] | None:
        replacements = entry.get("replacements") or []
        return replacements[-1] if replacements else None

    def _latest_failed_test(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """最近一次电阻超标的测试记录，用于在队列里标注“哪一次测超的”。"""
        for test in reversed(entry.get("tests") or []):
            if test.get("result") == "电阻超标":
                return test
        return None

    def _derive(self, entry: dict[str, Any], settings: dict[str, Any], today: date) -> dict[str, Any]:
        """根据原始台账与测试历史推导对外结论，台账页和复测队列都走这一份。"""
        degraded = bool(entry.get("degraded"))
        replaced_pending = bool(entry.get("replaced_pending"))
        latest = self._latest_test(entry)
        failed = self._latest_failed_test(entry)
        limit = float(settings["resistance_limit"])

        last_date = _parse_date(latest.get("date") if latest else None) or _parse_date(entry.get("created_at"))
        resistance = None
        if latest is not None:
            resistance = _parse_resistance(latest.get("resistance"))
        over_limit = bool(latest and latest.get("result") == "电阻超标")
        # 限值调整后以最新阻值重新认定一次，历史记录的当时结论仍保留在 tests 里。
        if resistance is not None and not over_limit:
            over_limit = resistance > limit

        if degraded:
            status = "模块劣化"
        elif over_limit:
            status = "电阻超标"
        elif replaced_pending:
            status = "已更换"
        else:
            status = "合格"

        next_day = _add_months(last_date, int(settings["cycle_months"])) if last_date else None
        days_left = (next_day - today).days if next_day else None

        if over_limit:
            queue_state = "电阻超标"
        elif degraded:
            # 劣化装置无论是否到复测日都要安排更换；同时已超期时叠加标注。
            if days_left is not None and days_left < 0:
                queue_state = "模块劣化·已超期"
            else:
                queue_state = "模块劣化"
        elif replaced_pending:
            queue_state = "已安排"
        elif days_left is not None and days_left < 0:
            queue_state = "已超期"
        elif days_left is not None and days_left <= int(settings["warn_days"]):
            queue_state = "即将到期"
        else:
            queue_state = ""  # 合格且未到期：退出复测队列
        failure_note = ""
        # 只在“最近一次测试就是超标测试”（即问题尚未复测闭环）时展示测超记录。
        if failed and latest is not None and failed is latest:
            value_text = f"{failed.get('resistance')}Ω" if failed.get("resistance") is not None else "阻值未填"
            failure_note = f"{failed.get('date', '')} 测试 {value_text}（限值 {limit:g}Ω），{failed.get('tester', '')}：{failed.get('remark') or '判定电阻超标'}"

        return {
            "status": status,
            "abnormal": over_limit,
            "degraded": degraded,
            "in_queue": bool(queue_state),
            "queue_state": queue_state,
            "next_date": next_day.isoformat() if next_day else "",
            "days_left": days_left,
            "over_limit": over_limit,
            "failure_note": failure_note,
            "latest_test_date": latest.get("date", "") if latest else "",
            "latest_resistance": resistance,
        }

    def _serialize(self, entry: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = settings or self.get_settings()
        today = _today()
        derived = self._derive(entry, settings, today)
        latest = self._latest_test(entry)
        return {
            "id": entry["id"],
            "装置编号": entry.get("装置编号", ""),
            "所属站点": entry.get("所属站点", ""),
            "接地电阻": derived["latest_resistance"],
            "防雷模块": entry.get("防雷模块", ""),
            "浪涌保护": entry.get("浪涌保护", ""),
            "上次测试": derived["latest_test_date"],
            "测试人员": latest.get("tester", "") if latest else "",
            "装置状态": derived["status"],
            "下次复测日": derived["next_date"],
            "距复测天数": derived["days_left"],
            "队列状态": derived["queue_state"] or "未入队",
            "in_queue": derived["in_queue"],
            "degraded": derived["degraded"],
            "超标说明": derived["failure_note"],
            "测试记录": entry.get("tests", []),
            "更换记录": entry.get("replacements", []),
        }

    def _recompute(self, entry: dict[str, Any]) -> dict[str, Any]:
        """推导结论并回写 status/pending/abnormal，供通用概览口径复用。"""
        settings = self.get_settings()
        derived = self._derive(entry, settings, _today())
        entry["status"] = derived["status"]
        entry["abnormal"] = derived["abnormal"]
        entry["pending"] = derived["in_queue"]
        return derived

    # ---- 台账列表/明细 ----
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        site: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        settings = self.get_settings()
        today = _today()
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("装置编号", ""))]
        if site:
            rows = [row for row in rows if site in str(row.get("所属站点", ""))]
        derived_rows = [(row, self._derive(row, settings, today)) for row in rows]
        if status:
            derived_rows = [pair for pair in derived_rows if pair[1]["status"] == status]
        # 台账默认也把超期/超标的顶到前面，便于一眼看到要处理的装置。
        derived_rows.sort(key=lambda pair: (
            0 if pair[1]["in_queue"] else 1,
            STATE_RANK.get(pair[1]["queue_state"], 99),
            pair[1]["next_date"] or "9999-12-31",
            str(pair[0].get("装置编号", "")),
        ))
        total = len(derived_rows)
        start = max(page - 1, 0) * size
        page_rows = [self._serialize(row, settings) for row, _ in derived_rows[start:start + size]]
        return page_rows, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._serialize(entry) if entry else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "tests": [],
            "replacements": [],
            "degraded": False,
            "replaced_pending": False,
            "created_at": str(values.get("登记日期") or _today().isoformat()),
        }
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["防雷模块"] = values.get("防雷模块", "")
        entry["浪涌保护"] = values.get("浪涌保护", "")
        rows.append(entry)
        # 登记时若直接带了首测结果，一并入历史；否则从登记日开始排复测周期。
        test_date = _parse_date(values.get("测试日期"))
        resistance = _parse_resistance(values.get("接地电阻"))
        tester = str(values.get("测试人员") or "").strip()
        if test_date and resistance is not None and tester:
            entry["tests"].append({
                "date": test_date.isoformat(),
                "resistance": resistance,
                "tester": tester,
                "remark": str(values.get("remark") or "登记时首测"),
                "result": self._judge(resistance)["result"],
            })
        self._recompute(entry)
        return self._serialize(entry), []

    def _judge(self, resistance: float) -> dict[str, Any]:
        limit = float(self.get_settings()["resistance_limit"])
        return {"result": "合格" if resistance <= limit else "电阻超标"}

    # ---- 登记复测结果（点开一台装置直接登记） ----
    def record_test(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"防雷装置 {entry_id} 不存在或已归档"
        test_date = _parse_date(values.get("date"))
        if test_date is None:
            return None, "测试日期格式不正确，应为 YYYY-MM-DD"
        resistance = _parse_resistance(values.get("resistance"))
        if resistance is None or resistance < 0:
            return None, "接地电阻需为不小于 0 的数字（Ω）"
        tester = str(values.get("tester") or "").strip()
        if not tester:
            return None, "测试人员必填，登记复测要留痕到人"
        remark = str(values.get("remark") or "").strip()

        latest = self._latest_test(entry)
        if latest and (last_date := _parse_date(latest.get("date"))) and test_date < last_date:
            return None, f"测试日期不能早于最近一次测试（{latest.get('date')}）"

        record = {
            "date": test_date.isoformat(),
            "resistance": resistance,
            "tester": tester,
            "remark": remark,
        }
        limit = float(self.get_settings()["resistance_limit"])
        record["result"] = "合格" if resistance <= limit else "电阻超标"
        entry.setdefault("tests", []).append(record)
        if record["result"] == "合格":
            # 复测合格：解除劣化/待复测状态，下次复测日顺延，装置退出队列。
            entry["degraded"] = False
            entry["replaced_pending"] = False
        self._recompute(entry)
        if record["result"] == "合格":
            return self._serialize(entry), "复测合格，装置已退出复测队列，下次复测日已顺延"
        return self._serialize(entry), f"复测仍超标（{resistance:g}Ω > {limit:g}Ω），装置保留在复测队列"

    # ---- 浪涌保护模块更换：人员、日期跟着更新，并以更换后复测重排周期 ----
    def replace_spd(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"防雷装置 {entry_id} 不存在或已归档"
        replace_date = _parse_date(values.get("date"))
        if replace_date is None:
            return None, "更换日期格式不正确，应为 YYYY-MM-DD"
        operator = str(values.get("operator") or "").strip()
        if not operator:
            return None, "更换/测试人员必填"
        module = str(values.get("module") or "").strip()
        if not module:
            return None, "新浪涌保护模块型号必填"
        resistance = _parse_resistance(values.get("resistance"))
        if resistance is None or resistance < 0:
            return None, "更换后接地电阻需为不小于 0 的数字（Ω）"
        reason = str(values.get("reason") or "").strip() or "浪涌保护模块到期/劣化更换"

        record = {
            "date": replace_date.isoformat(),
            "resistance": resistance,
            "tester": operator,
            "remark": f"更换浪涌保护模块「{module}」后测试：{reason}",
        }
        limit = float(self.get_settings()["resistance_limit"])
        record["result"] = "合格" if resistance <= limit else "电阻超标"
        entry.setdefault("tests", []).append(record)
        entry.setdefault("replacements", []).append({
            "date": replace_date.isoformat(),
            "operator": operator,
            "module": module,
            "reason": reason,
            "post_resistance": resistance,
            "post_result": record["result"],
        })
        # 台账上的浪涌保护、测试人员、测试日期与更换保持一致。
        entry["浪涌保护"] = f"{module}（{replace_date:%Y-%m} 更换）"
        entry["degraded"] = False
        entry["replaced_pending"] = record["result"] != "合格"
        self._recompute(entry)
        if record["result"] == "合格":
            return self._serialize(entry), "浪涌保护模块已更换，测试人员与日期同步更新，复测合格并退出队列"
        return self._serialize(entry), "模块已更换，但更换后测试电阻超标，装置仍留在复测队列"

    # ---- 记录劣化（不涉及阻值的现场判定） ----
    def mark_degraded(self, entry_id: int, remark: str = "") -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"防雷装置 {entry_id} 不存在或已归档"
        entry["degraded"] = True
        entry["degrade_remark"] = remark or "巡检发现浪涌保护模块劣化，待更换"
        self._recompute(entry)
        return self._serialize(entry), "已记录模块劣化，装置进入复测队列等待更换"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        """兼容旧动作入口；登记超标请走复测登记，安排更换请走模块更换。"""
        if action == "记录劣化":
            return self.mark_degraded(entry_id)
        if action in {"记录超标", "安排更换"}:
            return None, f"动作「{action}」需在复测队列登记测试结果或更换信息后生效"
        return None, f"动作「{action}」不属于防雷接地可执行范围"

    # ---- 复测队列：按站点列出下次复测日，超期/超标优先 ----
    def queue_overview(self, *, site: str | None = None, state: str | None = None) -> dict[str, Any]:
        settings = self.get_settings()
        today = _today()
        rows = store.rows(MODULE)
        if site:
            rows = [row for row in rows if site in str(row.get("所属站点", ""))]

        queued: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for row in rows:
            derived = self._derive(row, settings, today)
            if derived["in_queue"]:
                queued.append((row, derived))
        queued.sort(key=lambda pair: (
            STATE_RANK.get(pair[1]["queue_state"], 99),
            pair[1]["next_date"] or "9999-12-31",
            str(pair[0].get("所属站点", "")),
            str(pair[0].get("装置编号", "")),
        ))

        # 统计卡始终反映全部在队装置，不受 state 过滤影响；分组与 queued_total 才按过滤口径。
        counts = {name: 0 for name in QUEUE_STATES}
        for _, derived in queued:
            counts[derived["queue_state"]] += 1
        groups: dict[str, list[dict[str, Any]]] = {}
        for row, derived in queued:
            if state and derived["queue_state"] != state:
                continue
            groups.setdefault(str(row.get("所属站点", "")), []).append(self._serialize(row, settings))

        sites = sorted({str(row.get("所属站点", "")) for row in rows})
        rested: list[dict[str, Any]] = []
        for row in rows:
            derived = self._derive(row, settings, today)
            if not derived["in_queue"]:
                rested.append(self._serialize(row, settings))
        rested.sort(key=lambda item: (item.get("next_date") or "9999-12-31", str(item.get("装置编号", ""))))
        return {
            "today": today.isoformat(),
            "settings": settings,
            "sites": sites,
            "counts": counts,
            "queued_total": sum(
                1 for row, derived in queued
                if not state or derived["queue_state"] == state
            ),
            "groups": [{"site": name, "items": groups[name]} for name in sorted(groups)],
            "rested": rested,
        }
