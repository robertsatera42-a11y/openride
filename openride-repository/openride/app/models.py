import secrets
import unicodedata
from datetime import date
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

def fold(value):
    value=unicodedata.normalize('NFKD',value.strip().lower())
    return ''.join(c for c in value if not unicodedata.combining(c))

def school_email(email):
    if not isinstance(email,str) or email.count('@')!=1:
        return False
    local,domain=email.split('@')
    return bool(local) and domain.lower()=='opengate.cz' and len(email)<=254 and not any(c.isspace() for c in email)

def surname_matches(email,surname):
    if not school_email(email) or not surname or not surname.strip():
        return False
    local=email.split('@')[0]
    local=fold(''.join(c for c in local if not c.isdigit()))
    surname=fold(surname)
    if not local or not surname or not local.endswith(surname):
        return False
    prefix=local[:-len(surname)]
    return len(prefix)<=2 and all(c.isalpha() for c in prefix)

def validate_identity(email,surname):
    if not school_email(email):
        raise ValidationError('Použij školní e-mail na doméně @opengate.cz.')
    if not surname_matches(email,surname):
        raise ValidationError('Příjmení neodpovídá školnímu e-mailu. Zkontroluj zadané údaje.')

class User(AbstractUser):
    email=models.EmailField(unique=True)
    verified_at=models.DateTimeField(null=True,blank=True)
    driver_status=models.CharField(max_length=12,choices=[('none','Nežádá'),('pending','Čeká na schválení'),('approved','Schválen'),('rejected','Zamítnut')],default='none')
    birth_date=models.DateField(null=True,blank=True)
    parental_consent_recorded=models.BooleanField(default=False)
    parental_consent_note=models.CharField(max_length=200,blank=True)
    pending_email=models.EmailField(blank=True)
    def save(self,*args,**kwargs):
        self.email=self.email.lower()
        if self.pk:
            old=type(self).objects.filter(pk=self.pk).values_list('email',flat=True).first()
            if old and old.lower()!=self.email and not getattr(self,'_verified_email_change',False):
                self.verified_at=None; self.is_active=False; self.pending_email=''
                fields=kwargs.get('update_fields')
                if fields is not None: kwargs['update_fields']=set(fields)|{'email','username','verified_at','is_active','pending_email'}
        if self.verified_at: validate_identity(self.email,self.last_name)
        self.username=self.email
        super().save(*args,**kwargs)
    @property
    def can_drive(self):
        return self.is_active and self.verified_at and self.driver_status=='approved' and self.adult
    @property
    def adult(self):
        if not self.birth_date: return False
        today=timezone.localdate()
        return (today.year,today.month,today.day)>=(self.birth_date.year+18,self.birth_date.month,self.birth_date.day)

class EmailToken(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    digest=models.CharField(max_length=64,unique=True)
    purpose=models.CharField(max_length=20,choices=[('verify','Ověření'),('change','Změna e-mailu')])
    email=models.EmailField()
    created_at=models.DateTimeField(auto_now_add=True)
    used_at=models.DateTimeField(null=True,blank=True)

class Listing(models.Model):
    kind=models.CharField(max_length=10,choices=[('ride','Nabízím jízdu'),('demand','Hledám svezení')])
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='listings')
    direction=models.CharField(max_length=10,choices=[('to','Do školy'),('from','Ze školy')])
    origin_area=models.CharField(max_length=120)
    destination_area=models.CharField(max_length=120)
    pickup_private=models.CharField(max_length=200,blank=True)
    destination_private=models.CharField(max_length=200,blank=True)
    origin_lat=models.FloatField(null=True,blank=True)
    origin_lon=models.FloatField(null=True,blank=True)
    destination_lat=models.FloatField(null=True,blank=True)
    destination_lon=models.FloatField(null=True,blank=True)
    stops=models.JSONField(default=list,blank=True)
    departure=models.DateTimeField()
    flexibility_minutes=models.PositiveSmallIntegerField(default=0)
    capacity=models.PositiveSmallIntegerField(default=1)
    note=models.TextField(blank=True,max_length=1000)
    conditions=models.TextField(blank=True,max_length=500)
    status=models.CharField(max_length=12,choices=[('open','Aktivní'),('resolved','Vyřešeno'),('cancelled','Zrušeno'),('completed','Dokončeno')],default='open')
    route_distance_m=models.PositiveIntegerField(null=True,blank=True)
    route_duration_s=models.PositiveIntegerField(null=True,blank=True)
    route_geometry=models.JSONField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    def active_bookings(self):
        return self.bookings.filter(status__in=['confirmed','needs_reconfirm'])
    @property
    def available(self):
        return max(0,self.capacity-self.active_bookings().count()) if self.kind=='ride' else 0
    def visible_to(self,user):
        return user.is_authenticated and (user.pk==self.owner_id or self.bookings.filter(passenger=user,status__in=['confirmed','needs_reconfirm']).exists() or self.bookings.filter(ride__owner=user,status__in=['confirmed','needs_reconfirm']).exists())

class Booking(models.Model):
    ride=models.ForeignKey(Listing,on_delete=models.PROTECT,related_name='bookings',limit_choices_to={'kind':'ride'})
    passenger=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='bookings')
    demand=models.ForeignKey(Listing,on_delete=models.PROTECT,null=True,blank=True,related_name='proposals')
    initiated_by=models.CharField(max_length=10,choices=[('passenger','Cestující'),('driver','Řidič')])
    status=models.CharField(max_length=20,choices=[('pending','Čeká'),('confirmed','Potvrzeno'),('rejected','Odmítnuto'),('cancelled','Zrušeno'),('closed','Uzavřeno'),('needs_reconfirm','Znovu potvrdit')],default='pending')
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    completed_at=models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['ride','passenger'],condition=Q(status__in=['pending','confirmed','needs_reconfirm']),name='one_active_booking_per_ride_passenger')]

class Notice(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='notices')
    title=models.CharField(max_length=140)
    body=models.CharField(max_length=500)
    link=models.CharField(max_length=200,default='/openride/')
    read_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

class Report(models.Model):
    reporter=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='reports')
    listing=models.ForeignKey(Listing,on_delete=models.PROTECT,null=True,blank=True)
    description=models.TextField(max_length=1000)
    status=models.CharField(max_length=12,choices=[('open','Otevřené'),('closed','Uzavřené')],default='open')
    created_at=models.DateTimeField(auto_now_add=True)

class AuthAttempt(models.Model):
    key=models.CharField(max_length=254,db_index=True)
    at=models.DateTimeField(auto_now_add=True,db_index=True)
