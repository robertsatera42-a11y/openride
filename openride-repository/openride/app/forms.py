from django import forms
from django.contrib.auth.forms import UserCreationForm,AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import User,Listing,validate_identity
from .school import SCHOOL_ADDRESS,SCHOOL_LAT,SCHOOL_LON

class StyledForm:
    def style(self):
        for f in self.fields.values():
            f.widget.attrs.setdefault('class','field')

class RegisterForm(StyledForm,UserCreationForm):
    class Meta:
        model=User
        fields=['first_name','last_name','email','password1','password2']
        labels={'first_name':'Jméno','last_name':'Příjmení','email':'Školní e-mail'}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.style()
    def clean(self):
        data=super().clean()
        if data.get('email') and data.get('last_name'):
            validate_identity(data['email'],data['last_name'])
        return data
    def clean_email(self):
        email=self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('Tento e-mail je již registrovaný.')
        return email

class LoginForm(StyledForm,AuthenticationForm):
    username=forms.EmailField(label='Školní e-mail')
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.style()

class ListingForm(StyledForm,forms.ModelForm):
    stops_text=forms.CharField(label='Zastávky (každá na samostatný řádek)',required=False,widget=forms.Textarea(attrs={'rows':2}),help_text='Volitelné. Uveď obec nebo obecné místo setkání.')
    departure=forms.SplitDateTimeField(label='Datum a čas odjezdu',widget=forms.SplitDateTimeWidget(date_attrs={'type':'date'},time_attrs={'type':'time'}))
    class Meta:
        model=Listing
        fields=['direction','origin_area','destination_area','pickup_private','destination_private','origin_lat','origin_lon','destination_lat','destination_lon','departure','flexibility_minutes','capacity','note','conditions']
        labels={'direction':'Směr','origin_area':'Výchozí oblast','destination_area':'Cílová oblast','pickup_private':'Přesné místo vyzvednutí (jen potvrzeným)','destination_private':'Přesné cílové místo (jen potvrzeným)','origin_lat':'Šířka startu','origin_lon':'Délka startu','destination_lat':'Šířka cíle','destination_lon':'Délka cíle','flexibility_minutes':'Časová flexibilita (min)','capacity':'Volná místa','note':'Poznámka','conditions':'Podmínky jízdy'}
        widgets={'note':forms.Textarea(attrs={'rows':3}),'conditions':forms.Textarea(attrs={'rows':2}),'origin_lat':forms.HiddenInput(),'origin_lon':forms.HiddenInput(),'destination_lat':forms.HiddenInput(),'destination_lon':forms.HiddenInput()}
    def __init__(self,*args,kind='ride',**kwargs):
        self.kind=kind
        super().__init__(*args,**kwargs)
        if kind=='ride':
            del self.fields['flexibility_minutes']
            if self.instance.pk: self.fields['stops_text'].initial='\n'.join(x.get('area','') for x in self.instance.stops)
        else:
            for key in ['capacity','conditions','pickup_private','destination_private','stops_text']:
                del self.fields[key]
        if not self.is_bound and not self.instance.pk:
            self.initial.update(direction='to',destination_area=SCHOOL_ADDRESS,
                                destination_lat=SCHOOL_LAT,destination_lon=SCHOOL_LON)
            if kind=='ride':
                self.initial['destination_private']=SCHOOL_ADDRESS
        self.style()
    def clean_departure(self):
        value=self.cleaned_data['departure']
        if value<=timezone.now(): raise ValidationError('Zvol budoucí termín.')
        return value
    def clean_capacity(self):
        n=self.cleaned_data.get('capacity',1)
        if n<1 or n>8: raise ValidationError('Zadej 1 až 8 míst.')
        return n
    def clean(self):
        data=super().clean()
        stops=[x.strip() for x in (data.get('stops_text') or '').splitlines() if x.strip()]
        if len(stops)>5 or any(len(x)>120 for x in stops): raise ValidationError('Zadej nejvýše pět zastávek po 120 znacích.')
        for key in ['origin','destination']:
            lat,lon=data.get(key+'_lat'),data.get(key+'_lon')
            if (lat is None)!=(lon is None):
                raise ValidationError('U místa vyber oba údaje souřadnic.')
            if lat is not None and not (-90<=lat<=90 and -180<=lon<=180):
                raise ValidationError('Neplatné souřadnice.')
        return data

class ProfileForm(StyledForm,forms.ModelForm):
    class Meta:
        model=User
        fields=['first_name','last_name','birth_date']
        labels={'first_name':'Jméno','last_name':'Příjmení','birth_date':'Datum narození'}
        widgets={'birth_date':forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.style()
    def clean_last_name(self):
        name=self.cleaned_data['last_name']
        validate_identity(self.instance.email,name)
        return name

class EmailChangeForm(StyledForm,forms.Form):
    email=forms.EmailField(label='Nový školní e-mail')
    def __init__(self,user,*args,**kwargs):
        self.user=user; super().__init__(*args,**kwargs); self.style()
    def clean_email(self):
        email=self.cleaned_data['email'].strip().lower()
        validate_identity(email,self.user.last_name)
        if User.objects.filter(email__iexact=email).exists(): raise ValidationError('E-mail se již používá.')
        return email
