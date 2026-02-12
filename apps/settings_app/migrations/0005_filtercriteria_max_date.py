from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("settings_app", "0004_alter_filtercriteria_options_filtercriteria_counties_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="filtercriteria",
            name="max_date",
            field=models.DateField(
                blank=True,
                help_text="Maximum auction date allowed",
                null=True,
            ),
        ),
    ]
