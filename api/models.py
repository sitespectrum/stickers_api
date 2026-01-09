import datetime

from django.db import models
from django.contrib.auth.models import User
from django.db.models import ManyToManyField, SET_NULL, OneToOneField

from django.db.models.signals import post_delete
from django.dispatch import receiver


# Create your models here.
ROLE_CHOICES = (
    ("owner", "Owner"),
    ("admin", "Admin"),
    ("moderator", "Moderator"),
    ('user', 'User'),
)

OAUTH_PROVIDERS = (
    ("discord", "Discord"),
    ("telegram", "Telegram"),
    ("builtin", "Stickerß profile")
)

FILE_TYPES = (
    ("image", "Image"),
    ("document", "Document"),
    ("application_info", "Application Info"),
    ("release", "Release notes"),
)

ANNOUNCEMENT_TYPES = (
    ("public", "Public"),
    ("service", "Service"),
    ("staff", "Staff (Only visible on the dashboard)"),
)

ERROR_SEVERITIES = (
    ("critical", "Critical"),
    ("database", "Database Error"),
    ("high", "High"),
    ("medium", "Medium"),
    ("low", "Low"),
    ("info", "Information"),
    ("unknown", "Unknown")
)


class Note(models.Model):
    name = models.CharField(max_length=255)
    content = models.TextField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class Sticker(models.Model):
    emoji = models.CharField(max_length=255)
    file_name = models.CharField(max_length=255)
    file_id = models.CharField(max_length=255)
    unique_file_id = models.CharField(max_length=255)
    is_video = models.BooleanField(default=False)
    is_animated = models.BooleanField(default=False)


class StickerPack(models.Model):
    name = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=255)
    stickers = ManyToManyField(to=Sticker, related_name="packs")
    thumbnail = OneToOneField(to=Sticker,related_name="thumbnail_for_pack", on_delete=models.SET_NULL, null=True, blank=True, default=None)

    def __str__(self):
        return f"{self.title} ({self.name})"


# Ensure correct cleanup of related objects (stickers and thumbnail) when StickerPack is deleted
@receiver(post_delete, sender=StickerPack)
def delete_stickers_on_pack_delete(sender, instance, **kwargs):
    """
    Deletes stickers associated with a StickerPack when the StickerPack is deleted.
    This includes stickers in the `stickers` field and the `thumbnail`.
    """
    # Delete the thumbnail if it exists
    if instance.thumbnail:
        instance.thumbnail.delete()


class Ban(models.Model):
    reason = models.TextField(max_length=255)
    expires_at = models.DateTimeField(null=True, blank=True)


class UserData(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=255, blank=True, null=True)
    role = models.CharField(max_length=255, choices=ROLE_CHOICES, default="user")
    unsuccessful_attempts = models.IntegerField(default=0)
    is_locked = models.BooleanField(default=False)
    pfp_link = models.CharField(max_length=255, default="/person-fill.svg")
    favourite_stickers = ManyToManyField(to=Sticker, blank=True)
    sticker_packs = ManyToManyField(to=StickerPack, blank=True)
    oauth_id = models.CharField(max_length=255, blank=True, null=True)
    oauth_provider = models.CharField(max_length=255, choices=OAUTH_PROVIDERS, default="builtin")
    bans = ManyToManyField(to=Ban, blank=True)

    def __str__(self):
        return f"{self.user.username}'s user data"


class ConfigObject(models.Model):
    name = models.CharField(max_length=255, unique=True)
    data = models.JSONField()
    last_updated = models.DateField()

    def __str__(self):
        return self.name


class PasswordResetCode(models.Model):
    for_user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_after = models.IntegerField(default=7)

    def __str__(self):
        return self.code


class File(models.Model):
    name = models.CharField(max_length=255, unique=True)
    path = models.CharField(max_length=255, unique=True)
    file_type = models.CharField(choices=FILE_TYPES, max_length=255)

    def __str__(self):
        return self.name


class Announcement(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True, editable=True, default=None)
    announcement_type = models.CharField(choices=ANNOUNCEMENT_TYPES, max_length=255)
    made_by = models.ForeignKey(User, on_delete=SET_NULL, default=None, null=True, blank=True)

    def __str__(self):
        return f"{self.title} ({self.announcement_type})"


class ErrorLog(models.Model):
    error_type = models.CharField(max_length=255)
    error_message = models.TextField()
    error_traceback = models.TextField()
    error_time = models.DateTimeField(auto_now_add=True)
    error_severity = models.CharField(choices=ERROR_SEVERITIES, max_length=255)
    panicked = models.BooleanField(default=False)
    fallback = models.BooleanField(default=False)
    safe = models.BooleanField(default=False)

    def __str__(self):
        return f"({self.id}) [{dict(ERROR_SEVERITIES)[self.error_severity]}] {self.error_type} - {self.error_time.strftime('%Y-%m-%d %H:%M:%S')} UTC {'PANIC' if self.panicked else ''}{'FALLBACK' if self.fallback else ''}{'SAFE' if self.safe else ''} "


class Release(models.Model):
    version = models.CharField(max_length=255)
    release_date = models.DateField(blank=True, null=True, default=None)
    release_note_file = models.ForeignKey(File, on_delete=models.SET_NULL, default=None, null=True, blank=True)

    def __str__(self):
        return f"{self.version}"
