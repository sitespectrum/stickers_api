from django.urls import path
from . import response
import api.urls

urlpatterns = [
    path("login", response.login, name="login"),
    path("login/discord", response.discord_callback, name="discord_callback"),
    path("oauth/get_code", response.get_oauth_code, name="get_oauth_code"),
    path("oauth/validate_code", response.validate_oauth_code, name="validate_oauth_code"),
    path("register", response.register, name="register"),
    path("logout", response.logout, name="logout"),
    path("profile/change/email", response.change_email, name="change_email"),
    path("profile/change/password", response.change_password, name="change_password"),
    path("profile/change/display_name", response.change_display_name, name="change_display_name"),
    path("profile/change", response.update_profile, name="update_profile"),
    path("profile/me", response.me, name="me"),
    path("forgot_password", response.forgot_password, name="forgot_password"),
    path("reset_password", response.reset_password, name="reset_password"),
]
