import datetime

from django.db import models
from django.contrib.auth.models import User
from django.db.models import ManyToManyField, SET_NULL

# Create your models here.
ROLE_CHOICES = (
    ("owner", "Owner"),
    ('admin', 'Admin'),
    ('user', 'User'),
)

FILE_TYPES = (
    ("image", "Image"),
    ("document", "Document"),
    ("application_info", "Application Info"),
    ("release", "Release notes"),
)

ANNOUNCEMENT_TYPES = (
    ('public', 'Public'),
    ('service', 'Service'),
    ('staff', 'Staff (Only visible on the dashboard)'),
)

ERROR_SEVERITIES = (
    ('critical', 'Critical'),
    ('database', 'Database Error'),
    ('high', 'High'),
    ('medium', 'Medium'),
    ('low', 'Low'),
    ('info', 'Information'),
    ('unknown', 'Unknown')
)


class UserData(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=255, choices=ROLE_CHOICES)
    unsuccessful_attempts = models.IntegerField(default=0)
    is_disabled = models.BooleanField(default=False)

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


class Stickerpack(models.Model):
    name = models.CharField(max_length=255)
    url = models.URLField(unique=True)
    stickers = models.JSONField()

    def __str__(self):
        return f"{self.name} ({self.url})"
