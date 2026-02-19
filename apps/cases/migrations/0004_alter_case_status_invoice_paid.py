from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0003_casefollowup_timestamps"),
    ]

    operations = [
        migrations.AlterField(
            model_name="case",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("monitoring", "Monitoring"),
                    ("follow_up", "Follow Up"),
                    ("invoice_paid", "Invoice Paid"),
                    ("closed_won", "Closed Won"),
                    ("closed_lost", "Closed Lost"),
                ],
                default="active",
                max_length=32,
            ),
        ),
    ]
