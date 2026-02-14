from django.db import connection

tables = [
    ('prospects_prospectrulenote', 'prospect_id'),
    ('prospects_prospectnote', 'prospect_id'),
    ('prospects_prospectactionlog', 'prospect_id'),
    ('prospects_prospectemail', 'prospect_id'),
    ('cases_case', 'prospect_id'),
]

with connection.cursor() as cur:
    for table, col in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} NOT IN (SELECT id FROM prospects_prospect)")
        cnt = cur.fetchone()[0]
        if cnt:
            print(f"Found {cnt} orphaned rows in {table}; deleting...")
            cur.execute(f"DELETE FROM {table} WHERE {col} NOT IN (SELECT id FROM prospects_prospect)")
            print(f"Deleted {cnt} rows from {table}")
        else:
            print(f"No orphaned rows in {table}")

# handle orphaned Case rows (remove child rows first to satisfy FK constraints)
with connection.cursor() as cur:
    cur.execute("SELECT id FROM cases_case WHERE prospect_id NOT IN (SELECT id FROM prospects_prospect)")
    orphan_cases = [row[0] for row in cur.fetchall()]
    if orphan_cases:
        print(f"Orphaned cases found: {len(orphan_cases)} — cleaning child rows then deleting cases")
        for cid in orphan_cases:
            cur.execute("DELETE FROM cases_casenote WHERE case_id = %s" % cid)
            cur.execute("DELETE FROM cases_casefollowup WHERE case_id = %s" % cid)
            cur.execute("DELETE FROM cases_caseactionlog WHERE case_id = %s" % cid)
            cur.execute("DELETE FROM cases_case WHERE id = %s" % cid)
        print('Orphaned cases removed')
    else:
        print('No orphaned cases')

print('Done')