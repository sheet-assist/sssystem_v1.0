from django.db import migrations, models


# def remove_foreign_key_orphans(apps, schema_editor):
#     """
#     Remove any rows currently violating SQLite foreign keys so schema edits can run.
#     """
#     connection = schema_editor.connection
#     quote_name = connection.ops.quote_name

#     with connection.cursor() as cursor:
#         while True:
#             cursor.execute("PRAGMA foreign_key_check")
#             violations = cursor.fetchall()
#             if not violations:
#                 break

#             # PRAGMA result: (table, rowid, parent_table, fk_index)
#             for table_name, row_id, _parent, _fk_index in violations:
#                 cursor.execute(
#                     f"DELETE FROM {quote_name(table_name)} WHERE rowid = %s",
#                     [row_id],
#                 )


class Migration(migrations.Migration):

    dependencies = [
        ("prospects", "0007_rename_rule_note_and_add_decision"),
    ]

    operations = [
        # migrations.RunPython(remove_foreign_key_orphans, migrations.RunPython.noop),
        migrations.AddField(
            model_name="prospect",
            name="parcel_url",
            field=models.URLField(blank=True, default=""),
        ),
    ]
