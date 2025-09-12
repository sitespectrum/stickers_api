from datetime import datetime
import json
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.handlers.wsgi import WSGIRequest
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from api import models
from api.models import ErrorLog, UserData, ROLE_CHOICES
from authenticate import wrappers
from stickers_backend import utils
from stickers_backend.settings import GIT_USERNAME, GIT_PASSWORD


# Create your views here.

@login_required
@wrappers.require_role(["owner"])
def get_all(request: WSGIRequest):
    logs = ErrorLog.objects.all().order_by("-id")
    log_list = []
    for log in logs:
        log_list.append({
            "id": log.id,
            "title": str(log),
            "severity": log.error_severity,
        })
    return JsonResponse({
        "status": "Ok",
        "logs": log_list
    })


@login_required
@wrappers.require_role(["owner"])
def get_log(request: WSGIRequest, log_id):
    if not ErrorLog.objects.filter(id=log_id).exists():
        return JsonResponse({
            "status": "Error",
            "error": "Log not found.",
        }, status=404)
    log = ErrorLog.objects.get(id=log_id)
    if request.method == "DELETE":
        log.delete()
        return JsonResponse({"status": "Ok"}, status=200)
    return JsonResponse({
        "id": log.id,
        "type": log.error_type,
        "message": log.error_message,
        "traceback": log.error_traceback,
        "severity": dict(models.ERROR_SEVERITIES)[log.error_severity],
        "panicked": log.panicked,
        "time": f"{log.error_time.strftime('%Y-%m-%d %H:%M:%S')} UTC",
    })


@login_required
@wrappers.require_role(["owner"])
def reset_warning_status(request: WSGIRequest):
    utils.neutral()

    ErrorLog.objects.create(
        error_type="Service Status Reset",
        error_message="Service status reset",
        error_traceback=f"Service status has been restored to normal \n\nOperation initiated by {request.user.username}",
        error_severity="info",
        error_time=datetime.now(),
    )

    return JsonResponse({"status": "Ok"}, status=200)


@login_required
@wrappers.require_role(["owner"])
def set_service_status(request: WSGIRequest, status):
    statues = {
        "panic": utils.panic,
        "safe": utils.safe,
        "fallback": utils.fallback,
        "maintenance": utils.maintenance,
    }

    if status not in statues.keys():
        return JsonResponse({
            "status": "Error",
            "error": "Invalid status specified.",
        }, status=400)

    statues[status]()

    ErrorLog.objects.create(
        error_type="Service Status Changed",
        error_message="Service status changed",
        error_traceback=f"Service status changed to {status} \n\nOperation initiated by {request.user.username}",
        error_severity="info",
        error_time=datetime.now(),
    )

    return JsonResponse({"status": "Ok"}, status=200)


@login_required
@wrappers.require_role(["owner"])
def update(request: WSGIRequest):
    resp = utils.self_update(username=GIT_USERNAME, password=GIT_PASSWORD)
    return JsonResponse({
        "status": "Ok",
        "message": "\n".join(resp),
    }, status=200)


@login_required
@wrappers.require_role(["owner"])
@require_http_methods(["POST"])
def create_log(request: WSGIRequest):
    client_ip = request.META.get("REMOTE_ADDR")
    if client_ip not in ("127.0.0.1", "::1"):
        return JsonResponse({
            "status": "Error",
            "error": "Forbidden"
        }, status=403)
    try:
        body = json.loads(request.body)
    except json.decoder.JSONDecodeError:
        return JsonResponse({"status": "Bad Request"}, status=400)
    ErrorLog.objects.create(**body)
    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@login_required
@wrappers.require_role(["owner"])
@require_http_methods(["POST"])
def create_user(request: WSGIRequest):
    try:
        body = json.loads(request.body)
    except json.decoder.JSONDecodeError:
        return JsonResponse({"status": "Bad Request"}, status=400)
    if User.objects.filter(username=body["username"]).exists():
        return JsonResponse({
            "status": "Error",
            "error": "User already exists.",
        }, status=400)
    if body["role"] not in dict(ROLE_CHOICES).keys():
        return JsonResponse({
            "status": "Error",
            "error": "Role does not exists.",
        }, status=404)
    user = models.User.objects.create(username=body["username"])
    UserData.objects.create(
        user=user,
        role=body["role"]
    )
    user.set_password(body["password"])
    user.save()
    return JsonResponse({
        "status": "Ok",
        "message": f"User {user.username} created successfully.",
    }, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@login_required
@wrappers.require_role(["owner"])
@require_http_methods(["GET"])
def get_roles(request: WSGIRequest):
    return JsonResponse({
        "status": "Ok",
        "roles": ROLE_CHOICES,
    }, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@login_required
@wrappers.require_role(["owner"])
@require_http_methods(["POST", "DELETE"])
def modify_user(request: WSGIRequest, user_id):
    if not User.objects.filter(id=user_id).exists():
        return JsonResponse({
            "status": "Error",
            "error": "User does not exists.",
        }, status=404)

    user_obj = User.objects.get(id=user_id)

    if request.method == "DELETE":
        user_obj.delete()
        return JsonResponse({
            "status": "Ok",
        }, status=200)

    user_data = UserData.objects.get(user=user_obj)

    try:
        body = json.loads(request.body)
    except json.decoder.JSONDecodeError:
        return JsonResponse({"status": "Bad Request"}, status=400)

    if body["password"]:
        user_obj.set_password(body["password"])
        user_obj.save()

    user_data.role = body["role"]
    user_data.save()

    return JsonResponse({
        "status": "Ok",
    }, status=200)
