import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

BASE_DIR = Path(settings.BASE_DIR)
DEFAULT_CONFIG_PATH = BASE_DIR / "apps" / "scraper" / "config" / "scrape_config.json"
DEFAULT_OUTPUT_PATH = BASE_DIR / "apps" / "scraper" / "config" / "output.md"

from apps.locations.models import County, State
from apps.scraper.engine import run_scrape_job
from apps.scraper.models import ScrapeJob


VALID_JOB_TYPES = {"TD", "TL", "SS", "MF"}


@dataclass
class BackfillTarget:
    county: County
    start_date: date
    end_date: date


class Command(BaseCommand):
    help = (
        "Run county/date backfill scraping from a scrape_config.json file and "
        "continuously update a markdown progress report."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--config",
            default=str(DEFAULT_CONFIG_PATH),
            help="Path to scrape config JSON file (default: apps/scraper/config/scrape_config.json).",
        )
        parser.add_argument(
            "--output",
            default=None,
            help="Optional output markdown path. Overrides config output_file.",
        )

    def handle(self, *args, **options):
        config_path = Path(options["config"]).resolve()
        config = self._load_config(config_path)
        output_file_cfg = (config.get("output_file") or "").strip()
        output_path = self._resolve_output_path(
            options.get("output"), output_file_cfg, config_path
        )

        state = self._resolve_state(config)
        job_type = self._resolve_job_type(config)
        start_date, end_date = self._resolve_dates(config)
        chunk_days = self._resolve_chunk_days(config)

        selected_counties, missing_counties = self._resolve_target_counties(
            state=state,
            job_type=job_type,
            counties_from_config=config.get("counties"),
        )

        targets = self._build_targets(selected_counties, start_date, end_date, chunk_days)
        run_started = timezone.now()
        group_name = config.get("group_name", f"backfill_{job_type}_{run_started:%Y%m%d_%H%M%S}")
        dry_run = bool(config.get("dry_run", False))
        retry_failed = bool(config.get("retry_failed", True))
        skip_completed = bool(config.get("skip_completed", True))

        progress = {
            "run_started": run_started,
            "run_finished": None,
            "config_path": str(config_path),
            "output_path": str(output_path),
            "state": state.abbreviation,
            "job_type": job_type,
            "range_start": start_date,
            "range_end": end_date,
            "chunk_days": chunk_days,
            "group_name": group_name,
            "dry_run": dry_run,
            "retry_failed": retry_failed,
            "skip_completed": skip_completed,
            "missing_counties": missing_counties,
            "total_targets": len(targets),
            "stats": {
                "started": 0,
                "completed": 0,
                "failed": 0,
                "skipped": 0,
                "created": 0,
                "updated": 0,
                "qualified": 0,
                "disqualified": 0,
            },
            "current": "",
            "rows": [],
            "events": [],
        }
        self._write_progress(output_path, progress)

        if not targets:
            self._append_event(progress, "No matching county/date targets found.")
            progress["run_finished"] = timezone.now()
            self._write_progress(output_path, progress)
            self.stdout.write(self.style.WARNING("No targets to process."))
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Starting backfill: {len(targets)} target(s), "
                f"{state.abbreviation}, {job_type}, {start_date}..{end_date}, chunk={chunk_days}"
            )
        )

        for index, target in enumerate(targets, start=1):
            county = target.county
            label = f"{county.name} ({county.state.abbreviation}) {target.start_date}..{target.end_date}"
            progress["current"] = f"[{index}/{len(targets)}] {label}"
            self._append_event(progress, f"Processing {label}")
            self._write_progress(output_path, progress)

            existing = self._find_existing_job(county, job_type, target.start_date, target.end_date)
            job, action, reason = self._prepare_job(
                existing=existing,
                county=county,
                job_type=job_type,
                target_start=target.start_date,
                target_end=target.end_date,
                group_name=group_name,
                skip_completed=skip_completed,
                retry_failed=retry_failed,
                dry_run=dry_run,
            )

            row = {
                "county": county.name,
                "state": county.state.abbreviation,
                "date_start": str(target.start_date),
                "date_end": str(target.end_date),
                "job_id": str(job.pk) if job else "-",
                "job_action": action,
                "status": "pending",
                "started_at": "",
                "ended_at": "",
                "created": 0,
                "updated": 0,
                "qualified": 0,
                "disqualified": 0,
                "error": "",
            }

            if reason:
                row["status"] = "skipped"
                row["error"] = reason
                progress["stats"]["skipped"] += 1
                progress["rows"].append(row)
                self._append_event(progress, f"Skipped {label}: {reason}")
                self._write_progress(output_path, progress)
                continue

            if dry_run:
                row["status"] = "dry-run"
                progress["rows"].append(row)
                self._append_event(progress, f"Dry run only: {label}")
                self._write_progress(output_path, progress)
                continue

            progress["stats"]["started"] += 1
            row["status"] = "running"
            row["started_at"] = self._fmt_dt(timezone.now())
            progress["rows"].append(row)
            self._write_progress(output_path, progress)

            try:
                run_scrape_job(job)
                job.refresh_from_db()
                row["status"] = job.status
                row["ended_at"] = self._fmt_dt(job.completed_at or timezone.now())
                row["created"] = int(job.prospects_created or 0)
                row["updated"] = int(job.prospects_updated or 0)
                row["qualified"] = int(job.prospects_qualified or 0)
                row["disqualified"] = int(job.prospects_disqualified or 0)

                if job.status == "completed":
                    progress["stats"]["completed"] += 1
                else:
                    progress["stats"]["failed"] += 1
                    row["error"] = (job.error_message or "").strip()

                progress["stats"]["created"] += row["created"]
                progress["stats"]["updated"] += row["updated"]
                progress["stats"]["qualified"] += row["qualified"]
                progress["stats"]["disqualified"] += row["disqualified"]
                self._append_event(progress, f"Finished {label}: status={job.status}")
            except Exception as exc:
                row["status"] = "failed"
                row["ended_at"] = self._fmt_dt(timezone.now())
                row["error"] = str(exc)
                progress["stats"]["failed"] += 1
                self._append_event(progress, f"Failed {label}: {exc}")

            self._write_progress(output_path, progress)

        progress["current"] = ""
        progress["run_finished"] = timezone.now()
        self._append_event(progress, "Backfill run completed.")
        self._write_progress(output_path, progress)

        self.stdout.write(
            self.style.SUCCESS(
                "Done. "
                f"started={progress['stats']['started']} "
                f"completed={progress['stats']['completed']} "
                f"failed={progress['stats']['failed']} "
                f"skipped={progress['stats']['skipped']} "
                f"created={progress['stats']['created']} "
                f"updated={progress['stats']['updated']}"
            )
        )

    def _load_config(self, config_path: Path) -> Dict:
        if not config_path.exists():
            raise CommandError(f"Config file not found: {config_path}")

        raw = config_path.read_text(encoding="utf-8")

        if config_path.suffix.lower() == ".json":
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise CommandError(f"Invalid JSON in {config_path}: {exc}.")
        else:
            # Legacy .js support: strip comments and extract the object literal
            cleaned = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
            cleaned = re.sub(r"^\s*//.*$", "", cleaned, flags=re.M)
            match = re.search(r"\{.*\}", cleaned, flags=re.S)
            if not match:
                raise CommandError(
                    f"Could not find a JSON object in {config_path.name}. "
                    "Use a JSON object (quoted keys/strings) in the file."
                )
            candidate = re.sub(r",(\s*[}\]])", r"\1", match.group(0).strip())
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError as exc:
                raise CommandError(
                    f"Invalid config JSON in {config_path}: {exc}. "
                    "Ensure the file uses JSON syntax (double-quoted keys/strings)."
                )

        if not isinstance(parsed, dict):
            raise CommandError(f"Config root must be an object: {config_path}")
        return parsed

    def _resolve_output_path(self, output_arg: Optional[str], output_cfg: str, config_path: Path) -> Path:
        raw_path = output_arg or output_cfg or str(DEFAULT_OUTPUT_PATH)
        path = Path(raw_path)
        if not path.is_absolute():
            path = (config_path.parent / path).resolve()
        return path

    def _resolve_state(self, config: Dict) -> State:
        state_code = (config.get("state") or "").strip().upper()
        if not state_code:
            raise CommandError("Config requires 'state' (example: \"FL\").")
        try:
            return State.objects.get(abbreviation=state_code, is_active=True)
        except State.DoesNotExist:
            raise CommandError(f"Active state '{state_code}' not found.")

    def _resolve_job_type(self, config: Dict) -> str:
        raw = (config.get("doc_type") or config.get("job_type") or "").strip().upper()
        if raw not in VALID_JOB_TYPES:
            raise CommandError("Config requires doc_type/job_type with one of: TD, TL, SS, MF.")
        return raw

    def _resolve_dates(self, config: Dict) -> Tuple[date, date]:
        start = self._parse_date(config.get("start_date"), "start_date")
        end_raw = config.get("end_date")
        end = self._parse_date(end_raw, "end_date") if end_raw else timezone.localdate()
        if end < start:
            raise CommandError("end_date must be on or after start_date.")
        return start, end

    def _resolve_chunk_days(self, config: Dict) -> int:
        raw = config.get("chunk_days", 1)
        try:
            chunk_days = int(raw)
        except (TypeError, ValueError):
            raise CommandError("chunk_days must be an integer >= 1.")
        if chunk_days < 1:
            raise CommandError("chunk_days must be >= 1.")
        return chunk_days

    def _resolve_target_counties(
        self, state: State, job_type: str, counties_from_config: Optional[List[str]]
    ) -> Tuple[List[County], List[str]]:
        active_url_counties = County.objects.filter(
            state=state,
            is_active=True,
            scrape_urls__url_type=job_type,
            scrape_urls__is_active=True,
        ).distinct().order_by("name")

        if not counties_from_config:
            return list(active_url_counties), []

        requested = [(name or "").strip() for name in counties_from_config if (name or "").strip()]
        if not requested:
            return list(active_url_counties), []

        requested_lower = {name.lower() for name in requested}
        filtered = []
        matched_keys = set()

        for county in active_url_counties:
            candidates = {county.name.lower(), county.slug.lower()}
            if candidates & requested_lower:
                filtered.append(county)
                matched_keys.update(candidates & requested_lower)

        missing = sorted(name for name in requested if name.lower() not in matched_keys)
        return filtered, missing

    def _build_targets(
        self, counties: List[County], start_date: date, end_date: date, chunk_days: int
    ) -> List[BackfillTarget]:
        targets: List[BackfillTarget] = []
        for county in counties:
            current = start_date
            while current <= end_date:
                chunk_end = min(current + timedelta(days=chunk_days - 1), end_date)
                targets.append(
                    BackfillTarget(
                        county=county,
                        start_date=current,
                        end_date=chunk_end,
                    )
                )
                current = chunk_end + timedelta(days=1)
        return targets

    def _find_existing_job(self, county: County, job_type: str, start: date, end: date) -> Optional[ScrapeJob]:
        return (
            ScrapeJob.objects.filter(
                county=county,
                job_type=job_type,
                target_date=start,
                end_date=end,
            )
            .order_by("-created_at")
            .first()
        )

    def _prepare_job(
        self,
        *,
        existing: Optional[ScrapeJob],
        county: County,
        job_type: str,
        target_start: date,
        target_end: date,
        group_name: str,
        skip_completed: bool,
        retry_failed: bool,
        dry_run: bool,
    ) -> Tuple[Optional[ScrapeJob], str, str]:
        if existing:
            if existing.status == "running":
                return existing, "existing-running", "existing job is running"

            if existing.status == "completed" and skip_completed:
                return existing, "existing-completed", "existing job already completed"

            if existing.status == "failed":
                if not retry_failed:
                    return existing, "existing-failed", "existing failed job and retry_failed=false"
                if not dry_run:
                    self._reset_job(existing)
                return existing, "retry-failed", ""

            if existing.status == "pending":
                return existing, "reuse-pending", ""

        if dry_run:
            return None, "create", ""

        job_name = f"{group_name} | {county.name} | {target_start}..{target_end}"
        job = ScrapeJob.objects.create(
            name=job_name,
            county=county,
            job_type=job_type,
            target_date=target_start,
            end_date=target_end,
            status="pending",
        )
        return job, "created", ""

    def _reset_job(self, job: ScrapeJob):
        job.status = "pending"
        job.error_message = ""
        job.prospects_created = 0
        job.prospects_updated = 0
        job.prospects_qualified = 0
        job.prospects_disqualified = 0
        job.started_at = None
        job.completed_at = None
        job.save(
            update_fields=[
                "status",
                "error_message",
                "prospects_created",
                "prospects_updated",
                "prospects_qualified",
                "prospects_disqualified",
                "started_at",
                "completed_at",
            ]
        )

    def _append_event(self, progress: Dict, message: str):
        now_text = self._fmt_dt(timezone.now())
        progress["events"].append(f"{now_text} - {message}")
        if len(progress["events"]) > 200:
            progress["events"] = progress["events"][-200:]

    def _write_progress(self, output_path: Path, progress: Dict):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        lines.append("# Scrape Backfill Progress")
        lines.append("")
        lines.append("## Run")
        lines.append(f"- Started: {self._fmt_dt(progress['run_started'])}")
        lines.append(f"- Finished: {self._fmt_dt(progress['run_finished']) if progress['run_finished'] else '-'}")
        lines.append(f"- Config: `{progress['config_path']}`")
        lines.append(f"- Output: `{progress['output_path']}`")
        lines.append(f"- State: `{progress['state']}`")
        lines.append(f"- Doc Type: `{progress['job_type']}`")
        lines.append(f"- Date Range: `{progress['range_start']}` to `{progress['range_end']}`")
        lines.append(f"- Chunk Days: `{progress['chunk_days']}`")
        lines.append(f"- Group Name: `{progress['group_name']}`")
        lines.append(f"- Dry Run: `{progress['dry_run']}`")
        lines.append("")
        lines.append("## Current")
        lines.append(f"- Processing: {progress['current'] or '-'}")
        lines.append("")
        lines.append("## Stats")
        lines.append(f"- Targets: `{progress['total_targets']}`")
        lines.append(f"- Started Jobs: `{progress['stats']['started']}`")
        lines.append(f"- Completed Jobs: `{progress['stats']['completed']}`")
        lines.append(f"- Failed Jobs: `{progress['stats']['failed']}`")
        lines.append(f"- Skipped Jobs: `{progress['stats']['skipped']}`")
        lines.append(f"- Prospects Created: `{progress['stats']['created']}`")
        lines.append(f"- Prospects Updated: `{progress['stats']['updated']}`")
        lines.append(f"- Prospects Qualified: `{progress['stats']['qualified']}`")
        lines.append(f"- Prospects Disqualified: `{progress['stats']['disqualified']}`")
        if progress["missing_counties"]:
            lines.append(f"- Missing Counties From Config: `{', '.join(progress['missing_counties'])}`")
        lines.append("")
        lines.append("## Job Rows")
        lines.append(
            "| County | State | Start | End | Job ID | Action | Status | Start Time | End Time | Created | Updated | Qualified | Disqualified | Error |"
        )
        lines.append(
            "|---|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---|"
        )
        for row in progress["rows"]:
            lines.append(
                f"| {row['county']} | {row['state']} | {row['date_start']} | {row['date_end']} | "
                f"{row['job_id']} | {row['job_action']} | {row['status']} | {row['started_at'] or '-'} | "
                f"{row['ended_at'] or '-'} | {row['created']} | {row['updated']} | "
                f"{row['qualified']} | {row['disqualified']} | {self._escape_pipe(row['error']) or '-'} |"
            )
        lines.append("")
        lines.append("## Event Log")
        for event in progress["events"][-100:]:
            lines.append(f"- {event}")
        lines.append("")
        output_path.write_text("\n".join(lines), encoding="utf-8")

    def _fmt_dt(self, value) -> str:
        if not value:
            return ""
        if isinstance(value, datetime):
            return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    def _escape_pipe(self, text: str) -> str:
        return (text or "").replace("|", "\\|").replace("\n", " ").strip()

    def _parse_date(self, raw_value, key_name: str) -> date:
        if not raw_value:
            raise CommandError(f"Config requires '{key_name}' in YYYY-MM-DD format.")
        try:
            return datetime.strptime(str(raw_value), "%Y-%m-%d").date()
        except ValueError:
            raise CommandError(f"Invalid {key_name} '{raw_value}'. Expected YYYY-MM-DD.")
