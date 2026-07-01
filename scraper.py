from __future__ import annotations

import argparse
import json
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.shl.com"
START_URL = f"{BASE_URL}/products/assessments/"
ALLOWED_PREFIX = f"{BASE_URL}/products/assessments/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SKILL_KEYWORDS = {
    "adaptability": ["adaptability", "adapt"],
    "agility": ["learning agility"],
    "analysis": ["analysis", "analytical"],
    "call center": ["call center"],
    "coding": ["coding", "code"],
    "communication": ["communication", "communicate"],
    "customer service": ["customer service"],
    "data interpretation": ["data interpretation"],
    "debugging": ["debugging", "debug"],
    "java": ["java"],
    "joins": ["joins"],
    "language": ["language"],
    "motivation": ["motivation", "motivational"],
    "numerical reasoning": ["numerical reasoning"],
    "object oriented programming": ["object oriented"],
    "personality": ["personality"],
    "problem solving": ["problem solving"],
    "queries": ["queries", "query writing"],
    "reasoning": ["reasoning"],
    "role fit": ["role fit"],
    "sql": ["sql", "database"],
    "stakeholder management": ["stakeholder"],
    "teamwork": ["teamwork", "team work"],
    "verbal reasoning": ["verbal reasoning"],
    "work style": ["work style", "working preferences"],
}

JOB_LEVEL_KEYWORDS = {
    "entry": ["entry", "graduate", "early career", "junior", "fresher", "intern"],
    "mid": ["mid", "professional", "individual contributor"],
    "senior": ["senior", "lead", "leadership", "manager", "director", "executive"],
}

GENERIC_CATEGORY_NAMES = {
    "Assessments",
    "Assessment and Development Centers",
    "Behavioral Assessments",
    "Cognitive Assessments",
    "Job Focused Assessments",
    "Personality Assessment",
    "Skills & Simulations",
    "Virtual Assessment & Development Centers",
}


@dataclass
class PageRecord:
    url: str
    title: str
    breadcrumb_names: list[str]
    breadcrumb_urls: list[str]
    meta_description: str
    hero_text: str
    paragraphs: list[str]
    bullet_points: list[str]
    faq_questions: list[str]
    page_type: str
    slug: str
    category: str
    aliases: list[str]
    test_type: str
    categories: list[str]
    skills: list[str]
    job_levels: list[str]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "page"


def path_depth(url: str) -> int:
    return len([part for part in urlparse(url).path.split("/") if part])


def to_absolute_url(href: str) -> str:
    return urljoin(BASE_URL, href)


def should_visit(url: str) -> bool:
    if not url.startswith(ALLOWED_PREFIX):
        return False
    if any(fragment in url for fragment in ("#", "?")):
        return False
    if url.endswith("/rss/") or url.endswith(".pdf"):
        return False
    return True


def unique_texts(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = normalize_space(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def generate_aliases(name: str, title: str, url: str) -> list[str]:
    aliases: list[str] = []
    for source in (name, title):
        aliases.extend(re.findall(r"\b[A-Z]{2,6}\b", source))

    tail = urlparse(url).path.rstrip("/").split("/")[-1]
    aliases.append(tail.replace("-", " "))

    words = [
        word for word in re.findall(r"[A-Za-z]+", name)
        if word.lower() not in {"shl", "and"}
    ]
    has_explicit_acronym = any(alias.isupper() and 2 <= len(alias) <= 6 for alias in aliases)
    if not has_explicit_acronym and 2 <= len(words) <= 4:
        aliases.append("".join(word[0] for word in words).upper())

    return sorted({alias.strip() for alias in aliases if alias.strip()})


def infer_test_type(category: str, combined_text: str) -> str:
    lowered = f"{category} {combined_text}".lower()
    if "personality" in lowered:
        return "P"
    if any(keyword in lowered for keyword in ("behavioral", "situation judgement", "competency", "culture preview")):
        return "B"
    if any(keyword in lowered for keyword in ("cognitive", "reasoning", "verify", "ability")):
        return "C"
    if any(keyword in lowered for keyword in ("skill", "simulation", "coding", "technical", "job focused")):
        return "K"
    return "U"


def infer_skills(combined_text: str) -> list[str]:
    lowered = combined_text.lower()
    skills = [
        skill
        for skill, keywords in SKILL_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    ]
    return sorted(skills)


def infer_job_levels(combined_text: str) -> list[str]:
    lowered = combined_text.lower()
    levels = [
        level
        for level, keywords in JOB_LEVEL_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    ]
    return levels or ["entry", "mid", "senior"]


def extract_breadcrumbs(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    names: list[str] = []
    urls: list[str] = []
    for item in soup.select(".breadcrumbs__item"):
        link = item.select_one(".breadcrumbs__link")
        if not link:
            continue
        names.append(normalize_space(link.get_text(" ", strip=True)))
        href = link.get("href")
        if href:
            urls.append(to_absolute_url(href))
    return names, urls


def extract_text_blocks(soup: BeautifulSoup, selector: str) -> list[str]:
    return unique_texts(node.get_text(" ", strip=True) for node in soup.select(selector))


def extract_page_record(url: str, html: str) -> PageRecord:
    soup = BeautifulSoup(html, "html.parser")
    title = normalize_space(soup.title.get_text(" ", strip=True).replace("| SHL", "")) if soup.title else ""
    meta_description = ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag and meta_tag.get("content"):
        meta_description = normalize_space(meta_tag["content"])

    breadcrumb_names, breadcrumb_urls = extract_breadcrumbs(soup)
    hero_candidates = extract_text_blocks(soup, ".-banner-text, .banner-block p, .hero-banner p")
    hero_text = hero_candidates[0] if hero_candidates else meta_description

    paragraphs = [
        text for text in extract_text_blocks(soup, ".js-module .typ p")
        if len(text) > 50 and "cookie" not in text.lower()
    ]
    bullet_points = [
        text for text in extract_text_blocks(soup, ".js-module .typ li")
        if len(text) > 20
    ]
    faq_questions = extract_text_blocks(soup, ".faq__item-header-text")

    depth = path_depth(url)
    page_type = "detail" if depth >= 4 and len(breadcrumb_names) >= 4 else "category"
    name = breadcrumb_names[-1] if breadcrumb_names else title
    category = breadcrumb_names[-2] if len(breadcrumb_names) >= 2 else "Assessments"
    slug = slugify(name)

    combined_text = " ".join([name, title, meta_description, hero_text, *paragraphs, *bullet_points])
    aliases = generate_aliases(name=name, title=title, url=url)
    test_type = infer_test_type(category=category, combined_text=combined_text)
    categories = unique_texts([category, *breadcrumb_names[2:-1]])
    skills = infer_skills(combined_text)
    job_levels = infer_job_levels(combined_text)

    return PageRecord(
        url=url,
        title=title,
        breadcrumb_names=breadcrumb_names,
        breadcrumb_urls=breadcrumb_urls,
        meta_description=meta_description,
        hero_text=hero_text,
        paragraphs=paragraphs,
        bullet_points=bullet_points,
        faq_questions=faq_questions,
        page_type=page_type,
        slug=slug,
        category=category,
        aliases=aliases,
        test_type=test_type,
        categories=categories,
        skills=skills,
        job_levels=job_levels,
    )


def page_record_to_catalog_item(record: PageRecord) -> dict[str, object]:
    description_parts = [record.meta_description, record.hero_text]
    description = next((part for part in description_parts if part), "")
    return {
        "name": record.breadcrumb_names[-1] if record.breadcrumb_names else record.title,
        "url": record.url,
        "test_type": record.test_type,
        "description": description,
        "categories": record.categories,
        "skills": record.skills,
        "job_levels": record.job_levels,
        "aliases": record.aliases,
        "source_title": record.title,
        "hero_text": record.hero_text,
        "faq_questions": record.faq_questions,
    }


def save_raw_html(raw_dir: Path, record: PageRecord, html: str) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{record.slug}.html").write_text(html, encoding="utf-8")


def crawl(
    session: requests.Session,
    start_url: str,
    max_pages: int,
    delay: float,
    raw_dir: Path,
) -> tuple[list[PageRecord], list[str]]:
    queue: deque[str] = deque([start_url])
    visited: set[str] = set()
    discovered: list[str] = []
    records: list[PageRecord] = []
    page_links: dict[str, list[str]] = {}

    while queue and len(visited) < max_pages:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        response = session.get(url, timeout=30)
        response.raise_for_status()
        html = response.text
        record = extract_page_record(url, html)
        save_raw_html(raw_dir=raw_dir, record=record, html=html)
        records.append(record)
        discovered.append(url)

        soup = BeautifulSoup(html, "html.parser")
        links = []
        for link in soup.find_all("a", href=True):
            absolute = to_absolute_url(link["href"])
            if should_visit(absolute) and absolute not in visited:
                links.append(absolute)
        unique_links = unique_texts(links)
        page_links[url] = unique_links
        for next_url in unique_links:
            if next_url not in queue:
                queue.append(next_url)

        time.sleep(delay)

    return records, discovered, page_links


def is_detail_record(record: PageRecord, page_links: dict[str, list[str]]) -> bool:
    if path_depth(record.url) < 4:
        return False

    name = record.breadcrumb_names[-1] if record.breadcrumb_names else record.title
    if name in GENERIC_CATEGORY_NAMES:
        return False
    if "framework" in name.lower():
        return False

    current_path = urlparse(record.url).path.rstrip("/") + "/"
    for linked_url in page_links.get(record.url, []):
        linked_path = urlparse(linked_url).path.rstrip("/") + "/"
        if linked_path.startswith(current_path) and path_depth(linked_url) > path_depth(record.url):
            return False

    return True


def write_outputs(
    records: list[PageRecord],
    discovered_urls: list[str],
    page_links: dict[str, list[str]],
    raw_manifest_path: Path,
    processed_catalog_path: Path,
) -> None:
    raw_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    processed_catalog_path.parent.mkdir(parents=True, exist_ok=True)

    raw_payload = {
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "page_count": len(records),
        "urls": discovered_urls,
        "pages": [
            {
                "url": record.url,
                "title": record.title,
                "breadcrumbs": record.breadcrumb_names,
                "meta_description": record.meta_description,
                "hero_text": record.hero_text,
                "paragraphs": record.paragraphs,
                "bullet_points": record.bullet_points,
                "faq_questions": record.faq_questions,
                "page_type": record.page_type,
                "category": record.category,
                "linked_urls": page_links.get(record.url, []),
            }
            for record in records
        ],
    }
    raw_manifest_path.write_text(json.dumps(raw_payload, indent=2), encoding="utf-8")

    detail_records = [record for record in records if is_detail_record(record, page_links)]
    catalog_payload = [page_record_to_catalog_item(record) for record in detail_records]
    processed_catalog_path.write_text(json.dumps(catalog_payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape SHL assessment pages with requests + BeautifulSoup.")
    parser.add_argument("--start-url", default=START_URL, help="Starting SHL assessments URL.")
    parser.add_argument("--max-pages", type=int, default=80, help="Maximum number of pages to crawl.")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between requests in seconds.")
    parser.add_argument("--raw-dir", default="data/raw/shl_pages", help="Directory for raw HTML files.")
    parser.add_argument(
        "--raw-manifest",
        default="data/raw/shl_catalog_manifest.json",
        help="Path for the raw crawl manifest JSON.",
    )
    parser.add_argument(
        "--processed-catalog",
        default="data/processed/shl_catalog.json",
        help="Path for the normalized catalog JSON.",
    )
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    records, discovered_urls, page_links = crawl(
        session=session,
        start_url=args.start_url,
        max_pages=args.max_pages,
        delay=args.delay,
        raw_dir=Path(args.raw_dir),
    )
    write_outputs(
        records=records,
        discovered_urls=discovered_urls,
        page_links=page_links,
        raw_manifest_path=Path(args.raw_manifest),
        processed_catalog_path=Path(args.processed_catalog),
    )

    detail_count = sum(1 for record in records if is_detail_record(record, page_links))
    print(f"Visited {len(records)} pages and captured {detail_count} detail pages.")
    print(f"Raw manifest: {args.raw_manifest}")
    print(f"Processed catalog: {args.processed_catalog}")


if __name__ == "__main__":
    main()
