from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


@dataclass(frozen=True, slots=True)
class DateWindow:
    start: date
    end: date

    @classmethod
    def trailing_months(cls, today: date, months: int) -> "DateWindow":
        """The current (partial) month plus `months` full months before it."""
        return cls(start=today.replace(day=1) - relativedelta(months=months), end=today)

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def months(self) -> list[str]:
        keys: list[str] = []
        cursor = self.start.replace(day=1)
        while cursor <= self.end:
            keys.append(month_key(cursor))
            cursor += relativedelta(months=1)
        return keys

    @property
    def span_in_months(self) -> int:
        return len(self.months())
