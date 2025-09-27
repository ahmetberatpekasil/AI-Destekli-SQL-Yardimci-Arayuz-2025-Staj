# myapp/views.py
from django.shortcuts import render, redirect
from django.views import View
from django.conf import settings
from typing import List, Dict
from pathlib import Path
import sys

# --- main.py PROJE KÖKÜNDE (manage.py ile aynı klasör) ---
BASE_DIR = Path(getattr(settings, "BASE_DIR", Path(__file__).resolve().parents[2]))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    # main.py içinde: def handle_user_message(user_text: str, history: list | None = None) -> str
    from main import handle_user_message
except ImportError as e:
    raise ImportError(
        "main.py proje kökünde olmalı ve içinde handle_user_message fonksiyonu bulunmalı."
    ) from e


class ChatView(View):
    template_name = "home.html"

    def get(self, request):
        # ?reset=1 ile sohbeti temizle (isteğe bağlı)
        if request.GET.get("reset") == "1":
            request.session.pop("history", None)

        messages: List[Dict[str, str]] = request.session.get("history", [])
        return render(request, self.template_name, {"messages": messages})

    def post(self, request):
        user_text = (request.POST.get("message") or "").strip()
        if not user_text:
            return redirect("myapp:home")  # namespaced

        # Geçmişi al
        history: List[Dict[str, str]] = request.session.get("history", [])

        # main.handle_user_message geçmişi destekliyorsa verelim
        try:
            bot_reply = handle_user_message(user_text=user_text, history=history)
        except TypeError:
            bot_reply = handle_user_message(user_text)

        # Geçmişi güncelle
        history.append({"role": "user", "text": user_text})
        history.append({"role": "bot", "text": str(bot_reply)})
        request.session["history"] = history
        request.session.modified = True

        # PRG: yenilemede form yeniden post edilmesin
        return redirect("myapp:home")


def reset_chat(request):
    request.session.pop("history", None)
    return redirect("myapp:home")
