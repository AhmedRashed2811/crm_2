# core/urls.py
from django.urls import path
from core.views import UserListAPI

urlpatterns = [
    path("users/", UserListAPI.as_view(), name="user_list"),
]