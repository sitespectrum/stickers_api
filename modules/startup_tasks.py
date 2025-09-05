from django.core.management import call_command


def run_startup_tasks():
    call_command('makemigrations')
    call_command('migrate')
