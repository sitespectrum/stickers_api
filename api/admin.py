from django.contrib import admin
from . import models

# Register your models here.
admin.site.register(models.UserData)
admin.site.register(models.ConfigObject)
admin.site.register(models.File)
admin.site.register(models.Announcement)
admin.site.register(models.ErrorLog)
admin.site.register(models.Release)
admin.site.register(models.StickerPack)
admin.site.register(models.Sticker)
admin.site.register(models.Ban)
admin.site.register(models.Note)
admin.site.register(models.Bookmark)
admin.site.register(models.S3File)
