from django.contrib.auth.models import User
from django.core.management import call_command

from api.models import UserData, S3File


def run_startup_tasks():
    call_command('makemigrations')
    call_command('migrate')

    if not User.objects.filter(username='system').exists():
        system_user = User.objects.create_user('system', '', '')
        system_user.save()
        system_user.refresh_from_db()
        UserData.objects.create(
            user=system_user,
            role='system',
            is_locked=True,
            display_name='System',
        )

    print("Calculating used storage... ", end="")
    for i in S3File.objects.filter(size=0):
        i.size = i.file.size
        i.save()
    print("Done")
