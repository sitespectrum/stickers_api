import hashlib
import time
from datetime import timedelta
from json import JSONDecodeError

from django.db.models import Q

from stickers_backend import utils
from stickers_backend.settings import TURNSTILE_SECRET, PASSWORD_ATTEMPT_LIMIT, DISCORD_ID, DISCORD_KEY, \
    DISCORD_CALLBACK, PASSWORD_ATTEMPT_BAN_LIMIT
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.handlers.wsgi import WSGIRequest
import json
from api.models import UserData, PasswordResetCode, ROLE_CHOICES, OAUTH_PROVIDERS, Ban, OAUTHCode
import requests
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.utils import timezone
from authenticate import wrappers
import uuid


def check_for_bans(user_data):
    if user_data.bans.filter(Q(lifted=False) & (Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))).exists():
        return JsonResponse({
            "reason": "banned",
            "error": "You are currently banned.",
            "bans": [
                {
                    "id": i.id,
                    "reason": i.reason,
                    "expires_at": i.expires_at,
                    "is_active": (not i.lifted) and (i.expires_at is None or i.expires_at > timezone.now()),
                    "banned_by": UserData.objects.get(user=i.banned_by).display_name or ("@" + i.banned_by.username) if i.banned_by else "Deleted user",
                } for i in user_data.bans.filter(Q(lifted=False) & (Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)))
            ]
        }, status=403)
    return None


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["POST"])
def validate_oauth_code(request: WSGIRequest):
    try:
        body = json.loads(request.body)
    except JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)

    OAUTHCode.objects.filter(expires_at__lt=timezone.now()).delete()
    if not OAUTHCode.objects.filter(code=body.get("code")).exists():
        return JsonResponse({"error": "Invalid code"}, status=400)

    code_obj = OAUTHCode.objects.get(code=body.get("code"))
    if code_obj.challenge != hashlib.sha256(str(body.get("code_verifier")).encode("utf-8")).hexdigest():
        return JsonResponse({"error": "Invalid code verifier"}, status=400)

    auth_login(request, code_obj.user)
    code_obj.delete()
    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@wrappers.login_required()
@require_http_methods(["POST"])
def get_oauth_code(request: WSGIRequest):
    OAUTHCode.objects.filter(expires_at__lt=timezone.now()).delete()
    try:
        body = json.loads(request.body)
    except JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)

    oauth_code = uuid.uuid4().__str__()

    if not body.get("challenge"):
        return JsonResponse({"error": "Challenge missing"}, status=400)

    OAUTHCode.objects.create(
        user=request.user,
        code=oauth_code,
        challenge=body.get("challenge"),
        expires_at=timezone.now() + timedelta(minutes=10)
    )

    return JsonResponse({"status": "Ok", "code": oauth_code}, status=200)


@require_http_methods(["POST"])
def discord_callback(request):
    try:
        body = json.loads(request.body)
    except JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)

    code = body.get("code")
    if not code:
        return JsonResponse({"error": "Invalid request"}, status=400)

    data = {
        "client_id": DISCORD_ID,
        "client_secret": DISCORD_KEY,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_CALLBACK,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
    token = r.json()

    try:
        user_info = requests.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {token['access_token']}"}
        ).json()
    except KeyError:
        return JsonResponse({"error": "Unable to login"}, status=400)

    if UserData.objects.filter(oauth_id=user_info["id"], oauth_provider="discord").exists():
        user_data = UserData.objects.get(oauth_id=user_info["id"], oauth_provider="discord")
        if user_data.role == "system":
            return JsonResponse({"error": "This is a system managed account"}, status=403)

        bans = check_for_bans(user_data)
        if bans:
            return bans

        # User is not banned — log them in
        user = user_data.user
        auth_login(request, user)
        return JsonResponse({"status": "Ok"}, status=200)

    # Otherwise, create a new user
    if User.objects.filter(username=user_info["username"]).exists():
        return JsonResponse({
            "reason": "register_failed",
            "error": "A user with this username already exists in our service. Please try anther authentication method."
        }, status=409)
    user = User.objects.create(
        username=user_info["username"],
        email=user_info["email"] if user_info.get("verified") else ""
    )
    UserData.objects.create(
        user=user,
        oauth_id=user_info["id"],
        oauth_provider="discord",
        display_name=user_info.get("global_name", user_info["username"]),
        pfp_link=f"https://cdn.discordapp.com/avatars/{user_info['id']}/{user_info['avatar']}.png",
        role="user"
    )

    return JsonResponse({"status": "Ok"}, status=200)


# Create your views here.
@require_http_methods(["POST"])
def login(request: WSGIRequest):
    try:
        body = json.loads(request.body)
    except JSONDecodeError:
        return JsonResponse({
            "status": "Error",
            "error": "Bad request"
        }, status=400)
    request.session.clear_expired()
    login_method = body.get("login_method", "builtin")

    if login_method == "telegram":
        if UserData.objects.filter(oauth_id=body.get("id"), oauth_provider="telegram").exists():
            user_data = UserData.objects.get(oauth_id=body.get("id"), oauth_provider="telegram")
            if user_data.role == "system":
                return JsonResponse({"error": "This is a system managed account"}, status=403)
            bans = check_for_bans(user_data)
            if bans:
                return bans
            user = user_data.user
            auth_login(request, user)
            return JsonResponse({"status": "Ok"}, status=200)
        else:
            if User.objects.filter(username=body.get("username")).exists():
                return JsonResponse({
                    "reason": "register_failed",
                    "error": "A user with this username already exists in our service. Please try anther authentication method."
                }, status=409)
            user = User.objects.create(
                username=body.get("username"),
            )
            user.save()
            user_data = UserData.objects.create(
                user=user,
                oauth_id=body.get("id"),
                oauth_provider="telegram",
                display_name=body.get("first_name") + (" " + body.get("last_name") if body.get("last_name") else ""),
                pfp_link=body.get("photo_url"),
                role="user"
            )
            user_data.save()
            auth_login(request, user)
            return JsonResponse({"status": "Ok"}, status=200)

    user = authenticate(request, username=body.get("username"), password=body.get("password"))
    if user is not None:
        user_data = UserData.objects.get(user=user)
        if user_data.role == "system":
            return JsonResponse({"error": "This is a system managed account"}, status=403)
        bans = check_for_bans(user_data)
        if bans:
            return bans
        if user_data.is_locked:
            return JsonResponse({"error": "Your account has been locked for security reasons. Please reset your password"}, status=423)
        auth_login(request, user)
        client_ip = utils.get_client_ip(request)
        user_data.login_failed_ips.pop(client_ip, None)
        user_data.save()
        return JsonResponse({"status": "Ok"}, status=200)
    else:
        try:
            user = User.objects.get(username=body.get("username"))
            user_data = UserData.objects.get(user=user)
            if user_data.role == "system":
                return JsonResponse({"error": "This is a system managed account"}, status=403)
            bans = check_for_bans(user_data)
            if bans:
                return bans
            user_data.unsuccessful_attempts += 1
            user_data.save()
            client_ip = utils.get_client_ip(request)
            failed_attempts = user_data.login_failed_ips.get(client_ip, None)
            if failed_attempts is None:
                user_data.login_failed_ips[client_ip] = 1
            else:
                user_data.login_failed_ips[client_ip] = failed_attempts + 1
            user_data.save()
            user_data.refresh_from_db()
            failed_attempts = user_data.login_failed_ips[client_ip]
            if failed_attempts >= PASSWORD_ATTEMPT_BAN_LIMIT:
                system_user = User.objects.get(username="system")
                ban = Ban.objects.create(
                    reason="Too many unsuccessful login attempts.",
                    expires_at=timezone.now() + timedelta(minutes=10),
                    banned_by=system_user,
                )
                user_data.bans.add(ban)
                user_data.login_failed_ips[client_ip] = 10
                user_data.save()
            if failed_attempts >= PASSWORD_ATTEMPT_LIMIT:
                time.sleep(failed_attempts)
        except User.DoesNotExist:
            pass
        return JsonResponse({"error": "Invalid username or password"}, status=403)


@require_http_methods(["GET"])
def logout(request: WSGIRequest):
    request.session.clear_expired()
    auth_logout(request)
    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@utils.maintenance_protected()
@require_http_methods(["POST"])
def register(request: WSGIRequest):
    try:
        body = json.loads(request.body)
    except JSONDecodeError:
        return JsonResponse({
            "status": "Error",
            "error": "Bad request"
        }, status=400)
    params = {
        "secret": TURNSTILE_SECRET,
        "response": body.get("cf-turnstile-response")
    }
    captcha_data = requests.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", json=params).json()
    if not captcha_data["success"]:
        return JsonResponse({"error": "CAPTCHA failed"}, status=403)

    request.session.clear_expired()
    if not body.get("username"):
        return JsonResponse({"error": "Username is required"}, status=400)
    if not body.get("password"):
        return JsonResponse({"error": "Password is required"}, status=400)
    if not body.get("email"):
        return JsonResponse({"error": "Email is required"}, status=400)
    try:
        new_user = User.objects.create_user(
            username=body.get("username"),
            password=body.get("password"),
            email=body.get("email"),
            is_staff=False
        )
    except IntegrityError:
        return JsonResponse({"error": "User with this username already exists"}, status=409)

    UserData.objects.create(
        user=new_user,
        role="user"
    )

    auth_login(request, new_user)

    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["POST"])
@wrappers.login_required()
def change_email(request: WSGIRequest):
    try:
        data = json.loads(request.body)
    except JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)

    if not data["email"]:
        return JsonResponse({
            "status": "Error",
            "error": "Invalid email address",
        }, status=400)

    request.user.email = data["email"]
    request.user.save()

    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["POST"])
@wrappers.login_required()
def change_password(request: WSGIRequest):
    try:
        data = json.loads(request.body)
    except JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)
    if not json.loads(request.body)["password"]:
        return JsonResponse({"error": "Invalid password"}, status=400)

    request.user.set_password(data["password"])
    request.user.save()

    auth_login(request, request.user)

    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["POST"])
@wrappers.login_required()
def change_display_name(request: WSGIRequest):
    try:
        data = json.loads(request.body)
    except JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)
    if not json.loads(request.body)["display_name"]:
        return JsonResponse({"error": "Invalid password"}, status=400)

    user_data = UserData.objects.get(user=request.user)
    user_data.display_name = data["display_name"]
    user_data.save()

    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["POST"])
@wrappers.login_required()
def update_profile(request: WSGIRequest):
    try:
        data = json.loads(request.body)
    except JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)

    user_data = UserData.objects.get(user=request.user)
    if "password" in data.keys():
        request.user.set_password(data["password"])
        request.user.save()
        auth_login(request, request.user)
    if "display_name" in data.keys():
        user_data.display_name = data["display_name"]
    if "pfp_link" in data.keys():
        user_data.pfp_link = data["pfp_link"]
    if "email" in data.keys():
        request.user.email = data["email"]
        request.user.save()
    user_data.save()

    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["POST"])
def forgot_password(request: WSGIRequest):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid body"}, status=400)
    try:
        params = {
            "secret": TURNSTILE_SECRET,
            "response": data["token"]
        }
    except KeyError:
        return JsonResponse({"error": "CAPTCHA failed"}, status=403)
    captcha_data = requests.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", json=params).json()
    if not captcha_data["success"]:
        return JsonResponse({"error": "CAPTCHA failed"}, status=403)
    try:
        user = User.objects.get(email=data["email"], username=data["username"])
    except User.DoesNotExist:
        return JsonResponse({"error": "Invalid username or email"}, status=404)
    code = uuid.uuid4().__str__()

    # if not modules.send_mail.password_reset(recipient=user.email, username=user.username, code=code):
    #     return JsonResponse({"error": "Email limit bypassed"}, status=500)

    PasswordResetCode.objects.create(
        for_user=user,
        code=code,
    )

    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["POST"])
def reset_password(request: WSGIRequest):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid body"}, status=400)
    try:
        code_model = PasswordResetCode.objects.get(code=data["code"])
    except PasswordResetCode.DoesNotExist:
        return JsonResponse({"error": "Invalid code"}, status=404)

    if (code_model.created_at + timedelta(days=code_model.expires_after)).date() < timezone.now().date():
        code_model.delete()
        return JsonResponse({"error": "Expired code"}, status=403)

    user = code_model.for_user

    user_data = UserData.objects.get(user=user)
    user_data.is_locked = False
    user_data.unsuccessful_attempts = 0
    user_data.save()

    user.set_password(data["password"])
    user.save()
    code_model.delete()

    return JsonResponse({"status": "Ok"}, status=200)


@require_http_methods(["GET"])
def me(request: WSGIRequest):
    if not request.user.is_authenticated:
        return JsonResponse({"status": "Error"}, status=401)
    if not UserData.objects.filter(user=request.user).exists():
        return JsonResponse({"status": "Error"}, status=403)
    user_data = UserData.objects.get(user=request.user)
    return JsonResponse({
        "username": request.user.username,
        "display_name": user_data.display_name,
        "role": dict(ROLE_CHOICES)[user_data.role],
        "email": request.user.email or "no email",
        "profile_pic": user_data.pfp_link,
        "login_method": dict(OAUTH_PROVIDERS)[user_data.oauth_provider],
    }, status=200)
