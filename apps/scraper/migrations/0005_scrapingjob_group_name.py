from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scraper", "0004_county_scrape_url_add_url_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="scrapingjob",
            name="group_name",
            field=models.CharField(
                max_length=255,
                blank=True,
                default="",
                help_text="Optional label used to group related jobs",
            ),
        ),
    ]
