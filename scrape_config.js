/*
  Use JSON syntax (double-quoted keys/strings) inside this object.
  The backfill command reads this file and parses the object below.
*/
module.exports = {
  "state": "FL",
  "doc_type": "TD",
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "counties": ["Miami-Dade"],
  "chunk_days": 1,
  "group_name": "td_backfill_feb_2026_miami_dade",
  "output_file": "output.md",
  "skip_completed": true,
  "retry_failed": true,
  "dry_run": false
};
