"""Enforce identity uniqueness and retire sessions minted before the fixes."""

from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Lower


def harden(apps, schema_editor):
    User = apps.get_model("auth", "User")
    alias = schema_editor.connection.alias
    duplicates = (
        User.objects.using(alias)
        .annotate(canonical=Lower("username"))
        .values("canonical")
        .annotate(total=Count("pk"))
        .filter(total__gt=1)
    )
    if duplicates.exists():
        raise RuntimeError(
            "Resolve case-insensitive duplicate usernames before applying this migration; accounts are not merged automatically."
        )
    table = schema_editor.quote_name(User._meta.db_table)
    schema_editor.execute(
        f'CREATE UNIQUE INDEX "auth_user_username_ci_unique" ON {table} (LOWER("username"))'
    )
    # Includes legacy plaintext-delivery sessions and sessions created by the
    # inactive-user login bug. All users must authenticate again after upgrade.
    apps.get_model("sessions", "Session").objects.using(alias).all().delete()


def reverse(apps, schema_editor):
    schema_editor.execute('DROP INDEX "auth_user_username_ci_unique"')


class Migration(migrations.Migration):
    dependencies = [
        ("licenses", "0002_device_name_constraint"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("sessions", "0001_initial"),
    ]
    operations = [migrations.RunPython(harden, reverse)]
