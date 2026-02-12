from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("settings_app", "0005_filtercriteria_max_date"),
        ("prospects", "0005_prospectdisqualificationnote"),
    ]

    operations = [
        migrations.AddField(
            model_name="prospectdisqualificationnote",
            name="rule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="disqualification_notes",
                to="settings_app.filtercriteria",
            ),
        ),
    ]
