import datetime
import uuid
from pathlib import Path
from time import timezone

from django.db import models
from django.contrib.auth.models import User
from django.db.models import ManyToManyField, SET_NULL, OneToOneField, FileField

from django.db.models.signals import post_delete
from django.dispatch import receiver

# Create your models here.
ROLE_CHOICES = (
    ("owner", "Owner"),
    ("admin", "Admin"),
    ("moderator", "Moderator"),
    ('user', 'User'),
    ('system', 'System'),
)

OAUTH_PROVIDERS = (
    ("discord", "Discord"),
    ("telegram", "Telegram"),
    ("builtin", "ÆTHER profile")
)

FILE_TYPES = (
    ("image", "Image"),
    ("document", "Document"),
    ("application_info", "Application Info"),
    ("release", "Release file"),
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


def upload_to(instance, filename):
    ext = Path(filename).suffix
    return f"{uuid.uuid4()}{ext}"



class NoteTag(models.Model):
    name = models.CharField(max_length=255)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name
        }


class Note(models.Model):
    name = models.CharField(max_length=255)
    content = models.TextField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    tags = models.ManyToManyField(to=NoteTag)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    def to_dict(self, truncate = False):
        return {
            "id": self.id,
            "name": self.name,
            "content": self.content[:600] if truncate else self.content,
            "owner": self.owner.username,
            "tags": [i.to_dict() for i in self.tags.all()],
            "created_at": self.created_at.isoformat(),
            "edited_at": self.edited_at.isoformat()
        }


class Bookmark(models.Model):
    name = models.CharField(max_length=255)
    url = models.URLField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    folder = models.ForeignKey("BookmarkFolder", on_delete=models.SET_NULL, null=True, blank=True, default=None)
    page_title = models.CharField(max_length=512, blank=True, null=True, default=None)
    cover_image_url = models.URLField(blank=True, null=True, default=None)

    def __str__(self):
        return self.name


class BookmarkFolder(models.Model):
    name = models.CharField(max_length=255)
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
    thumbnail = OneToOneField(to=Sticker, related_name="thumbnail_for_pack", on_delete=models.SET_NULL, null=True,
                              blank=True, default=None)

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
    if instance.stickers:
        instance.stickers.all().delete()


class Ban(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reason = models.TextField(max_length=255)
    expires_at = models.DateTimeField(null=True, blank=True)
    can_be_lifted = models.BooleanField(default=False)
    lifted = models.BooleanField(default=False)
    lifted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="lifted_by")
    banned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="banned_by")
    ip = models.CharField(max_length=255, blank=True, null=True, default=None)


class OAUTHCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=255)
    challenge = models.CharField(max_length=255)
    expires_at = models.DateTimeField()


class UserData(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=255, blank=True, null=True)
    role = models.CharField(max_length=255, choices=ROLE_CHOICES, default="user")
    unsuccessful_attempts = models.IntegerField(default=0)
    is_locked = models.BooleanField(default=False)
    pfp_link = models.CharField(max_length=255, default="", null=True, blank=True)
    favourite_stickers = ManyToManyField(to=Sticker, blank=True)
    sticker_packs = ManyToManyField(to=StickerPack, blank=True)
    oauth_id = models.CharField(max_length=255, blank=True, null=True)
    oauth_provider = models.CharField(max_length=255, choices=OAUTH_PROVIDERS, default="builtin")
    login_failed_ips = models.JSONField(default=dict)
    used_storage = models.BigIntegerField(default=0)

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


class S3File(models.Model):
    file = FileField(upload_to=upload_to)
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    folder = models.ForeignKey("S3Folder", on_delete=models.SET_NULL, null=True, blank=True, default=None)
    size = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    captured_at = models.DateTimeField(null=True, blank=True, default=None)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "folder", "name"], name="unique_file_name_per_folder")
        ]

    def __str__(self):
        return self.name

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "folder_id": self.folder_id,
            "size": self.size,
            "created_at": self.created_at.isoformat(),
            "captured_at": self.captured_at.isoformat() if self.captured_at is not None else None,
        }


class S3Folder(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, default=None, related_name="children")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "parent", "name"], name="unique_folder_name_per_parent")
        ]

    def __str__(self):
        return self.name

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "created_at": self.created_at.isoformat(),
        }


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
    release_file = models.ForeignKey(File, on_delete=models.SET_NULL, default=None, null=True, blank=True)

    def __str__(self):
        return f"{self.version}"
