from django.contrib.auth import logout
from .models import school_email,surname_matches
class SchoolAccountMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        if request.user.is_authenticated:
            u=request.user
            if not u.is_active or not u.verified_at or not school_email(u.email) or not surname_matches(u.email,u.last_name):
                logout(request)
        return self.get_response(request)
