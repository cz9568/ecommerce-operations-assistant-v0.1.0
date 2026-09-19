import inspect
import ipaddress
import json
import re
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from backend.app.api.schemas.competitors import (
    CompetitorCreate,
    CompetitorUpdate,
    MonitorUpsert,
    ParseTaskApply,
    ParseTaskCreate,
    SnapshotApply,
)
from backend.app.config import Settings, get_settings
from backend.app.errors import AppError
from backend.app.models.entities import (
    Competitor,
    CompetitorMonitor,
    CompetitorMonitorSnapshot,
    PublicLinkParseTask,
    User,
)
from backend.app.services.audit import add_audit_log
from backend.app.services.products import get_product_or_error
from backend.app.services.settings import resolve_runtime_settings

COMPETITOR_FIELDS = (
    "name",
    "url",
    "price",
    "sales_hint",
    "title",
    "main_image",
    "selling_points",
    "review_keywords",
)
PARSED_FIELDS = (
    "price",
    "sales_hint",
    "title",
    "main_image",
    "selling_points",
    "review_keywords",
)


class ParseFailure(Exception):
    def __init__(self, code: str, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self._script_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name")).lower()
            content = values.get("content", "").strip()
            if key and content:
                self.meta[key] = content
        if tag.lower() == "script" and values.get("type", "").lower() == "application/ld+json":
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False
        if tag.lower() == "script" and self._script_parts is not None:
            self.json_ld.append("".join(self._script_parts))
            self._script_parts = None

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self._script_parts is not None:
            self._script_parts.append(data)


def _now() -> datetime:
    return datetime.now(UTC)


def _domain_allowed(hostname: str) -> bool:
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in get_settings().competitor_allowed_domains
    )


def validate_public_url(url: str, *, resolve_host: bool = False) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AppError(422, "PUBLIC_URL_INVALID", "仅支持公开的 HTTP(S) 商品链接")
    if parsed.username or parsed.password:
        raise AppError(422, "PUBLIC_URL_INVALID", "公开链接不能包含账号凭证")
    if parsed.port not in {None, 80, 443}:
        raise AppError(422, "PUBLIC_URL_PORT_BLOCKED", "公开链接仅允许标准 HTTP(S) 端口")
    hostname = parsed.hostname.lower().rstrip(".")
    if not _domain_allowed(hostname):
        raise AppError(
            422,
            "PUBLIC_URL_DOMAIN_NOT_ALLOWED",
            "该域名不在公开链接解析白名单中",
            details={"hostname": hostname},
        )
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and not literal_ip.is_global:
        raise AppError(422, "PUBLIC_URL_PRIVATE_ADDRESS", "禁止访问内网或保留地址")
    if resolve_host:
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port or 443)}
        except OSError as exc:
            raise AppError(422, "PUBLIC_URL_DNS_FAILED", "公开链接域名解析失败") from exc
        if not addresses or any(
            not ipaddress.ip_address(address).is_global for address in addresses
        ):
            raise AppError(422, "PUBLIC_URL_PRIVATE_ADDRESS", "域名解析到了内网或保留地址")
    return url


def _normalize_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized[:limit] or None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    match = re.search(r"\d+(?:\.\d{1,2})?", str(value).replace(",", ""))
    if not match:
        return None
    try:
        amount = Decimal(match.group(0)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return amount if amount >= 0 else None


def _json_safe_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, Decimal) else value for key, value in result.items()
    }


def _walk_json_ld(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        result = [value]
        for child in value.values():
            result.extend(_walk_json_ld(child))
        return result
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(_walk_json_ld(child))
        return result
    return []


def _extract_metadata(html: str) -> dict[str, Any]:
    parser = _MetadataParser()
    parser.feed(html)
    title = _normalize_text(parser.meta.get("og:title") or "".join(parser.title_parts), 500)
    image = _normalize_text(parser.meta.get("og:image"), 2048)
    description = _normalize_text(
        parser.meta.get("og:description") or parser.meta.get("description"), 10000
    )
    price = _decimal(
        parser.meta.get("product:price:amount")
        or parser.meta.get("og:price:amount")
        or parser.meta.get("price")
    )
    sales_hint = None
    for raw in parser.json_ld:
        try:
            values = _walk_json_ld(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue
        for value in values:
            value_type = value.get("@type")
            if isinstance(value_type, list):
                is_product = "Product" in value_type
            else:
                is_product = value_type == "Product"
            if is_product:
                title = title or _normalize_text(value.get("name"), 500)
                description = description or _normalize_text(value.get("description"), 10000)
                raw_image = value.get("image")
                if isinstance(raw_image, list):
                    raw_image = raw_image[0] if raw_image else None
                image = image or _normalize_text(raw_image, 2048)
                offers = value.get("offers")
                if isinstance(offers, list):
                    offers = offers[0] if offers else None
                if isinstance(offers, dict):
                    price = price or _decimal(offers.get("price") or offers.get("lowPrice"))
            if not sales_hint:
                sales_hint = _normalize_text(
                    value.get("sales") or value.get("soldCount") or value.get("salesVolume"),
                    255,
                )
    return {
        "title": title,
        "price": price,
        "sales_hint": sales_hint,
        "main_image": image,
        "selling_points": description,
        "review_keywords": None,
    }


def _fetch_public_metadata(
    source_url: str, *, settings: Settings | None = None
) -> tuple[dict[str, Any], str, int]:
    settings = settings or get_settings()
    current_url = source_url
    headers = {
        "User-Agent": "EcommerceOperationsAssistant/0.1 public-metadata-fetcher",
        "Accept": "text/html,application/xhtml+xml",
    }
    timeout = httpx.Timeout(settings.competitor_parse_timeout_seconds)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
            for redirect_count in range(settings.competitor_parse_max_redirects + 1):
                validate_public_url(current_url, resolve_host=True)
                with client.stream("GET", current_url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise ParseFailure("REDIRECT_INVALID", "公开链接返回了无目标的重定向")
                        if redirect_count >= settings.competitor_parse_max_redirects:
                            raise ParseFailure("TOO_MANY_REDIRECTS", "公开链接重定向次数过多")
                        current_url = urljoin(current_url, location)
                        validate_public_url(current_url)
                        continue
                    if response.status_code in {401, 403}:
                        raise ParseFailure(
                            "ACCESS_RESTRICTED",
                            "页面需要登录或拒绝公开访问，系统不会绕过访问控制",
                            http_status=response.status_code,
                        )
                    if response.status_code >= 400:
                        raise ParseFailure(
                            "UPSTREAM_HTTP_ERROR",
                            f"公开页面返回 HTTP {response.status_code}",
                            http_status=response.status_code,
                        )
                    content_type = response.headers.get("content-type", "").lower()
                    if (
                        "text/html" not in content_type
                        and "application/xhtml+xml" not in content_type
                    ):
                        raise ParseFailure("CONTENT_TYPE_UNSUPPORTED", "公开链接不是 HTML 页面")
                    length = response.headers.get("content-length")
                    if length and int(length) > settings.competitor_parse_max_bytes:
                        raise ParseFailure("RESPONSE_TOO_LARGE", "公开页面超过允许的响应大小")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > settings.competitor_parse_max_bytes:
                            raise ParseFailure("RESPONSE_TOO_LARGE", "公开页面超过允许的响应大小")
                    text = bytes(content).decode(response.encoding or "utf-8", errors="replace")
                    lowered = text[:200_000].lower()
                    restricted_words = ("captcha", "验证码", "人机验证", "请登录", "扫码登录")
                    if any(word in lowered for word in restricted_words):
                        raise ParseFailure(
                            "CHALLENGE_OR_LOGIN_REQUIRED",
                            "页面出现登录或验证码，系统不会尝试绕过",
                            http_status=response.status_code,
                        )
                    result = _extract_metadata(text)
                    if not any(result.values()):
                        raise ParseFailure("NO_PUBLIC_METADATA", "页面未提供可识别的公开商品字段")
                    return result, str(response.url), response.status_code
    except AppError as exc:
        raise ParseFailure(exc.code, exc.message) from exc
    except httpx.TimeoutException as exc:
        raise ParseFailure("FETCH_TIMEOUT", "公开链接访问超时") from exc
    except httpx.NetworkError as exc:
        raise ParseFailure("FETCH_NETWORK_ERROR", "公开链接网络访问失败") from exc
    raise ParseFailure("FETCH_FAILED", "公开链接解析失败")


def _fetch_with_runtime_settings(
    source_url: str, session: Session
) -> tuple[dict[str, Any], str, int]:
    """Apply database overrides while keeping one-argument test doubles compatible."""
    if len(inspect.signature(_fetch_public_metadata).parameters) == 1:
        return _fetch_public_metadata(source_url)
    return _fetch_public_metadata(source_url, settings=resolve_runtime_settings(session))


def _competitor_response(competitor: Competitor) -> dict[str, Any]:
    return {
        "id": competitor.id,
        "product_id": competitor.product_id,
        "name": competitor.name,
        "platform": competitor.platform,
        "url": competitor.url,
        "price": competitor.price,
        "sales_hint": competitor.sales_hint,
        "title": competitor.title,
        "main_image": competitor.main_image,
        "selling_points": competitor.selling_points,
        "review_keywords": competitor.review_keywords,
        "status": competitor.status,
        "field_sources": competitor.field_sources_json or {},
        "last_parsed_at": competitor.last_parsed_at,
        "created_at": competitor.created_at,
        "updated_at": competitor.updated_at,
    }


def get_competitor_or_error(session: Session, *, product_id: int, competitor_id: int) -> Competitor:
    get_product_or_error(session, product_id)
    competitor = session.scalar(
        select(Competitor).where(
            Competitor.id == competitor_id, Competitor.product_id == product_id
        )
    )
    if competitor is None:
        raise AppError(404, "COMPETITOR_NOT_FOUND", "竞品不存在或不属于该商品")
    return competitor


def list_competitors(
    session: Session,
    *,
    product_id: int,
    page: int,
    page_size: int,
    status: str | None,
    platform: str | None,
    query: str | None,
) -> tuple[list[dict[str, Any]], int]:
    get_product_or_error(session, product_id)
    filters = [Competitor.product_id == product_id]
    if status:
        filters.append(Competitor.status == status)
    if platform:
        filters.append(Competitor.platform == platform)
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(or_(Competitor.name.like(pattern), Competitor.title.like(pattern)))
    total = session.scalar(select(func.count(Competitor.id)).where(*filters)) or 0
    items = session.scalars(
        select(Competitor)
        .where(*filters)
        .order_by(Competitor.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_competitor_response(item) for item in items], int(total)


def create_competitor(
    session: Session,
    *,
    product_id: int,
    payload: CompetitorCreate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    get_product_or_error(session, product_id)
    if payload.url:
        validate_public_url(payload.url)
    sources = {
        field: "manual"
        for field, value in payload.model_dump().items()
        if field in COMPETITOR_FIELDS and value is not None
    }
    competitor = Competitor(
        product_id=product_id,
        **payload.model_dump(),
        field_sources_json=sources,
    )
    session.add(competitor)
    session.flush()
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="competitor.create",
        target_type="competitor",
        target_id=competitor.id,
        request_id=request_id,
        detail={"product_id": product_id},
    )
    session.commit()
    session.refresh(competitor)
    return _competitor_response(competitor)


def update_competitor(
    session: Session,
    *,
    product_id: int,
    competitor_id: int,
    payload: CompetitorUpdate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    competitor = get_competitor_or_error(
        session, product_id=product_id, competitor_id=competitor_id
    )
    data = payload.model_dump(exclude_unset=True)
    if "url" in data and data["url"]:
        validate_public_url(data["url"])
    sources = dict(competitor.field_sources_json or {})
    for field, value in data.items():
        setattr(competitor, field, value)
        if field in COMPETITOR_FIELDS:
            sources[field] = "manual"
    competitor.field_sources_json = sources
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="competitor.update",
        target_type="competitor",
        target_id=competitor.id,
        request_id=request_id,
        detail={"product_id": product_id, "changed_fields": sorted(data)},
    )
    session.commit()
    session.refresh(competitor)
    return _competitor_response(competitor)


def archive_competitor(
    session: Session,
    *,
    product_id: int,
    competitor_id: int,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    competitor = get_competitor_or_error(
        session, product_id=product_id, competitor_id=competitor_id
    )
    competitor.status = "inactive"
    monitor = session.scalar(
        select(CompetitorMonitor).where(CompetitorMonitor.competitor_id == competitor.id)
    )
    if monitor:
        monitor.monitor_status = "paused"
        monitor.next_run_at = None
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="competitor.archive",
        target_type="competitor",
        target_id=competitor.id,
        request_id=request_id,
        detail={"product_id": product_id},
    )
    session.commit()
    session.refresh(competitor)
    return _competitor_response(competitor)


def _task_response(task: PublicLinkParseTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "product_id": task.product_id,
        "competitor_id": task.competitor_id,
        "source_url": task.source_url,
        "task_status": task.task_status,
        "attempts": task.attempts,
        "max_attempts": task.max_attempts,
        "result": task.result_json,
        "final_url": task.final_url,
        "http_status": task.http_status,
        "error_code": task.error_code,
        "error_message": task.error_message,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "applied_at": task.applied_at,
        "applied_by": task.applied_by,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def get_parse_task_or_error(
    session: Session, *, product_id: int, task_id: int
) -> PublicLinkParseTask:
    get_product_or_error(session, product_id)
    task = session.scalar(
        select(PublicLinkParseTask).where(
            PublicLinkParseTask.id == task_id,
            PublicLinkParseTask.product_id == product_id,
        )
    )
    if task is None:
        raise AppError(404, "LINK_PARSE_TASK_NOT_FOUND", "公开链接解析任务不存在或不属于该商品")
    return task


def create_parse_task(
    session: Session,
    *,
    product_id: int,
    payload: ParseTaskCreate,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    get_product_or_error(session, product_id)
    validate_public_url(payload.source_url)
    if payload.competitor_id is not None:
        get_competitor_or_error(session, product_id=product_id, competitor_id=payload.competitor_id)
    task = PublicLinkParseTask(
        product_id=product_id,
        competitor_id=payload.competitor_id,
        source_url=payload.source_url,
        task_status="pending",
        attempts=0,
        max_attempts=3,
    )
    session.add(task)
    session.flush()
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="link_parse_task.create",
        target_type="public_link_parse_task",
        target_id=task.id,
        request_id=request_id,
        detail={"product_id": product_id, "competitor_id": payload.competitor_id},
    )
    session.commit()
    session.refresh(task)
    return _task_response(task)


def list_parse_tasks(
    session: Session,
    *,
    product_id: int,
    page: int,
    page_size: int,
    status: str | None,
) -> tuple[list[dict[str, Any]], int]:
    get_product_or_error(session, product_id)
    filters = [PublicLinkParseTask.product_id == product_id]
    if status:
        filters.append(PublicLinkParseTask.task_status == status)
    total = session.scalar(select(func.count(PublicLinkParseTask.id)).where(*filters)) or 0
    tasks = session.scalars(
        select(PublicLinkParseTask)
        .where(*filters)
        .order_by(PublicLinkParseTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_task_response(task) for task in tasks], int(total)


def run_parse_task(
    session: Session,
    *,
    product_id: int,
    task_id: int,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    task = get_parse_task_or_error(session, product_id=product_id, task_id=task_id)
    if task.task_status == "running":
        raise AppError(409, "LINK_PARSE_TASK_RUNNING", "公开链接解析任务正在执行")
    if task.attempts >= task.max_attempts:
        raise AppError(409, "LINK_PARSE_RETRY_EXHAUSTED", "公开链接解析任务已达到最大尝试次数")
    task.task_status = "running"
    task.attempts += 1
    task.started_at = _now()
    task.finished_at = None
    task.error_code = None
    task.error_message = None
    task.result_json = None
    session.commit()
    try:
        result, final_url, http_status = _fetch_with_runtime_settings(task.source_url, session)
        task.result_json = _json_safe_result(result)
        task.final_url = final_url
        task.http_status = http_status
        task.task_status = "succeeded"
    except ParseFailure as exc:
        task.task_status = "failed"
        task.error_code = exc.code
        task.error_message = exc.message
        task.http_status = exc.http_status
    task.finished_at = _now()
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="link_parse_task.run",
        target_type="public_link_parse_task",
        target_id=task.id,
        request_id=request_id,
        detail={
            "status": task.task_status,
            "attempts": task.attempts,
            "error_code": task.error_code,
        },
    )
    session.commit()
    session.refresh(task)
    return _task_response(task)


def _infer_platform(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    mappings = {
        "taobao.com": "taobao",
        "tmall.com": "tmall",
        "jd.com": "jd",
        "pinduoduo.com": "pinduoduo",
        "douyin.com": "douyin",
        "kuaishou.com": "kuaishou",
        "xiaohongshu.com": "xiaohongshu",
        "weixin.qq.com": "wechat",
    }
    return next((value for domain, value in mappings.items() if host.endswith(domain)), "other")


def apply_parse_task(
    session: Session,
    *,
    product_id: int,
    task_id: int,
    payload: ParseTaskApply,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    task = get_parse_task_or_error(session, product_id=product_id, task_id=task_id)
    if task.task_status != "succeeded" or not task.result_json:
        raise AppError(409, "LINK_PARSE_RESULT_UNAVAILABLE", "只有成功任务的解析结果可以回填")
    target_id = payload.competitor_id or task.competitor_id
    if target_id is None:
        name = payload.name or task.result_json.get("title")
        if not name:
            raise AppError(422, "COMPETITOR_NAME_REQUIRED", "创建竞品时需要提供竞品名称")
        competitor = Competitor(
            product_id=product_id,
            name=name,
            platform=payload.platform or _infer_platform(task.final_url or task.source_url),
            status="active",
            field_sources_json={"name": "parsed" if payload.name is None else "manual"},
        )
        session.add(competitor)
        session.flush()
        task.competitor_id = competitor.id
    else:
        competitor = get_competitor_or_error(
            session, product_id=product_id, competitor_id=target_id
        )
    sources = dict(competitor.field_sources_json or {})
    applied_fields: list[str] = []
    for field in payload.fields:
        if field == "url":
            value = task.final_url or task.source_url
        elif field == "name":
            value = payload.name or task.result_json.get("title")
        else:
            value = task.result_json.get(field)
        if value is not None:
            setattr(competitor, field, value)
            sources[field] = "parsed"
            applied_fields.append(field)
    if not applied_fields:
        raise AppError(422, "PARSE_FIELDS_EMPTY", "所选字段没有可回填的解析结果")
    competitor.field_sources_json = sources
    competitor.last_parsed_at = _now()
    task.applied_at = _now()
    task.applied_by = actor.id
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="link_parse_task.apply",
        target_type="competitor",
        target_id=competitor.id,
        request_id=request_id,
        detail={"task_id": task.id, "applied_fields": applied_fields},
    )
    session.commit()
    session.refresh(competitor)
    return _competitor_response(competitor)


def _monitor_response(monitor: CompetitorMonitor) -> dict[str, Any]:
    return {
        "id": monitor.id,
        "competitor_id": monitor.competitor_id,
        "monitor_status": monitor.monitor_status,
        "interval_minutes": monitor.interval_minutes,
        "next_run_at": monitor.next_run_at,
        "last_error": monitor.last_error,
        "last_error_code": monitor.last_error_code,
        "consecutive_failures": monitor.consecutive_failures,
        "last_run_at": monitor.last_run_at,
        "last_success_at": monitor.last_success_at,
        "created_at": monitor.created_at,
        "updated_at": monitor.updated_at,
    }


def get_monitor_or_error(
    session: Session, *, product_id: int, competitor_id: int
) -> CompetitorMonitor:
    competitor = get_competitor_or_error(
        session, product_id=product_id, competitor_id=competitor_id
    )
    monitor = session.scalar(
        select(CompetitorMonitor).where(CompetitorMonitor.competitor_id == competitor.id)
    )
    if monitor is None:
        raise AppError(404, "COMPETITOR_MONITOR_NOT_FOUND", "竞品监控尚未配置")
    return monitor


def upsert_monitor(
    session: Session,
    *,
    product_id: int,
    competitor_id: int,
    payload: MonitorUpsert,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    competitor = get_competitor_or_error(
        session, product_id=product_id, competitor_id=competitor_id
    )
    if competitor.status != "active":
        raise AppError(409, "COMPETITOR_INACTIVE", "停用竞品不能启用监控")
    if not competitor.url:
        raise AppError(409, "COMPETITOR_URL_REQUIRED", "配置监控前需要填写公开链接")
    validate_public_url(competitor.url)
    monitor = session.scalar(
        select(CompetitorMonitor).where(CompetitorMonitor.competitor_id == competitor.id)
    )
    if monitor is None:
        monitor = CompetitorMonitor(competitor_id=competitor.id)
        session.add(monitor)
    monitor.monitor_status = payload.monitor_status
    monitor.interval_minutes = payload.interval_minutes
    monitor.next_run_at = _now() if payload.monitor_status == "active" else None
    if payload.monitor_status == "active":
        monitor.last_error = None
        monitor.last_error_code = None
        monitor.consecutive_failures = 0
    session.flush()
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="competitor_monitor.upsert",
        target_type="competitor_monitor",
        target_id=monitor.id,
        request_id=request_id,
        detail={"product_id": product_id, "status": payload.monitor_status},
    )
    session.commit()
    session.refresh(monitor)
    return _monitor_response(monitor)


def get_monitor(session: Session, *, product_id: int, competitor_id: int) -> dict[str, Any]:
    return _monitor_response(
        get_monitor_or_error(session, product_id=product_id, competitor_id=competitor_id)
    )


def _snapshot_response(snapshot: CompetitorMonitorSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "monitor_id": snapshot.monitor_id,
        "price": snapshot.price,
        "sales_hint": snapshot.sales_hint,
        "title": snapshot.title,
        "main_image": snapshot.main_image,
        "selling_points": snapshot.selling_points,
        "review_keywords": snapshot.review_keywords,
        "source_url": snapshot.source_url,
        "changed_fields": snapshot.changed_fields_json or [],
        "is_success": snapshot.is_success,
        "error_code": snapshot.error_code,
        "error_message": snapshot.error_message,
        "created_at": snapshot.created_at,
    }


def list_snapshots(
    session: Session,
    *,
    product_id: int,
    competitor_id: int,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    monitor = get_monitor_or_error(session, product_id=product_id, competitor_id=competitor_id)
    total = (
        session.scalar(
            select(func.count(CompetitorMonitorSnapshot.id)).where(
                CompetitorMonitorSnapshot.monitor_id == monitor.id
            )
        )
        or 0
    )
    snapshots = session.scalars(
        select(CompetitorMonitorSnapshot)
        .where(CompetitorMonitorSnapshot.monitor_id == monitor.id)
        .order_by(CompetitorMonitorSnapshot.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [_snapshot_response(snapshot) for snapshot in snapshots], int(total)


def _changed_fields(
    previous: CompetitorMonitorSnapshot | None, result: dict[str, Any]
) -> list[str]:
    if previous is None:
        return [field for field in PARSED_FIELDS if result.get(field) is not None]
    return [field for field in PARSED_FIELDS if result.get(field) != getattr(previous, field)]


def _claim_monitor(session: Session, monitor_id: int, *, force: bool) -> str | None:
    now = _now()
    token = uuid4().hex
    conditions = [CompetitorMonitor.id == monitor_id]
    if not force:
        conditions.extend(
            [
                CompetitorMonitor.monitor_status == "active",
                CompetitorMonitor.next_run_at <= now,
            ]
        )
    conditions.append(
        or_(CompetitorMonitor.lock_token.is_(None), CompetitorMonitor.locked_until < now)
    )
    result = session.execute(
        update(CompetitorMonitor)
        .where(*conditions)
        .values(lock_token=token, locked_until=now + timedelta(minutes=5))
    )
    session.commit()
    return token if result.rowcount == 1 else None


def run_monitor(
    session: Session,
    *,
    product_id: int,
    competitor_id: int,
    force: bool = True,
) -> dict[str, Any]:
    competitor = get_competitor_or_error(
        session, product_id=product_id, competitor_id=competitor_id
    )
    monitor = get_monitor_or_error(session, product_id=product_id, competitor_id=competitor_id)
    token = _claim_monitor(session, monitor.id, force=force)
    if token is None:
        raise AppError(409, "COMPETITOR_MONITOR_BUSY", "竞品监控正在执行或尚未到期")
    session.refresh(monitor)
    now = _now()
    monitor.last_run_at = now
    previous = session.scalar(
        select(CompetitorMonitorSnapshot)
        .where(
            CompetitorMonitorSnapshot.monitor_id == monitor.id,
            CompetitorMonitorSnapshot.is_success.is_(True),
        )
        .order_by(CompetitorMonitorSnapshot.id.desc())
        .limit(1)
    )
    try:
        if competitor.status != "active" or not competitor.url:
            raise ParseFailure("COMPETITOR_NOT_MONITORABLE", "竞品已停用或未填写公开链接")
        result, final_url, _http_status = _fetch_with_runtime_settings(competitor.url, session)
        snapshot = CompetitorMonitorSnapshot(
            monitor_id=monitor.id,
            source_url=final_url,
            changed_fields_json=_changed_fields(previous, result),
            is_success=True,
            raw_payload_json=_json_safe_result(result),
            **result,
        )
        monitor.monitor_status = "active"
        monitor.consecutive_failures = 0
        monitor.last_error = None
        monitor.last_error_code = None
        monitor.last_success_at = now
        monitor.next_run_at = now + timedelta(minutes=monitor.interval_minutes)
    except ParseFailure as exc:
        failures = monitor.consecutive_failures + 1
        snapshot = CompetitorMonitorSnapshot(
            monitor_id=monitor.id,
            source_url=competitor.url,
            changed_fields_json=[],
            is_success=False,
            error_code=exc.code,
            error_message=exc.message,
            raw_payload_json=None,
        )
        monitor.consecutive_failures = failures
        monitor.last_error = exc.message
        monitor.last_error_code = exc.code
        monitor.monitor_status = "failed" if failures >= 3 else "active"
        backoff = min(2**failures, 16)
        monitor.next_run_at = now + timedelta(minutes=monitor.interval_minutes * backoff)
    monitor.lock_token = None
    monitor.locked_until = None
    session.add(snapshot)
    session.commit()
    session.refresh(monitor)
    return _monitor_response(monitor)


def run_due_monitors(session: Session, *, limit: int) -> dict[str, int]:
    now = _now()
    monitor_ids = session.scalars(
        select(CompetitorMonitor.id)
        .where(
            CompetitorMonitor.monitor_status == "active",
            CompetitorMonitor.next_run_at <= now,
            or_(CompetitorMonitor.lock_token.is_(None), CompetitorMonitor.locked_until < now),
        )
        .order_by(CompetitorMonitor.next_run_at.asc())
        .limit(limit)
    ).all()
    summary = {
        "due_count": len(monitor_ids),
        "claimed_count": 0,
        "succeeded_count": 0,
        "failed_count": 0,
    }
    for monitor_id in monitor_ids:
        row = session.execute(
            select(CompetitorMonitor, Competitor)
            .join(Competitor, Competitor.id == CompetitorMonitor.competitor_id)
            .where(CompetitorMonitor.id == monitor_id)
        ).one()
        try:
            result = run_monitor(
                session,
                product_id=row.Competitor.product_id,
                competitor_id=row.Competitor.id,
                force=False,
            )
            summary["claimed_count"] += 1
            if result["last_error_code"]:
                summary["failed_count"] += 1
            else:
                summary["succeeded_count"] += 1
        except AppError as exc:
            if exc.code != "COMPETITOR_MONITOR_BUSY":
                raise
    return summary


def apply_snapshot(
    session: Session,
    *,
    product_id: int,
    competitor_id: int,
    snapshot_id: int,
    payload: SnapshotApply,
    actor: User,
    request_id: str | None,
) -> dict[str, Any]:
    competitor = get_competitor_or_error(
        session, product_id=product_id, competitor_id=competitor_id
    )
    monitor = get_monitor_or_error(session, product_id=product_id, competitor_id=competitor_id)
    snapshot = session.scalar(
        select(CompetitorMonitorSnapshot).where(
            CompetitorMonitorSnapshot.id == snapshot_id,
            CompetitorMonitorSnapshot.monitor_id == monitor.id,
        )
    )
    if snapshot is None:
        raise AppError(404, "MONITOR_SNAPSHOT_NOT_FOUND", "竞品监控快照不存在")
    if not snapshot.is_success:
        raise AppError(409, "MONITOR_SNAPSHOT_FAILED", "失败快照不能回填")
    sources = dict(competitor.field_sources_json or {})
    applied_fields = []
    for field in payload.fields:
        if field not in PARSED_FIELDS:
            continue
        value = getattr(snapshot, field)
        if value is not None:
            setattr(competitor, field, value)
            sources[field] = "monitor"
            applied_fields.append(field)
    if not applied_fields:
        raise AppError(422, "SNAPSHOT_FIELDS_EMPTY", "所选字段在快照中没有值")
    competitor.field_sources_json = sources
    competitor.last_parsed_at = snapshot.created_at
    add_audit_log(
        session,
        actor_user_id=actor.id,
        action="competitor_monitor_snapshot.apply",
        target_type="competitor",
        target_id=competitor.id,
        request_id=request_id,
        detail={"snapshot_id": snapshot.id, "applied_fields": applied_fields},
    )
    session.commit()
    session.refresh(competitor)
    return _competitor_response(competitor)
