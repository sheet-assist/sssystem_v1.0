from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("settings_app", "0006_ssrevenuesetting"),
    ]

    operations = [
        migrations.AddField(
            model_name="ssrevenuesetting",
            name="ars_tier_percent",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (1, "1%"),
                    (3, "3%"),
                    (5, "5%"),
                    (7, "7%"),
                    (8, "8%"),
                    (9, "9%"),
                    (10, "10%"),
                ],
                default=5,
            ),
        ),
    ]
