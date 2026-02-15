from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prospects", "0011_prospect_ack_url_prospect_tdm_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="prospect",
            name="qualification_date",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

