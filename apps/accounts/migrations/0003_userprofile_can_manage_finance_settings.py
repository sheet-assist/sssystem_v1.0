from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_alter_userprofile_options_alter_userprofile_phone"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="can_manage_finance_settings",
            field=models.BooleanField(default=False),
        ),
    ]
