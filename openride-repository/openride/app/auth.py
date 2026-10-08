from django.contrib.auth.backends import ModelBackend
from .models import school_email,surname_matches
class SchoolBackend(ModelBackend):
    def authenticate(self,request,username=None,password=None,**kwargs):
        value=username or kwargs.get('email')
        return super().authenticate(request,username=value.strip().lower() if isinstance(value,str) else value,password=password,**kwargs)
    def user_can_authenticate(self,user):
        return bool(super().user_can_authenticate(user) and user.verified_at and school_email(user.email) and surname_matches(user.email,user.last_name))
