import json
from datetime import date, datetime

from myne.core.errors import UpstreamServiceError
from myne.core.http import HttpClient
from myne.integrations.types import ArchiveSnapshot


class WaybackClient:
    """Internet Archive CDX + raw snapshot access. No API key required."""

    _CDX_URL = "https://web.archive.org/cdx/search/cdx"
    _SNAPSHOT_URL = "https://web.archive.org/web/{timestamp}id_/{url}"
    _SERVICE = "wayback"

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    async def monthly_snapshots(self, url: str, *, start: date, end: date) -> list[ArchiveSnapshot]:
        response = await self._http.request(
            self._SERVICE,
            "GET",
            self._CDX_URL,
            params={
                "url": url,
                "output": "json",
                "from": start.strftime("%Y%m%d"),
                "to": end.strftime("%Y%m%d"),
                "filter": "statuscode:200",
                "collapse": "timestamp:6",
                "fl": "timestamp,original",
            },
        )
        if not response.text.strip():
            return []
        try:
            rows = json.loads(response.text)
        except json.JSONDecodeError:
            raise UpstreamServiceError(self._SERVICE, "CDX returned invalid JSON") from None
        if not isinstance(rows, list) or len(rows) < 2:
            return []

        header, *records = rows
        ts_index, url_index = header.index("timestamp"), header.index("original")
        snapshots: list[ArchiveSnapshot] = []
        for record in records:
            try:
                captured_on = datetime.strptime(record[ts_index][:8], "%Y%m%d").date()
            except (ValueError, IndexError):
                continue
            snapshots.append(ArchiveSnapshot(record[ts_index], record[url_index], captured_on))
        return snapshots

    async def fetch_html(self, snapshot: ArchiveSnapshot) -> str:
        url = self._SNAPSHOT_URL.format(timestamp=snapshot.timestamp, url=snapshot.original_url)
        response = await self._http.request(self._SERVICE, "GET", url)
        return response.text
