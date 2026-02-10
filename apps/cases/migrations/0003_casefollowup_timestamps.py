import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0002_alter_case_options_alter_caseactionlog_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="casefollowup",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="casefollowup",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="casenote",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
