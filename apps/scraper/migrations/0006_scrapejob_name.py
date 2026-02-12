from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scraper", "0005_scrapingjob_group_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="scrapejob",
            name="name",
            field=models.CharField(
                max_length=255,
                blank=True,
                default="",
                help_text="Human-friendly identifier used to group related jobs",
            ),
        ),
    ]
