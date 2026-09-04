"""Scraper for the gebrauchte-veranstaltungstechnik.de search page.

Site notes (reverse engineered):

* Base host is ``https://gebrauchte-veranstaltungstechnik.de`` -- the ``www.``
  variant is NOT covered by the TLS certificate, so it must not be used.
* Search endpoint: ``/?modul=search&site=search&key=<keyword>&order=<order>``
* ``order`` accepts ``rel``, ``dDESC``, ``dASC``, ``pDESC``, ``pASC``, ``distASC``.
* The result page is NOT paginated -- every hit is rendered at once.
* Each hit is one ``<table class='adslist_item'>`` element:

  .. code-block:: html

     <table class='adslist_item '>
       <tr>
         <td class='adslist_left'><a href='ad-123-slug'><img src='...'/></a></td>
         <td class='adslist_middle'>
           <a href='ad-123-slug' class='hdl_link'>Title</a>
           <span class='hidden-phone'>Description snippet...</span>
         </td>
         <td class='adslist_right'>
           <b>4850&euro;</b> <i class='icon-list-alt' title='Gewerblicher Verkäufer'></i><br>
           28.03.2026<br>
           53115 Bonn
         </td>
       </tr>
     </table>
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup, Tag

from .models import Listing

log = logging.getLogger(__name__)

BASE_URL = "https://gebrauchte-veranstaltungstechnik.de"
SEARCH_PATH = "/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

VALID_ORDERS = ("rel", "dDESC", "dASC", "pDESC", "pASC", "distASC")

_AD_ID_RE = re.compile(r"ad-(\d+)-")
_DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
_PRICE_RE = re.compile(r"(\d[\d.,\s]*)")


class ScrapeError(RuntimeError):
    """Raised when the search page could not be fetched or parsed."""


def _parse_price(raw: str) -> float | None:
    """Turn a German price string such as ``1.234,50€`` into a float."""
    match = _PRICE_RE.search(raw)
    if not match:
        return None
    number = match.group(1).strip().replace(" ", "")
    # German notation: '.' groups thousands, ',' is the decimal separator.
    if "," in number:
        number = number.replace(".", "").replace(",", ".")
    else:
        number = number.replace(".", "")
    try:
        return float(number)
    except ValueError:
        return None


def _parse_date(raw: str) -> date | None:
    match = _DATE_RE.search(raw)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%d.%m.%Y").date()
    except ValueError:
        return None


def _parse_location(cell_text: str) -> str:
    """The location is the line that follows the posting date."""
    lines = [line.strip() for line in cell_text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if _DATE_RE.search(line) and index + 1 < len(lines):
            return lines[index + 1]
    return lines[-1] if lines else ""


def _parse_item(table: Tag) -> Listing | None:
    link = table.find("a", class_="hdl_link")
    if not isinstance(link, Tag):
        return None

    href = str(link.get("href") or "")
    id_match = _AD_ID_RE.search(href)
    if not id_match:
        return None

    title = link.get_text(" ", strip=True)

    snippet = table.find("span", class_="hidden-phone")
    description = snippet.get_text("\n", strip=True) if isinstance(snippet, Tag) else ""

    right = table.find("td", class_="adslist_right")
    price_text = ""
    price = None
    posted = None
    location = ""
    commercial = False
    if isinstance(right, Tag):
        bold = right.find("b")
        if isinstance(bold, Tag):
            price_text = bold.get_text(" ", strip=True)
            price = _parse_price(price_text)
        commercial = right.find("i", class_="icon-list-alt") is not None
        cell_text = right.get_text("\n", strip=True)
        posted = _parse_date(cell_text)
        location = _parse_location(cell_text)

    image = table.find("img", class_="textbild")
    image_url = str(image.get("src")) if isinstance(image, Tag) and image.get("src") else None

    return Listing(
        ad_id=id_match.group(1),
        title=title,
        url=f"{BASE_URL}/{href.lstrip('/')}",
        description=description,
        price=price,
        price_text=price_text,
        posted=posted,
        location=location,
        image_url=image_url,
        commercial=commercial,
    )


def parse_search_html(html: str) -> list[Listing]:
    """Parse a raw search result page into :class:`Listing` objects."""
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Listing] = []
    seen: set[str] = set()
    for table in soup.find_all("table", class_="adslist_item"):
        listing = _parse_item(table)
        if listing is None or listing.ad_id in seen:
            continue
        seen.add(listing.ad_id)
        listings.append(listing)
    return listings


class GvtClient:
    """Thin HTTP client around the site's search page."""

    def __init__(self, timeout: float = 30.0, session: requests.Session | None = None) -> None:
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            }
        )

    def search(self, keyword: str, order: str = "dDESC") -> list[Listing]:
        """Run a keyword search and return all listings on the result page."""
        if order not in VALID_ORDERS:
            raise ValueError(f"order must be one of {VALID_ORDERS}, got {order!r}")

        params = {"modul": "search", "site": "search", "key": keyword, "order": order}
        try:
            response = self.session.get(
                BASE_URL + SEARCH_PATH, params=params, timeout=self.timeout
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ScrapeError(f"search for {keyword!r} failed: {exc}") from exc

        response.encoding = response.encoding or "utf-8"
        listings = parse_search_html(response.text)
        log.debug("keyword %r -> %d listings", keyword, len(listings))
        return listings

    def close(self) -> None:
        self.session.close()
