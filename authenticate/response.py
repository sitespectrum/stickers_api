from datetime import timedelta
from json import JSONDecodeError

from stickers_backend import utils
from stickers_backend.settings import HCAPTCHA_SECRET, PASSWORD_ATTEMPT_LIMIT
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.handlers.wsgi import WSGIRequest
import json
# import modules.send_mail
from api.models import UserData, PasswordResetCode, ROLE_CHOICES
import requests
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.utils import timezone
from authenticate import wrappers
from django.contrib.auth.decorators import login_required
import uuid


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
    # I wrote this at nearly 8pm while half asleep so don't ask questions. And yes, it works.
    request.session.clear_expired()
    user = authenticate(request, username=body.get("username"), password=body.get("password"))
    if user is not None:
        user_data = UserData.objects.get(user=user)
        if user_data.is_disabled:
            return JsonResponse({"error": "Too many unsuccessful attempts. Reset password to continue"}, status=423)
        auth_login(request, user)
        user_data.unsuccessful_attempts = 0
        user_data.save()
        return JsonResponse({"status": "Ok"}, status=200)
    else:
        try:
            user = User.objects.get(username=request.POST.get("username"))
            user_data = UserData.objects.get(user=user)
            if user_data.unsuccessful_attempts == PASSWORD_ATTEMPT_LIMIT or user_data.is_disabled:
                return JsonResponse({"error": "Too many unsuccessful attempts. Reset password to continue"}, status=423)
            user_data.unsuccessful_attempts += 1
            if user_data.unsuccessful_attempts == PASSWORD_ATTEMPT_LIMIT:
                user_data.is_disabled = True
                user_data.save()
                return JsonResponse({"error": "Too many unsuccessful attempts. Reset password to continue"}, status=423)
            user_data.save()
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
def register(request: WSGIRequest, invite_code):
    params = {
        "secret": HCAPTCHA_SECRET,
        "response": request.POST.get("cf-turnstile-response")
    }
    captcha_data = requests.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", json=params).json()
    if not captcha_data["success"]:
        return JsonResponse({"error": "CAPTCHA failed"}, status=403)

    request.session.clear_expired()
    try:
        new_user = User.objects.create_user(
            username=request.POST.get("username"),
            password=request.POST.get("password"),
            email=request.POST.get("email"),
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
@login_required
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
@login_required
def change_password(request: WSGIRequest):
    try:
        data = json.loads(request.body)
    except JSONDecodeError:
        return JsonResponse({"error": "Invalid request body"}, status=400)
    if not json.loads(request.body)["password"]:
        return JsonResponse({"error": "Invalid password"}, status=400)

    request.user.set_password(data["password"])
    request.user.save()

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
            "secret": HCAPTCHA_SECRET,
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
    user_data.is_disabled = False
    user_data.unsuccessful_attempts = 0
    user_data.save()

    user.set_password(data["password"])
    user.save()
    code_model.delete()

    return JsonResponse({"status": "Ok"}, status=200)


@utils.panic_protected()
@utils.safe_protected()
@utils.fallback_protected()
@require_http_methods(["GET"])
def me(request: WSGIRequest):
    if not request.user.is_authenticated:
        return JsonResponse({"status": "Error"}, status=401)
    if not UserData.objects.filter(user=request.user).exists():
        return JsonResponse({"status": "Error"}, status=403)
    user_data = UserData.objects.get(user=request.user)
    return JsonResponse({
        "role": dict(ROLE_CHOICES)[user_data.role],
        "email": request.user.email,
    })
