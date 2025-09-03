# myapp/views.py
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.conf import settings
from main import handle_user_message  # main.py içindeki fonksiyon
import os, sys

BASE_DIR = settings.BASE_DIR  # manage.py ile aynı dizin
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

@method_decorator(never_cache, name="dispatch")
class ChatView(View):
    template_name = "home.html"

    def get(self, request):
        # POST→Redirect sonrası: /?once=1 geldiğinde mesajları göster, SONRA session'ı sıfırla
        if request.GET.get("once") == "1":
            shown = request.session.get("messages", [])
            request.session["messages"] = []
            request.session.modified = True
            resp = render(request, self.template_name, {"messages": shown})
            resp["Cache-Control"] = "no-store"
            return resp

        # Normal giriş/yenile: her zaman temiz başla
        request.session["messages"] = []
        request.session.modified = True
        resp = render(request, self.template_name, {"messages": []})
        resp["Cache-Control"] = "no-store"
        return resp

    def post(self, request):
        text = (request.POST.get("message") or "").strip()
        messages = request.session.get("messages", [])
        if text:
            messages.append({"role": "user", "text": text})
            try:
                reply = handle_user_message(text)
            except Exception as exc:
                reply = f"Hata: {exc}"
            messages.append({"role": "assistant", "text": reply})

        request.session["messages"] = messages
        request.session.modified = True
        # PRG: ilk GET'te gösterilsin, sonra otomatik temizlensin
        return redirect(reverse("myapp:home") + "?once=1")

def reset_chat(request):
    # Elle Temizle linki tıklandığında sıfırla
    request.session["messages"] = []
    request.session.modified = True
    return redirect(reverse("myapp:home"))
