# myapp/urls.py
from django.urls import path
from .views import ChatView, reset_chat

app_name = "myapp"

urlpatterns = [
    path("", ChatView.as_view(), name="home"),
    path("reset/", reset_chat, name="reset_chat"),
]
