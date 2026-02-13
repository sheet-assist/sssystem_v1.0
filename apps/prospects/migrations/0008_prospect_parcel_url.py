from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prospects", "0007_rename_rule_note_and_add_decision"),
    ]

    operations = [
        migrations.AddField(
            model_name="prospect",
            name="parcel_url",
            field=models.URLField(blank=True, default=""),
        ),
    ]
