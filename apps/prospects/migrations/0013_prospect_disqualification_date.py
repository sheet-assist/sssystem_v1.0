from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prospects", "0012_prospect_qualification_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="prospect",
            name="disqualification_date",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

