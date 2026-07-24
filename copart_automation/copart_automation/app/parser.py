"""HTML parsing module for Copart vehicle listings.

Design decisions:
- BeautifulSoup4 is used for its simplicity and resilience with
  malformed or changing HTML. Playwright provides the raw HTML after
  JavaScript execution, ensuring dynamic content is captured.
- Parsing never relies on a single CSS selector; fallbacks are used
  for common data points to improve resilience against site updates.
- All parsed data is validated through Pydantic models before being
  returned, ensuring data quality.
"""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup
from playwright.async_api import Page

from copart_automation.app.config import settings
from copart_automation.app.exceptions import ParseError
from copart_automation.app.logger import get_logger
from copart_automation.app.models import Vehicle

logger = get_logger(__name__)


class VehicleParser:
    """Parses HTML from Copart pages into structured Vehicle models.

    This parser operates on the assumption that pages have completed
    their JavaScript execution (managed by Playwright) and provides
    approximate selectors. If Copart updates its site structure,
    selectors must be updated accordingly.
    """

    def __init__(self) -> None:
        # Pre-compile common selectors is not practical with BeautifulSoup
        # since selectors are evaluated at parse time.
        pass

    async def parse_search_results(self, page: Page) -> list[Vehicle]:
        """Parse a search results page and return Vehicle instances.

        Args:
            page: The Playwright Page instance after navigation.

        Returns:
            A list of Vehicle objects extracted from the results page.

        Raises:
            ParseError: If the page structure does not match expected patterns.
        """
        logger.info("Parsing search results from {}", page.url)
        try:
            export_vehicles = await self.parse_export_lot_search_results(page)
            if export_vehicles:
                logger.info("Using export endpoint for {} results", len(export_vehicles))
                return export_vehicles
        except Exception as exc:
            logger.warning("Export endpoint parsing failed for {}: {}", page.url, exc)

        html_content = await page.content()
        soup = BeautifulSoup(html_content, "lxml")

        vehicles: list[Vehicle] = []
        # Common container selectors for result cards
        result_containers = soup.select(
            ".search-result, .vehicle-card, .lot-item, .listing, [data-testid*='vehicle']"
        )
        if not result_containers:
            # Fallback: look for any table rows with lot numbers
            result_containers = soup.select("tr[data-lot], .results-row, .search-row")

        for container in result_containers:
            try:
                vehicle = await self._parse_result_container(container)
                if vehicle:
                    vehicles.append(vehicle)
            except Exception as exc:
                logger.warning(f"Failed to parse result container: {exc}")
                # Continue with remaining results rather than failing entirely
                continue

        if not vehicles and result_containers:
            logger.info("No complete vehicles parsed from {} containers.", len(result_containers))
        elif not vehicles:
            logger.info("No result containers found on page.")

        return vehicles

    async def parse_vehicle_details(self, page: Page) -> Vehicle | None:
        """Parse an individual vehicle detail page.

        Args:
            page: The Playwright Page instance for the detail page.

        Returns:
            A Vehicle instance if parsing succeeds; None otherwise.
        """
        logger.info("Parsing vehicle details from {}", page.url)
        html_content = await page.content()
        soup = BeautifulSoup(html_content, "lxml")

        try:
            return await self._parse_detail_page(soup, page_url=page.url)
        except Exception as exc:
            logger.error(f"Failed to parse vehicle details: {exc}")
            raise ParseError(f"Could not parse vehicle details: {exc}") from exc

    async def parse_export_lot_search_results(self, page: Page) -> list[Vehicle]:
        """Parse the Copart exportLotSearchResults JSON payload.

        The endpoint returns a JSON array of lot-search rows that can be
        consumed directly without scraping the HTML markup. This is more
        reliable for account-accessible auction pages and keeps the existing
        parser API consistent.
        """
        logger.info("Parsing export lot search results from {}", page.url)
        payload_text: str | None = None

        context = getattr(page, "context", None)
        request_api = getattr(context, "request", None)
        if request_api is not None:
            get_method = getattr(request_api, "get", None)
            if callable(get_method):
                try:
                    headers = {
                        "accept": "application/json, text/plain, */*",
                        "accept-language": "en-US,en;q=0.9",
                        "cache-control": "no-cache",
                        "pragma": "no-cache",
                        "referer": str(page.url),
                        "x-requested-with": "XMLHttpRequest",
                        "user-agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/125.0.0.0 Safari/537.36"
                        ),
                    }
                    response = await get_method(
                        "https://www.copart.com/client/exportLotSearchResults",
                        headers=headers,
                    )
                    if getattr(response, "ok", False):
                        payload_text = await response.text()
                except Exception:
                    payload_text = None

        if not payload_text:
            evaluate = getattr(page, "evaluate", None)
            if callable(evaluate):
                try:
                    payload_text = await evaluate("() => document.body.innerText || document.documentElement.innerText")
                except Exception:
                    payload_text = None

        if not payload_text:
            content = getattr(page, "content", None)
            if callable(content):
                try:
                    payload_text = await content()
                except Exception:
                    payload_text = None

        if not payload_text:
            request = getattr(page, "request", None)
            get_method = getattr(request, "get", None)
            if callable(get_method):
                try:
                    response = await get_method(str(page.url), headers={})
                    payload_text = await response.text()
                except Exception:
                    payload_text = None

        if not payload_text:
            return []

        vehicles: list[Vehicle] = []
        try:
            data = json.loads(payload_text)
        except json.JSONDecodeError:
            # Some responses may be wrapped in a JSON object or contain a preamble.
            cleaned = payload_text.strip()
            if cleaned.startswith("[") and cleaned.endswith("]"):
                data = json.loads(cleaned)
            else:
                import re
                match = re.search(r"\[(.*?)\]\s*$", cleaned, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                else:
                    return []

        if isinstance(data, dict):
            rows = data.get("results") or data.get("data") or data.get("lots") or []
        else:
            rows = data

        for row in rows:
            if not isinstance(row, dict):
                continue
            lot_number = row.get("lotNumber") or row.get("lot") or row.get("lotNumberDisplay")
            vin = row.get("vin") or row.get("VIN")
            if not lot_number or not vin:
                continue

            vehicle = Vehicle(
                vin=str(vin).strip(),
                lot_number=str(lot_number).strip(),
                title_text=row.get("title") or row.get("titleText"),
                year=self._clean_int(str(row.get("year") or "")),
                make=row.get("make"),
                model=row.get("model"),
                odometer=self._clean_int(str(row.get("odometer") or "")),
                damage_description=row.get("damage") or row.get("damageDescription"),
                sale_date=row.get("saleDate") or row.get("auctionDate"),
                current_bid=self._clean_float(str(row.get("currentBid") or row.get("bid") or "")),
                auction_status=row.get("status") or row.get("auctionStatus"),
                detail_url=row.get("detailUrl") or row.get("lotUrl"),
                image_urls=row.get("imageUrls") if isinstance(row.get("imageUrls"), list) else None,
            )
            vehicles.append(vehicle)

        return vehicles

    async def parse_lots_list(self, page: Page) -> list[str]:
        """Parse an auction 'lots view' page and return a list of lot detail URLs.

        This returns absolute URLs to individual lot/detail pages.
        """
        logger.info("Parsing lots list from {}", page.url)
        try:
            export_vehicles = await self.parse_export_lot_search_results(page)
            if export_vehicles:
                urls = [str(vehicle.detail_url) for vehicle in export_vehicles if vehicle.detail_url]
                if urls:
                    logger.info("Using export endpoint for {} lot URLs", len(urls))
                    return self._dedupe_urls(urls)
        except Exception as exc:
            logger.warning("Export endpoint lot parsing failed for {}: {}", page.url, exc)

        html_content = await page.content()
        soup = BeautifulSoup(html_content, "lxml")

        urls: list[str] = []
        # Common selectors for lot links/buttons
        link_selectors = [
            "a[href*='/lot/']",
            "a[href*='/vehicle/']",
            "a.view-lots, a.lot-link, .lot a",
        ]
        for sel in link_selectors:
            for a in soup.select(sel):
                href = a.get("href")
                if not href:
                    continue
                if href.startswith("/"):
                    href = f"https://www.copart.com{href}"
                if href.startswith("http") and href not in urls:
                    urls.append(href)

        deduped = self._dedupe_urls(urls)
        logger.info("Found {} lot URLs on page", len(deduped))
        return deduped

    @staticmethod
    def _dedupe_urls(urls: list[str]) -> list[str]:
        seen = set()
        deduped: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped

    async def _parse_result_container(self, container: Any) -> Vehicle | None:
        """Parse a single result container into a Vehicle model."""
        # Extract VIN (look for text patterns or specific selectors)
        vin_text = self._find_text(container, [
            ".vin-label", ".vehicle-vin", "[data-field='vin']", "td[data-label='VIN']",
        ])
        vin = self._clean_vin(vin_text)

        # Extract lot number
        lot_text = self._find_text(container, [
            ".lot-number", ".lot-label", "[data-field='lot']", "a[href*='lot/']",
        ])
        lot_number = self._clean_lot(lot_text)

        # Extract title
        title_text = self._find_text(container, [
            ".title-status", ".vehicle-title", "[data-field='title']",
        ])

        # Extract year, make, model
        year_text = self._find_text(container, [
            ".year", ".model-year", "[data-field='year']",
        ])
        year = self._clean_int(year_text)

        make_text = self._find_text(container, [
            ".make", "[data-field='make']",
        ])
        model_text = self._find_text(container, [
            ".model", "[data-field='model']",
        ])

        # Odometer
        odometer_text = self._find_text(container, [
            ".odometer", ".mileage", "[data-field='odometer']",
        ])
        odometer = self._clean_int(odometer_text)

        # Damage description
        damage_text = self._find_text(container, [
            ".damage", ".damage-desc", "[data-field='damage']",
        ])

        # Sale date
        sale_date_text = self._find_text(container, [
            ".sale-date", ".auction-date", "[data-field='sale_date']",
        ])

        # Current bid
        bid_text = self._find_text(container, [
            ".current-bid", ".bid-amount", ".price", "[data-field='current_bid']",
        ])
        current_bid = self._clean_float(bid_text)

        # Auction status
        status_text = self._find_text(container, [
            ".auction-status", ".status", "[data-field='status']",
        ])

        # Detail URL
        link = container.select_one("a[href*='lot/'], a[href*='vehicle/']")
        detail_url = str(link["href"]) if link else None
        if detail_url and not detail_url.startswith("http"):
            detail_url = f"https://www.copart.com{detail_url}"

        # Image URLs (look for img tags within container)
        image_urls: list[str] = []
        for img in container.select("img[src*='copart']"):
            src = img.get("src") or img.get("data-src")
            if src and isinstance(src, str) and src.startswith("http"):
                image_urls.append(src)

        if not vin or not lot_number:
            # If core identifiers are missing, do not create a partial record
            logger.debug("Skipping container: missing VIN or lot number.")
            return None

        return Vehicle(
            vin=vin,
            lot_number=lot_number,
            title_text=title_text,
            year=year,
            make=make_text,
            model=model_text,
            odometer=odometer,
            damage_description=damage_text,
            sale_date=sale_date_text,
            current_bid=current_bid,
            auction_status=status_text,
            detail_url=detail_url,
            image_urls=image_urls if image_urls else None,
        )

    async def _parse_detail_page(self, soup: BeautifulSoup, page_url: str | None = None) -> Vehicle:
        """Parse a full vehicle detail page with broader selectors."""
        # For detail pages, we try to gather more comprehensive data
        # This is a fallback/extended version of the result parser.
        container = soup

        vin_text = self._find_text(soup, [
            ".vin", ".vehicle-vin", "span:contains('VIN'), td:contains('VIN') + td",
        ])
        vin = self._clean_vin(vin_text)
        lot_text = self._find_text(soup, [
            ".lot-number", ".lot-number-detail", "span:contains('Lot'), td:contains('Lot') + td",
        ])
        lot_number = self._clean_lot(lot_text)

        # If VIN/lot are still missing, try to extract from URL or title
        if not vin:
            title_tag = soup.select_one("title")
            if title_tag:
                title_str = title_tag.get_text()
                # Very rough VIN extraction from title
                import re
                match = re.search(r"VIN[:\s]*([A-HJ-NPR-Z0-9]{17})", title_str)
                if match:
                    vin = match.group(1)

        # Build a minimal Vehicle if core data is present
        year_text = self._find_text(soup, [".year", ".model-year"])
        make_text = self._find_text(soup, [".make"])
        model_text = self._find_text(soup, [".model"])
        odometer_text = self._find_text(soup, [".odometer", ".mileage"])
        damage_text = self._find_text(soup, [".damage", ".damage-desc"])
        sale_date_text = self._find_text(soup, [".sale-date", ".auction-date"])
        bid_text = self._find_text(soup, [".current-bid", ".price"])
        status_text = self._find_text(soup, [".auction-status", ".status"])
        title_text = self._find_text(soup, [".title-status", ".title"])

        # Image URLs from detail page
        image_urls = []
        for img in soup.select("img[src*='copart'], img[data-src*='copart']"):
            src = img.get("src") or img.get("data-src")
            if src and isinstance(src, str) and src.startswith("http"):
                image_urls.append(src)

        if not vin or not lot_number:
            # Try URL-based lot extraction
            from urllib.parse import urlparse
            # Not easily available here without page URL; rely on text
            pass

        # We must have VIN and lot to create a record
        if not vin or not lot_number:
            raise ParseError("Could not extract VIN and lot number from vehicle details.")

        return Vehicle(
            vin=vin,
            lot_number=lot_number,
            title_text=title_text,
            year=self._clean_int(year_text),
            make=make_text,
            model=model_text,
            odometer=self._clean_int(odometer_text),
            damage_description=damage_text,
            sale_date=sale_date_text,
            current_bid=self._clean_float(bid_text),
            auction_status=status_text,
            detail_url=page_url if page_url else None,
            image_urls=image_urls if image_urls else None,
        )

    @staticmethod
    def _find_text(container: Any, selectors: list[str]) -> str | None:
        """Find text content using a prioritized list of selectors.

        Returns the first non-empty text match.
        """
        # Try CSS selectors first
        for selector in selectors:
            try:
                element = container.select_one(selector)
            except Exception:
                element = None
            if element:
                text = element.get_text(strip=True)
                if text:
                    return text

        # Fallback: search the full text for common label patterns
        try:
            full_text = container.get_text(separator="\n", strip=True)
        except Exception:
            try:
                full_text = str(container)
            except Exception:
                return None

        # Map selectors to simple keywords (best-effort)
        keywords = []
        for s in selectors:
            # extract readable token from selector
            token = s
            # remove CSS punctuation
            for ch in ['.', '#', '[', ']', '>', '+', '~', '*', ':']:
                token = token.replace(ch, ' ')
            token = token.strip()
            if token:
                # split and take likely words
                parts = token.split()
                for p in parts:
                    if len(p) > 2:
                        keywords.append(p)

        # Deduplicate keywords while preserving order
        seen = set()
        dedup_k = []
        for k in keywords:
            kl = k.lower()
            if kl not in seen:
                seen.add(kl)
                dedup_k.append(k)

        # Search for label: value patterns like "VIN: 1HGBH41JXMN109186"
        import re
        for k in dedup_k:
            pattern = re.compile(rf"{re.escape(k)}\s*[:\-\t]*\s*(.+)", re.IGNORECASE)
            m = pattern.search(full_text)
            if m:
                val = m.group(1).split('\n')[0].strip()
                if val:
                    return val

        # Specific heuristics for VIN and lot number
        # VIN (17 chars, may be masked with asterisks)
        vin_match = re.search(r"([A-HJ-NPR-Z0-9\*]{6,17})", full_text)
        if vin_match:
            return vin_match.group(1)

        # Lot number: look for 'Lot' followed by digits
        lot_match = re.search(r"Lot(?:\s|\#|\:)?\s*([0-9]{3,12})", full_text, re.IGNORECASE)
        if lot_match:
            return lot_match.group(1)

        return None

    @staticmethod
    def _clean_vin(text: Any) -> str | None:
        if not text or not isinstance(text, str):
            return None
        # Remove common prefixes and whitespace
        cleaned = text.replace("VIN:", "").replace("VIN", "").strip()
        # VINs are 17 characters; take the first 17 alphanumeric chars that look right
        import re
        match = re.search(r"[A-HJ-NPR-Z0-9]{17}", cleaned)
        if match:
            return match.group(0)
        # If shorter, return as-is if it looks somewhat valid
        if len(cleaned) >= 10:
            return cleaned[:17]
        return None

    @staticmethod
    def _clean_lot(text: Any) -> str | None:
        if not text or not isinstance(text, str):
            return None
        cleaned = text.replace("Lot:", "").replace("Lot", "").strip()
        # Remove URL fragments and extra whitespace
        import re
        match = re.search(r"[\w\-/]+", cleaned)
        if match:
            return match.group(0)
        if cleaned:
            return cleaned
        return None

    @staticmethod
    def _clean_int(text: Any) -> int | None:
        if not text or not isinstance(text, str):
            return None
        import re
        match = re.search(r"\d+", text)
        if match:
            try:
                return int(match.group(0))
            except ValueError:
                return None
        return None

    @staticmethod
    def _clean_float(text: Any) -> float | None:
        if not text or not isinstance(text, str):
            return None
        import re
        # Match currency amounts like $1,234.56 or 1234.56
        match = re.search(r"[\$]?([\d,]+\.\d{2})", text)
        if match:
            cleaned = match.group(1).replace(",", "")
            try:
                return float(cleaned)
            except ValueError:
                return None
        # Try integer-style amounts
        int_match = re.search(r"[\$]?([\d,]+)", text)
        if int_match:
            cleaned = int_match.group(1).replace(",", "")
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None
