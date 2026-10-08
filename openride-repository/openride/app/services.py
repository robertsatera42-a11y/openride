import hashlib,secrets
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from .models import EmailToken,Notice

def email_ready():
    return bool(settings.BREVO_API_KEY and settings.BREVO_FROM_EMAIL)

def send_token(user,purpose,email,request):
    if not email_ready(): return False
    raw=secrets.token_urlsafe(32)
    digest=hashlib.sha256(raw.encode()).hexdigest()
    link=request.build_absolute_uri('/openride/verify/'+raw+'/')
    subject='OpenRide – ověření školního e-mailu'
    body=f'Ahoj,\n\npro ověření školního e-mailu otevři tento odkaz do 24 hodin:\n{link}\n\nPokud jsi o to nežádal/a, zprávu ignoruj.\n'
    token=EmailToken.objects.create(user=user,digest=digest,purpose=purpose,email=email)
    try: send_mail(subject,body,settings.DEFAULT_FROM_EMAIL,[email],fail_silently=False)
    except Exception:
        token.delete()
        raise
    return True

def notify(user,title,body,link='/openride/'):
    Notice.objects.create(user=user,title=title,body=body,link=link)
    if email_ready():
        def send():
            try: send_mail('OpenRide – '+title,body+'\n\nOtevři OpenRide: '+link,settings.DEFAULT_FROM_EMAIL,[user.email],fail_silently=False)
            except Exception: pass
        transaction.on_commit(send)
