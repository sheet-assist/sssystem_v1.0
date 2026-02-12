from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("prospects", "0004_prospect_auction_type_prospect_sold_to"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProspectDisqualificationNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("note", models.TextField()),
                ("rule_name", models.CharField(blank=True, default="", max_length=255)),
                ("source", models.CharField(choices=[("rule", "Rule"), ("scraper", "Scraper"), ("manual", "Manual")], default="rule", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_disqualification_notes", to=settings.AUTH_USER_MODEL)),
                ("prospect", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="disqualification_notes", to="prospects.prospect")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
