from datetime import datetime
from functools import wraps
import os
import git
from django.db.models import Q

from api.models import ErrorLog, Announcement


from django.http import JsonResponse, HttpResponse

from modules import html_parse

PANIC = False
SAFE = False
FALLBACK = False
MAINTENANCE = False

statuses = {
    "panic": "Panic",
    "safe": "Safe",
    "fallback": "Fallback",
    "maintenance": "Maintenance",
    "normal": "Normal"
}


def get_status():
    if PANIC:
        return "panic"
    elif SAFE:
        return "safe"
    elif FALLBACK:
        return "fallback"
    elif MAINTENANCE:
        return "maintenance"
    else:
        return "normal"


def neutral():
    global PANIC, SAFE, FALLBACK, MAINTENANCE
    PANIC = False
    SAFE = False
    FALLBACK = False
    MAINTENANCE = False


def panic():
    global PANIC, SAFE, FALLBACK, MAINTENANCE
    if SAFE or FALLBACK or MAINTENANCE:
        return
    PANIC = True


def safe():
    global PANIC, SAFE, FALLBACK, MAINTENANCE
    if PANIC or FALLBACK or MAINTENANCE:
        return
    SAFE = True


def fallback():
    global PANIC, SAFE, FALLBACK, MAINTENANCE
    if PANIC or SAFE or MAINTENANCE:
        return
    FALLBACK = True


def maintenance():
    global PANIC, SAFE, FALLBACK, MAINTENANCE
    if PANIC or SAFE or FALLBACK:
        return
    MAINTENANCE = True


def panic_protected():
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if PANIC and "/api" in request.path:
                return JsonResponse({
                    "status": "Error",
                    "error": "Service unavailable.",
                }, status=503)
            if PANIC:
                page_contents = """
                <div class='center-container'>
                    <h1>503 - Service unavailable</h1>
                </div>"""
                with open("frontend/error.html") as f:
                    return HttpResponse(
                        f.read().replace("%error%", page_contents)
                    )

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def safe_protected():
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if SAFE and "/api" in request.path:
                return JsonResponse({
                    "status": "Error",
                    "error": "Service unavailable.",
                }, status=503)
            if SAFE:
                page_contents = """
                <div class='center-container'>
                    <h1>503 - Service unavailable</h1>
                </div>"""
                with open("frontend/error.html") as f:
                    return HttpResponse(
                        f.read().replace("%error%", page_contents)
                    )

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def maintenance_protected():
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if MAINTENANCE and "/api" in request.path:
                return JsonResponse({
                    "status": "Error",
                    "error": "Service under maintenance.",
                }, status=503)
            if MAINTENANCE:
                page_contents = "<h1>Our website is currently under maintenance</h1>"
                with open("frontend/error.html") as f:
                    return HttpResponse(
                        f.read().replace("%error%", page_contents)
                    )

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def fallback_protected():
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if FALLBACK and "/api" in request.path:
                return JsonResponse({
                    "status": "Error",
                    "error": "Service unavailable.",
                }, status=503)
            if FALLBACK:
                page_contents = """
                <div class='center-container'>
                    <h1>503 - Service unavailable</h1>
                </div>"""
                with open("frontend/error.html") as f:
                    return HttpResponse(
                        f.read().replace("%error%", page_contents)
                    )

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def get_size(start_path='.'):
    if not os.path.exists(start_path):
        return 0
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size / 1024 / 1024  # Returns MiB


def self_update(repo_path='', username=None, password=None):
    repo = git.Repo(repo_path)
    remote_url = repo.remotes.origin.url

    if username and password:
        if remote_url.startswith("https://"):
            remote_url = remote_url.replace("https://", f"https://{username}:{password}@")
        elif remote_url.startswith("git@"):
            raise ValueError("Cannot authenticate SSH URLs with username/password. Use HTTPS instead.")

    try:
        resp = repo.git.pull(remote_url).splitlines()
        ErrorLog.objects.create(
            error_type="Git Pull",
            error_message="Admin issued server update succeeded",
            error_traceback="\n".join(resp) + "\n\nExecuted by the internal function",
            error_time=datetime.now(),
            error_severity="info",
            panicked=False,
            safe=False,
            fallback=False,
        )
        return resp
    except git.exc.GitCommandError as err:
        err_list = str(err).splitlines()
        if "Your local changes to the following files would be overwritten" in err_list:
            ErrorLog.objects.create(
                error_type="Git Pull",
                error_message="Admin issued server update failed",
                error_traceback="\n".join(err_list) + "\n\nExecuted by the internal function",
                error_time=datetime.now(),
                error_severity="low",
                panicked=False,
                safe=False,
                fallback=False,
            )
            return err_list
        raise


def get_public_announcements():
    if FALLBACK:
        return ["<blockquote><h3>We are currently dealing with technical difficulties</h3><p>We apologize for any inconvenience and are already working to resolve the issue<p></blockquote>"]

    return [
        f"""<blockquote class="{i.announcement_type}"><h1><i class="bi bi-megaphone"></i> {i.title}</h1> {html_parse.md_to_html(i.content)}</blockquote>"""
        for i in Announcement.objects.filter(
            Q(announcement_type__in=["public", "service"]) &
            Q(Q(end_date__gte=datetime.today()) | Q(end_date__isnull=True)) &
            Q(start_date__lte=datetime.today())
        )
    ]


def get_staff_announcements():
    if FALLBACK:
        return ["<blockquote><h1>Unable to retrieve announcements</h1></blockquote>"]

    return [
        f"""<blockquote class="{i.announcement_type}"><h1><i class="bi bi-megaphone"></i> {i.title}</h1> {html_parse.md_to_html(i.content)}</blockquote>"""
        for i in Announcement.objects.filter(
            Q(announcement_type__in=["public", "service", "staff"]) &
            Q(Q(end_date__gte=datetime.today()) | Q(end_date__isnull=True)) &
            Q(start_date__lte=datetime.today())
        )
    ]
