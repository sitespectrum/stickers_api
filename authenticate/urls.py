from django.urls import path
from . import response
import api.urls

urlpatterns = [
    path("login", response.login, name="login"),
    path("discord/callback", response.discord_callback, name="discord_callback"),
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
