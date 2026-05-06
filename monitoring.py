import os
import smtplib
import socket
import sys
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import pygsheets


DEFAULT_SHEET_ID = "1wPXr5FMHpbzhYCIDPpsEvIwIXNoz2Bgm0ozNaHALAQA"
DEFAULT_EMAIL_TO = "bo.huang@omc.com"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

RUNS_HEADERS = [
    "run_id",
    "job_name",
    "script",
    "status",
    "start_time_taipei",
    "end_time_taipei",
    "duration_seconds",
    "date_taipei",
    "error_message",
    "cloud_run_execution",
    "updated_at_taipei",
]

LATEST_HEADERS = [
    "job_name",
    "script",
    "latest_status",
    "latest_start_time_taipei",
    "latest_end_time_taipei",
    "latest_duration_seconds",
    "latest_error_message",
    "cloud_run_execution",
    "updated_at_taipei",
]


@dataclass
class RunState:
    run_id: str
    job_name: str
    script: str
    start_time: datetime
    execution: str


def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ)


def fmt(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def date_taipei(dt: datetime) -> str:
    return dt.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_job_name(script: str) -> str:
    return (
        os.environ.get("CLOUD_RUN_JOB")
        or os.environ.get("K_SERVICE")
        or os.environ.get("JOB_NAME")
        or Path(script).stem
    )


def get_execution_name() -> str:
    return (
        os.environ.get("CLOUD_RUN_EXECUTION")
        or os.environ.get("CLOUD_RUN_TASK_INDEX")
        or os.environ.get("EXECUTION_NAME")
        or ""
    )


def get_service_file() -> Optional[str]:
    candidates = [
        os.environ.get("MONITOR_SERVICE_ACCOUNT_FILE"),
        "/app/eco-carver-356809-a5ccbfde00b9.json",
        "/app/eco-carver-356809-38c8914cd90f.json",
        "eco-carver-356809-a5ccbfde00b9.json",
        "eco-carver-356809-38c8914cd90f.json",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def get_sheet():
    sheet_id = os.environ.get("MONITOR_SHEET_ID", DEFAULT_SHEET_ID)
    service_file = get_service_file()
    if not service_file:
        raise FileNotFoundError("No monitor service account JSON file found")

    client = pygsheets.authorize(service_file=service_file)
    return client.open_by_key(sheet_id)


def get_or_create_worksheet(spreadsheet, title: str, headers: list[str]):
    try:
        worksheet = spreadsheet.worksheet_by_title(title)
    except pygsheets.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))

    values = worksheet.get_values("A1", (1, len(headers)), include_tailing_empty=False)
    current_headers = values[0] if values else []
    if current_headers != headers:
        worksheet.update_values("A1", [headers])
    return worksheet


def find_row_by_value(worksheet, column: int, value: str) -> Optional[int]:
    values = worksheet.get_col(column, include_tailing_empty=False)
    for index, cell in enumerate(values, start=1):
        if index == 1:
            continue
        if cell == value:
            return index
    return None


def append_or_update_by_key(worksheet, key_column: int, key_value: str, row: list[str]) -> None:
    row_number = find_row_by_value(worksheet, key_column, key_value)
    if row_number:
        worksheet.update_values(f"A{row_number}", [row])
    else:
        worksheet.append_table(values=[row], start="A1", dimension="ROWS", overwrite=False)


def write_sheet_status(state: RunState, status: str, end_time: Optional[datetime], error_message: str = "") -> None:
    spreadsheet = get_sheet()
    runs_title = os.environ.get("MONITOR_RUNS_WORKSHEET", "runs")
    latest_title = os.environ.get("MONITOR_LATEST_WORKSHEET", "latest_status")
    runs_ws = get_or_create_worksheet(spreadsheet, runs_title, RUNS_HEADERS)
    latest_ws = get_or_create_worksheet(spreadsheet, latest_title, LATEST_HEADERS)

    updated_at = now_taipei()
    duration = ""
    if end_time:
        duration = str(round((end_time - state.start_time).total_seconds(), 2))

    runs_row = [
        state.run_id,
        state.job_name,
        state.script,
        status,
        fmt(state.start_time),
        fmt(end_time),
        duration,
        date_taipei(state.start_time),
        error_message[:4500],
        state.execution,
        fmt(updated_at),
    ]
    latest_row = [
        state.job_name,
        state.script,
        status,
        fmt(state.start_time),
        fmt(end_time),
        duration,
        error_message[:4500],
        state.execution,
        fmt(updated_at),
    ]

    append_or_update_by_key(runs_ws, 1, state.run_id, runs_row)
    append_or_update_by_key(latest_ws, 1, state.job_name, latest_row)


def safe_write_sheet_status(state: RunState, status: str, end_time: Optional[datetime], error_message: str = "") -> None:
    try:
        write_sheet_status(state, status, end_time, error_message)
    except Exception as exc:
        print(f"[monitoring] Failed to write Google Sheet status: {exc}", file=sys.stderr)


def start_run(script: str) -> RunState:
    start_time = now_taipei()
    state = RunState(
        run_id=os.environ.get("RUN_ID") or f"{start_time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}",
        job_name=get_job_name(script),
        script=script,
        start_time=start_time,
        execution=get_execution_name(),
    )
    safe_write_sheet_status(state, "RUNNING", None)
    return state


def send_email(subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST")
    if not host:
        print("[monitoring] SMTP_HOST is not set; email notification skipped", file=sys.stderr)
        return

    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM") or username or DEFAULT_EMAIL_TO
    recipients = [
        recipient.strip()
        for recipient in os.environ.get("MONITOR_EMAIL_TO", DEFAULT_EMAIL_TO).split(",")
        if recipient.strip()
    ]

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)

    timeout = int(os.environ.get("SMTP_TIMEOUT", "20"))
    use_tls = env_bool("SMTP_USE_TLS", True)

    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)


def safe_send_failure_email(state: RunState, error_message: str, end_time: datetime) -> None:
    if not env_bool("MONITOR_EMAIL_ON_FAILURE", True):
        return

    subject = f"[HAN Cloud Run] FAILED - {state.job_name} / {state.script}"
    body = "\n".join(
        [
            "HAN Cloud Run job failed.",
            "",
            f"Job: {state.job_name}",
            f"Script: {state.script}",
            f"Run ID: {state.run_id}",
            f"Execution: {state.execution}",
            f"Host: {socket.gethostname()}",
            f"Start time: {fmt(state.start_time)}",
            f"End time: {fmt(end_time)}",
            f"Duration seconds: {round((end_time - state.start_time).total_seconds(), 2)}",
            "",
            "Error:",
            error_message,
        ]
    )

    try:
        send_email(subject, body)
    except Exception as exc:
        print(f"[monitoring] Failed to send failure email: {exc}", file=sys.stderr)


def finish_success(state: RunState) -> None:
    safe_write_sheet_status(state, "SUCCESS", now_taipei())


def finish_failed(state: RunState, exc: BaseException) -> None:
    end_time = now_taipei()
    error_message = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    safe_write_sheet_status(state, "FAILED", end_time, error_message)
    safe_send_failure_email(state, error_message, end_time)
