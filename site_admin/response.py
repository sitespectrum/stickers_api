import time
from datetime import datetime
import json
from django.utils import timezone

from django.contrib.auth.models import User
from django.core.handlers.wsgi import WSGIRequest
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from api import models
from api.models import ErrorLog, UserData, ROLE_CHOICES, OAUTH_PROVIDERS, Ban
from authenticate import wrappers
from stickers_backend import utils
from stickers_backend.settings import GIT_USERNAME, GIT_PASSWORD
from django.core.paginator import Paginator
from django.db.models import Q
from qsessions.models import Session


# Create your views here.

@wrappers.login_required()
@wrappers.require_role(["owner"])
def get_all_logs(request: WSGIRequest):
    page = request.GET.get("page", 1)
    try:
        page = int(page)
    except ValueError:
        return JsonResponse({
            "status": "Error",
            "error": "Page must be an integer.",
        }, status=400)
    logs = ErrorLog.objects.all().order_by("-id")
    log_list = []
    for log in logs:
        log_list.append({
            "id": log.id,
            "title": str(log),
            "severity": log.error_severity,
        })
    pages = Paginator(log_list, 50)
    if page > pages.num_pages:
        return JsonResponse({
            "status": "Error",
            "error": "Page does not exist.",
        }, status=404)
    return JsonResponse({
        "status": "Ok",
        "logs": pages.page(page).object_list,
        "pages": pages.num_pages,
        "page": page,
    })


@wrappers.login_required()
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
        "time": f"{log.error_time.strftime('%Y. %m. %d. %H:%M:%S')} UTC",
        "timestamp": log.error_time,
    })


@wrappers.login_required()
@wrappers.require_role(["owner"])
def get_status(request: WSGIRequest):
    return JsonResponse({
        "status": "Ok",
        "server_operation_title": utils.statuses[utils.get_status()],
        "server_operation_code": utils.get_status(),
        "statuses": utils.statuses,
    }, status=200)


@wrappers.login_required()
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


@wrappers.login_required()
@wrappers.require_role(["owner"])
@require_http_methods(["POST"])
def set_service_status(request: WSGIRequest, status):
    statues = {
        "panic": utils.panic,
        "safe": utils.safe,
        "fallback": utils.fallback,
        "maintenance": utils.maintenance,
        "normal": utils.neutral,
    }

    if status not in statues.keys():
        return JsonResponse({
            "status": "Error",
            "error": "Invalid status specified.",
        }, status=400)

    if status == utils.get_status():
        return JsonResponse({
            "status": "Not changed"
        }, status=200)

    statues[status]()

    ErrorLog.objects.create(
        error_type="Service Status Changed",
        error_message="Service status changed",
        error_traceback=f"Service status changed to {status} \n\nOperation initiated by {request.user.username}",
        error_severity="info",
        error_time=datetime.now(),
    )

    return JsonResponse({"status": "Ok"}, status=200)


@wrappers.login_required()
@wrappers.require_role(["owner"])
def update(request: WSGIRequest):
    resp = utils.self_update(username=GIT_USERNAME, password=GIT_PASSWORD)
    return JsonResponse({
        "status": "Ok",
        "message": "\n".join(resp),
    }, status=200)


@wrappers.login_required()
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
@utils.fallback_protected()
@wrappers.login_required()
@wrappers.require_role(["owner", "moderator"])
@require_http_methods(["GET"])
def get_users(request: WSGIRequest):
    users = UserData.objects.filter(~Q(user=request.user) & ~Q(role="system"))
    user_list = []
    for user in users:
        user_list.append({
            "id": user.user.id,
            "username": user.user.username,
            "role": user.role,
        })
    return JsonResponse({
        "status": "Ok",
        "users": user_list
    }, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@wrappers.login_required()
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
    }, status=201)


@utils.panic_protected()
@utils.fallback_protected()
@wrappers.login_required()
@wrappers.require_role(["owner", "moderator"])
@require_http_methods(["GET"])
def get_roles(request: WSGIRequest):
    roles = dict(ROLE_CHOICES)
    roles.pop("system", None)
    return JsonResponse({
        "status": "Ok",
        "roles": roles
    }, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@wrappers.login_required()
@wrappers.require_role(["owner", "moderator"])
@require_http_methods(["PATCH", "GET"])
def modify_user(request: WSGIRequest, user_id):
    if not User.objects.filter(id=user_id).exists():
        return JsonResponse({
            "status": "Error",
            "error": "User does not exists.",
        }, status=404)

    user_obj = User.objects.get(id=user_id)
    user_data = UserData.objects.get(user=user_obj)
    current_user = UserData.objects.get(user=request.user)
    if user_data.role == "system":
        return JsonResponse({
            "status": "Error",
            "error": "This is a system managed account.",
        }, status=403)

    if user_obj.id == request.user.id:
        return JsonResponse({
            "status": "Error",
            "error": "You cannot modify yourself.",
        }, status=400)

    if request.method == "GET":
        return JsonResponse({
            "status": "Ok",
            "id": user_obj.id,
            "username": user_obj.username,
            "role": user_data.role,
            "display_name": user_data.display_name,
            "email": user_obj.email,
            "stickers": user_data.sticker_packs.count(),
            "favourites": user_data.favourite_stickers.count(),
            "login_method": dict(OAUTH_PROVIDERS)[user_data.oauth_provider],
            "login_method_code": user_data.oauth_provider,
            "total_bans": len(Ban.objects.filter(user=user_obj)),
            "active_bans": len(Ban.objects.filter(Q(user=user_obj) & Q(lifted=False) & (Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)))),
        })

    try:
        body = json.loads(request.body)
    except json.decoder.JSONDecodeError:
        return JsonResponse({"status": "Bad Request"}, status=400)

    if current_user.role != "owner":
        return JsonResponse({
            "status": "Error",
            "error": "You cannot change user data",
        }, status=403)

    if body.get("role") == "system":
        return JsonResponse({
            "status": "Error",
            "error": "This role cannot be assigned",
        }, status=403)

    if body.get("password"):
        user_obj.set_password(body["password"])
        user_obj.save()

    if body.get("role"):
        user_data.role = body["role"]
        user_data.save()
    return JsonResponse({
        "status": "Ok",
    }, status=200)


@utils.panic_protected()
@utils.fallback_protected()
@wrappers.login_required()
@wrappers.require_role(["owner", "moderator"])
@require_http_methods(["GET"])
def bans(request: WSGIRequest, user_id):
    if not User.objects.filter(id=user_id).exists():
        return JsonResponse({
            "status": "Error",
            "error": "User does not exists.",
        }, status=404)
    user_data = UserData.objects.get(user=User.objects.get(id=user_id))
    if request.method == "GET":
        only_active = request.GET.get("active_only", "false").lower() == "true"

        now = timezone.now()
        active_q = Q(user=user_data.user) & Q(lifted=False) & (Q(expires_at__gt=now) | Q(expires_at__isnull=True))

        bans_qs = Ban.objects.filter(active_q) if only_active else Ban.objects.filter(user=user_data.user)

        return JsonResponse({
            "status": "Ok",
            "bans": [
                {
                    "id": i.id,
                    "reason": i.reason,
                    "expires_at": i.expires_at,
                    "is_active": (not i.lifted) and (i.expires_at is None or i.expires_at > now),
                    "can_be_revoked": i.can_be_lifted,
                    "lifted_by": (
                        (UserData.objects.get(user=i.lifted_by).display_name or ("@" + i.lifted_by.username))
                        if i.lifted_by else "Deleted user"
                        if i.lifted else ""
                    ),
                    "banned_by": UserData.objects.get(user=i.banned_by).display_name or ("@" + i.banned_by.username) if i.banned_by else "Deleted user",
                }
                for i in bans_qs.order_by("expires_at")
            ]
        })
    return JsonResponse({
        "status": "Ok",
    }, status=200)


@utils.panic_protected()
@utils.fallback_protected()
@wrappers.login_required()
@wrappers.require_role(["owner", "moderator"])
@require_http_methods(["POST", "DELETE"])
def ban_user(request: WSGIRequest, user_id):
    if not User.objects.filter(id=user_id).exists():
        return JsonResponse({
            "status": "Error",
            "error": "User does not exists.",
        }, status=404)
    user_data = UserData.objects.get(user=User.objects.get(id=user_id))
    if user_data.role == "owner":
        return JsonResponse({
            "status": "Error",
            "error": "You cannot ban an owner",
        }, status=403)
    if user_data.role == "system":
        return JsonResponse({
            "status": "Error",
            "error": "You cannot ban a system user",
        }, status=403)
    try:
        body = json.loads(request.body)
    except json.decoder.JSONDecodeError:
        return JsonResponse({"status": "Bad Request"}, status=400)
    if request.method == "DELETE":
        if not Ban.objects.filter(id=body["ban_id"]).exists():
            return JsonResponse({
                "status": "Error",
                "error": "Ban does not exists",
            }, status=404)
        ban = Ban.objects.get(id=body["ban_id"])
        if not ban.can_be_lifted:
            return JsonResponse({
                "status": "Error",
                "error": "This ban cannot be lifted",
            }, status=403)
        ban.lifted = True
        ban.lifted_by = request.user
        ban.save()
        user_data.save()
        return JsonResponse({
            "status": "Ok",
        }, status=204)
    expires_at_date = datetime.fromisoformat(body.get("expires_at")).date() if body.get("expires_at") else None
    if expires_at_date:
        expires_at_date = timezone.make_aware(datetime.combine(expires_at_date, datetime.min.time()))
    ban_reason = body.get("reason") or "Banned by moderator"
    if expires_at_date:
        if expires_at_date < timezone.now():
            return JsonResponse({
                "status": "Error",
                "error": "Expiry date must be in the future.",
            }, status=400)
    Ban.objects.create(
        user=user_data.user,
        reason=ban_reason,
        expires_at=expires_at_date,
        can_be_lifted=True,
        banned_by=request.user,
    )

    _logout_user(user_id)

    return JsonResponse({
        "status": "Ok",
    }, status=201)


@utils.panic_protected()
@utils.fallback_protected()
@wrappers.login_required()
@wrappers.require_role(["owner", "moderator"])
@require_http_methods(["GET"])
def search_users(request: WSGIRequest):
    users = User.objects.filter(username__icontains=request.GET.get("q", ""))
    user_list = []
    for user in users:
        user_list.append({
            "id": user.id,
            "username": user.username,
            "role": dict(ROLE_CHOICES)[UserData.objects.get(user=user).role],
        })
    return JsonResponse({
        "status": "Ok",
        "users": user_list
    }, status=200)


def _logout_user(user_id):
    Session.objects.filter(user__id=user_id).delete()


@utils.panic_protected()
@utils.fallback_protected()
@utils.safe_protected()
@wrappers.login_required()
@wrappers.require_role(["owner", "moderator"])
@require_http_methods(["POST"])
def logout_user(request: WSGIRequest):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid body"}, status=400)
    if not body.get("user_id"):
        return JsonResponse({"error": "Missing user_id"}, status=400)
    if not User.objects.filter(id=body["user_id"]).exists():
        return JsonResponse({"error": "User not found"}, status=404)
    _logout_user(body["user_id"])

    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.fallback_protected()
@utils.safe_protected()
@wrappers.login_required()
@wrappers.require_role(["owner"])
@require_http_methods(["POST"])
def lock_user(request: WSGIRequest):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid body"}, status=400)
    if not body.get("user_id"):
        return JsonResponse({"error": "Missing user_id"}, status=400)
    if not User.objects.filter(id=body["user_id"]).exists():
        return JsonResponse({"error": "User not found"}, status=404)
    user = UserData.objects.get(user=User.objects.get(id=body["user_id"]))
    user.is_locked = True
    user.save()

    _logout_user(body["user_id"])

    return JsonResponse({"status": "Ok"}, status=200)
