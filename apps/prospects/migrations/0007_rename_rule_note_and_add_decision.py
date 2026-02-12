from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prospects", "0006_prospectdisqualificationnote_rule"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="ProspectDisqualificationNote",
            new_name="ProspectRuleNote",
        ),
        migrations.AlterField(
            model_name="prospectrulenote",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="created_rule_notes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="prospectrulenote",
            name="prospect",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="rule_notes",
                to="prospects.prospect",
            ),
        ),
        migrations.AlterField(
            model_name="prospectrulenote",
            name="rule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="rule_notes",
                to="settings_app.filtercriteria",
            ),
        ),
        migrations.AddField(
            model_name="prospectrulenote",
            name="decision",
            field=models.CharField(
                choices=[("qualified", "Qualified"), ("disqualified", "Disqualified")],
                default="disqualified",
                max_length=32,
            ),
        ),
    ]
