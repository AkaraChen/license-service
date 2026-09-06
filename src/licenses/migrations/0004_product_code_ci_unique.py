"""Enforce case-insensitive uniqueness for Product.code."""

from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower


def refuse_case_variant_duplicates(apps, schema_editor):
    Product = apps.get_model("licenses", "Product")
    alias = schema_editor.connection.alias
    duplicates = (
        Product.objects.using(alias)
        .annotate(canonical=Lower("code"))
        .values("canonical")
        .annotate(total=Count("pk"))
        .filter(total__gt=1)
    )
    if duplicates.exists():
        raise RuntimeError(
            "Resolve case-insensitive duplicate product codes before applying this migration; products are not merged automatically."
        )


class Migration(migrations.Migration):
    dependencies = [("licenses", "0003_identity_and_session_security")]

    operations = [
        migrations.RunPython(refuse_case_variant_duplicates, migrations.RunPython.noop),
        migrations.AlterField(model_name="product", name="code", field=models.CharField(max_length=64)),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.UniqueConstraint(Lower("code"), name="product_code_ci_unique"),
        ),
    ]
