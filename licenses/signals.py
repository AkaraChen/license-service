"""Invalidate account sessions on either side of an activation change."""

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver


@receiver(pre_save, sender=User)
def track_active_change(sender, instance, **kwargs):
    previous = sender.objects.filter(pk=instance.pk).values_list("is_active", flat=True).first()
    instance._active_changed = previous is not None and previous != instance.is_active


@receiver(post_save, sender=User)
def invalidate_sessions(sender, instance, **kwargs):
    if getattr(instance, "_active_changed", False):
        for session in Session.objects.iterator():
            if session.get_decoded().get("_auth_user_id") == str(instance.pk):
                session.delete()
