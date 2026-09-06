from django.db import models


class Product(models.Model):
    code = models.CharField(max_length=64, unique=True)  # trimmed, unique (compared case-insensitively)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code
