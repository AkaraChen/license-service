from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("licenses", "0003_identity_and_session_security")]

    operations = [
        migrations.AddConstraint(
            model_name="device",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "bound")),
                fields=("entitlement", "device_fingerprint"),
                name="device_bound_fingerprint_unique",
            ),
        )
    ]
