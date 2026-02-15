import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("settings_app", "0005_filtercriteria_max_date"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SSRevenueSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tier_percent", models.PositiveSmallIntegerField(choices=[(10, "10%"), (13, "13%"), (15, "15%"), (18, "18%"), (25, "25%"), (30, "30%")], default=15)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_ss_revenue_settings", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "SS Revenue Setting",
                "verbose_name_plural": "SS Revenue Settings",
            },
        ),
    ]
