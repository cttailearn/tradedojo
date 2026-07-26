"""
轻量级 5 字段 cron 表达式解析 —— 不引入第三方依赖,够用于数据更新调度。

支持格式 (从左到右): 分 时 日 月 周
  - 通配符: *
  - 范围:   1-5
  - 步长:   */5 或 1-30/2
  - 列表:   1,3,5

周约定: 0=周一 ... 6=周日(与 Python weekday() 对齐),1-5 即周一到周五(与标准 cron 一致)。
"""
from datetime import datetime, timedelta


class CronExpr:
    def __init__(self, expr: str):
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"cron 必须 5 字段,实得 {len(parts)}: {expr!r}")
        self.minute = self._parse(parts[0], 0, 59)
        self.hour   = self._parse(parts[1], 0, 23)
        self.dom    = self._parse(parts[2], 1, 31)
        self.month  = self._parse(parts[3], 1, 12)
        self.dow    = self._parse(parts[4], 0, 6)

    @staticmethod
    def _parse(field: str, lo: int, hi: int) -> set:
        out = set()
        for part in field.split(","):
            step = 1
            if "/" in part:
                part, s = part.split("/", 1)
                step = int(s)
            if part == "*":
                start, end = lo, hi
            elif "-" in part:
                a, b = part.split("-", 1)
                start, end = int(a), int(b)
            else:
                start = end = int(part)
            if start < lo or end > hi:
                raise ValueError(f"cron 字段 {field!r} 超出范围 [{lo},{hi}]")
            out.update(range(start, end + 1, step))
        if not out:
            raise ValueError(f"cron 字段 {field!r} 无有效值")
        return out

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute  in self.minute and
            dt.hour    in self.hour   and
            dt.day     in self.dom    and
            dt.month   in self.month  and
            dt.weekday() in self.dow
        )

    def next_after(self, after: datetime) -> datetime:
        """返回 after 之后下一个匹配时刻(分钟级)"""
        d = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # 一年足够找出下一个匹配,防止表达式错误时死循环
        for _ in range(60 * 24 * 366):
            if self.matches(d):
                return d
            d += timedelta(minutes=1)
        raise RuntimeError(f"在 1 年内找不到匹配: {self!r}")