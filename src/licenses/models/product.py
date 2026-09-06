from django.db import models
from django.db.models.functions import Lower


class Product(models.Model):
    code = models.CharField(max_length=64)  # trimmed, unique (compared case-insensitively)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("code"), name="product_code_ci_unique")]

    def __str__(self):
        return self.code
