# -*- coding: UTF-8 -*-

import re
import env
from config.log import get_logger
from typing import Optional

logger = get_logger(__name__)

try:
    import trafilatura

    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    logger.warning(
        "trafilatura is not installed. Article extraction will use HTML fallback."
    )


def _strip_html_tags(html: str) -> str:
    """Basic HTML tag stripping as fallback when trafilatura is unavailable."""
    clean = re.sub(
        r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE
    )
    clean = re.sub(
        r"<style[^>]*>.*?</style>", " ", clean, flags=re.DOTALL | re.IGNORECASE
    )
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"&nbsp;", " ", clean)
    clean = re.sub(r"&amp;", "&", clean)
    clean = re.sub(r"&lt;", "<", clean)
    clean = re.sub(r"&gt;", ">", clean)
    clean = re.sub(r"&quot;", '"', clean)
    clean = re.sub(r"&#?\w+;", " ", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def _get_user_agent() -> str:
    """Get user-agent from env with fallback."""
    ua = getattr(env, "WASHING_USER_AGENT", None)
    if not ua:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    return ua


def extract_article(url: str, timeout: int = 30) -> dict:
    """Extract article content from URL using trafilatura with fallback.

    Args:
        url: The article URL to extract
        timeout: Request timeout in seconds

    Returns:
        dict with keys: url, title, markdown_content, html_content,
        extraction_method, metadata (dict with author, date, description, sitename)
    """
    result = {
        "url": url,
        "title": None,
        "markdown_content": "",
        "html_content": None,
        "extraction_method": "unknown",
        "metadata": {
            "author": None,
            "date": None,
            "description": None,
            "sitename": None,
        },
    }

    if TRAFILATURA_AVAILABLE:
        try:
            user_agent = _get_user_agent()
            downloaded = trafilatura.fetch_url(
                url,
                timeout=timeout,
                decode=True,
                user_agent=user_agent,
            )
            if downloaded is not None:
                # Extract markdown
                markdown = trafilatura.extract(
                    downloaded,
                    output_format="markdown",
                    include_tables=True,
                    include_links=True,
                    include_images=False,
                    with_metadata=True,
                    favor_precision=True,
                )
                if markdown and markdown.strip():
                    result["markdown_content"] = markdown.strip()
                    result["extraction_method"] = "trafilatura"

                # Extract HTML (XML) version
                try:
                    html_content = trafilatura.extract(
                        downloaded,
                        output_format="xml",
                        include_tables=True,
                        include_links=True,
                        include_images=False,
                        with_metadata=False,
                    )
                    if html_content and html_content.strip():
                        result["html_content"] = html_content.strip()
                except Exception:
                    # Fallback: use raw downloaded HTML
                    if isinstance(downloaded, str) and downloaded.strip():
                        result["html_content"] = downloaded.strip()
                    logger.debug(
                        "trafilatura XML extraction failed for %s, using raw HTML", url
                    )

                # Extract metadata
                try:
                    meta = trafilatura.extract_metadata(downloaded)
                    if meta:
                        result["metadata"]["author"] = getattr(meta, "author", None)
                        result["metadata"]["date"] = getattr(meta, "date", None)
                        result["metadata"]["description"] = getattr(
                            meta, "description", None
                        )
                        result["metadata"]["sitename"] = getattr(meta, "sitename", None)
                except Exception as exc:
                    logger.debug("Metadata extraction failed for %s: %s", url, exc)

                # Try to extract title from metadata if not yet set
                if result["markdown_content"] and not result["title"]:
                    try:
                        title_try = trafilatura.extract(
                            downloaded,
                            output_format="markdown",
                            include_tables=False,
                            include_links=False,
                            include_images=False,
                            with_metadata=False,
                        )
                        meta_only = trafilatura.extract_metadata(downloaded)
                        if meta_only and meta_only.title:
                            result["title"] = meta_only.title
                    except Exception:
                        pass

                if result["markdown_content"]:
                    logger.info(
                        "Extracted article from %s via trafilatura (%d chars)",
                        url,
                        len(result["markdown_content"]),
                    )
                    return result
        except Exception as exc:
            logger.warning("trafilatura extraction failed for %s: %s", url, exc)

    # Fallback: urllib + basic HTML text extraction
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={"User-Agent": _get_user_agent()},
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw_html = response.read().decode("utf-8", errors="replace")
            result["html_content"] = raw_html

            # Try to extract a title from <title> tag
            title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
            if title_match and not result["title"]:
                result["title"] = _strip_html_tags(title_match.group(1))

            text = _strip_html_tags(raw_html)
            if text:
                result["markdown_content"] = text
                result["extraction_method"] = "html_fallback"
                logger.info(
                    "Extracted article from %s via HTML fallback (%d chars)",
                    url,
                    len(result["markdown_content"]),
                )
                return result
    except Exception as exc:
        logger.error("Fallback extraction failed for %s: %s", url, exc)

    # Return partial result with whatever we managed to extract
    result["extraction_method"] = "failed"
    logger.error("All extraction methods failed for %s", url)
    return result
