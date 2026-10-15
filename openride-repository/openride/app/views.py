import hashlib,json,requests
from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login,logout,update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm,PasswordResetForm,SetPasswordForm
from django.core.exceptions import ValidationError
from django.db import IntegrityError,transaction
from django.db.models import Q,Count
from django.http import Http404,HttpResponse,JsonResponse
from django.core.cache import cache
from django.shortcuts import render,redirect,get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .auth import SchoolBackend
from .forms import RegisterForm,LoginForm,ListingForm,ProfileForm,EmailChangeForm
from .models import User,EmailToken,Listing,Booking,Notice,Report,AuthAttempt,school_email,surname_matches
from .services import send_token,notify,email_ready

P='/openride/'
def health(request): return HttpResponse('ok',content_type='text/plain')
def require_school(view):
    @login_required
    def inner(request,*args,**kwargs):
        u=request.user
        if not u.verified_at or not school_email(u.email) or not surname_matches(u.email,u.last_name):
            logout(request); return redirect(P+'login/')
        return view(request,*args,**kwargs)
    return inner

def register(request):
    if request.user.is_authenticated: return redirect(P)
    form=RegisterForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        user=form.save(commit=False); user.is_active=False; user.save()
        try: sent=send_token(user,'verify',user.email,request)
        except Exception: sent=False
        messages.success(request,'Účet je založený. '+('Ověř školní e-mail odkazem v doručené zprávě.' if sent else 'Ověřovací e-mail zatím nelze odeslat. Účet zůstává neaktivní; zkus to později.'))
        return redirect(P+'login/')
    return render(request,'auth_form.html',{'title':'Přidej se k OpenRide','form':form,'submit':'Vytvořit účet','subtext':'Jen pro školní e-mail @opengate.cz. Aktivace vyžaduje ověření odkazu.','extra_link':(P+'login/','Už mám účet')})

def verify(request,token):
    digest=hashlib.sha256(token.encode()).hexdigest()
    with transaction.atomic():
        item=EmailToken.objects.select_for_update().filter(digest=digest,used_at__isnull=True,created_at__gte=timezone.now()-timedelta(hours=24)).first()
        if not item: messages.error(request,'Odkaz vypršel nebo už byl použit.'); return redirect(P+'login/')
        user=User.objects.select_for_update().get(pk=item.user_id)
        if not school_email(item.email) or not surname_matches(item.email,user.last_name):
            messages.error(request,'Školní e-mail a příjmení už neodpovídají.'); return redirect(P+'login/')
        if item.purpose=='change':
            if user.pending_email.lower()!=item.email.lower() or User.objects.filter(email__iexact=item.email).exclude(pk=user.pk).exists():
                messages.error(request,'Změna e-mailu už není platná.'); return redirect(P+'profile/')
            user.email=item.email; user.pending_email=''; user._verified_email_change=True
        elif user.email.lower()!=item.email.lower():
            messages.error(request,'Odkaz neodpovídá účtu.'); return redirect(P+'login/')
        user.verified_at=timezone.now(); user.is_active=True; user.save()
        item.used_at=timezone.now(); item.save(update_fields=['used_at'])
        EmailToken.objects.filter(user=user,used_at__isnull=True).exclude(pk=item.pk).update(used_at=timezone.now())
    messages.success(request,'Školní e-mail je ověřený. Můžeš se přihlásit.')
    return redirect(P+'login/')

def signin(request):
    if request.user.is_authenticated: return redirect(P)
    form=LoginForm(request,data=request.POST or None)
    if request.method=='POST':
        email=(request.POST.get('username') or '').strip().lower()
        AuthAttempt.objects.filter(at__lt=timezone.now()-timedelta(days=7)).delete()
        recent=AuthAttempt.objects.filter(key=email[:254],at__gte=timezone.now()-timedelta(minutes=15)).count()
        if recent>=5:
            messages.error(request,'Příliš mnoho pokusů. Zkus to za 15 minut.')
        elif form.is_valid():
            AuthAttempt.objects.filter(key=email[:254]).delete()
            login(request,form.get_user())
            return redirect(P)
        else:
            AuthAttempt.objects.create(key=email[:254])
            messages.error(request,'Přihlášení se nepovedlo. Zkontroluj údaje a ověření e-mailu.')
    return render(request,'auth_form.html',{'title':'Vítej zpátky','form':form,'submit':'Přihlásit se','extra_link':(P+'register/','Vytvořit účet'),'reset_link':True,'resend_link':True})

@require_POST
def signout(request): logout(request); return redirect(P+'login/')

@require_POST
def resend(request):
    email=(request.POST.get('email') or '').strip().lower()
    user=User.objects.filter(email__iexact=email,is_active=False,verified_at__isnull=True).first()
    if user and school_email(user.email) and surname_matches(user.email,user.last_name) and EmailToken.objects.filter(user=user,purpose='verify',created_at__gte=timezone.now()-timedelta(hours=1)).count()<3:
        try: send_token(user,'verify',user.email,request)
        except Exception: pass
    messages.info(request,'Pokud neověřený účet existuje a pošta funguje, nový odkaz byl odeslán.')
    return redirect(P+'login/')

def reset_password(request):
    form=PasswordResetForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        email=form.cleaned_data['email'].lower()
        if email_ready() and User.objects.filter(email__iexact=email,is_active=True,verified_at__isnull=False).exists() and AuthAttempt.objects.filter(key=('reset:'+email)[:254],at__gte=timezone.now()-timedelta(hours=1)).count()<3:
            AuthAttempt.objects.create(key=('reset:'+email)[:254])
            try: form.save(request=request,use_https=request.is_secure(),from_email=settings.DEFAULT_FROM_EMAIL,email_template_name='reset_email.txt',subject_template_name='reset_subject.txt')
            except Exception: pass
        messages.info(request,'Pokud je účet aktivní a pošta funguje, poslali jsme odkaz pro obnovu.')
        return redirect(P+'login/')
    return render(request,'auth_form.html',{'title':'Obnova hesla','form':form,'submit':'Poslat odkaz'})

@require_school
def marketplace(request):
    qs=Listing.objects.filter(status='open',departure__gte=timezone.now()).select_related('owner').order_by('departure')
    for field in ['direction','kind']:
        value=request.GET.get(field)
        if value in (['to','from'] if field=='direction' else ['ride','demand']): qs=qs.filter(**{field:value})
    area=request.GET.get('area','').strip()[:100]
    if area: qs=qs.filter(Q(origin_area__icontains=area)|Q(destination_area__icontains=area))
    day=request.GET.get('date')
    if day: qs=qs.filter(departure__date=day)
    after=request.GET.get('after')
    if after: qs=qs.filter(departure__time__gte=after)
    rides=list(qs.filter(kind='ride')[:100]); demands=list(qs.filter(kind='demand')[:100])
    if request.GET.get('seats')=='1': rides=[r for r in rides if r.available>0]
    return render(request,'market.html',{'rides':rides,'demands':demands,'filters':request.GET})

@require_school
def listing_new(request,kind):
    if kind not in ['ride','demand']: raise Http404
    if kind=='ride' and not request.user.can_drive:
        messages.error(request,'Nabídky jízd mohou zveřejňovat jen schválení plnoletí řidiči.')
        return redirect(P+'profile/')
    form=ListingForm(request.POST or None,kind=kind)
    if request.method=='POST' and form.is_valid():
        obj=form.save(commit=False); obj.kind=kind; obj.owner=request.user
        if kind=='demand': obj.capacity=1
        obj.stops=resolve_stops(form.cleaned_data.get('stops_text','')) if kind=='ride' else []
        obj.save()
        messages.success(request,'Inzerát je zveřejněný.')
        return redirect(P+'listing/'+str(obj.pk)+'/')
    return render(request,'listing_form.html',{'form':form,'kind':kind,'title':'Nabízím jízdu' if kind=='ride' else 'Hledám svezení'})

@require_school
def listing_detail(request,pk):
    obj=get_object_or_404(Listing.objects.select_related('owner'),pk=pk)
    own=obj.owner_id==request.user.pk
    private=obj.visible_to(request.user)
    bookings=obj.bookings.select_related('passenger','ride','demand').order_by('-created_at') if obj.kind=='ride' and own else []
    proposals=obj.proposals.select_related('ride','ride__owner').order_by('-created_at') if obj.kind=='demand' and own else []
    my_booking=obj.bookings.filter(passenger=request.user,status__in=['pending','confirmed','needs_reconfirm']).first() if obj.kind=='ride' else None
    return render(request,'detail.html',{'item':obj,'own':own,'private':private,'bookings':bookings,'proposals':proposals,'my_booking':my_booking,'past':obj.departure<timezone.now(),'my_rides':Listing.objects.filter(owner=request.user,kind='ride',status='open',departure__gte=timezone.now()) if obj.kind=='demand' and not own and request.user.can_drive else []})

@require_school
def listing_edit(request,pk):
    obj=get_object_or_404(Listing,pk=pk,owner=request.user,status='open')
    form=ListingForm(request.POST or None,instance=obj,kind=obj.kind)
    if request.method=='POST' and form.is_valid():
        new_stops=resolve_stops(form.cleaned_data.get('stops_text','')) if obj.kind=='ride' else []
        with transaction.atomic():
            obj=Listing.objects.select_for_update().get(pk=pk)
            confirmed=obj.active_bookings().select_related('passenger')
            if obj.kind=='ride' and form.cleaned_data.get('capacity',obj.capacity)<confirmed.count():
                form.add_error('capacity','Nelze snížit počet míst pod počet potvrzených účastníků.')
            else:
                old=(obj.origin_area,obj.destination_area,obj.departure,obj.origin_lat,obj.origin_lon,obj.destination_lat,obj.destination_lon,obj.pickup_private,obj.destination_private,obj.stops)
                edited=form.save(commit=False)
                edited.stops=new_stops
                changed=old!=(edited.origin_area,edited.destination_area,edited.departure,edited.origin_lat,edited.origin_lon,edited.destination_lat,edited.destination_lon,edited.pickup_private,edited.destination_private,edited.stops)
                edited.route_geometry=None; edited.route_distance_m=None; edited.route_duration_s=None
                edited.save()
                if changed and obj.kind=='ride':
                    for b in confirmed:
                        b.status='needs_reconfirm'; b.save(update_fields=['status','updated_at'])
                        notify(b.passenger,'Jízda se změnila','Zkontroluj novou trasu nebo čas a potvrď účast znovu.',P+'listing/'+str(pk)+'/')
                messages.success(request,'Inzerát byl upravený.')
                return redirect(P+'listing/'+str(pk)+'/')
    return render(request,'listing_form.html',{'form':form,'kind':obj.kind,'title':'Upravit inzerát'})

@require_school
@require_POST
def listing_cancel(request,pk):
    with transaction.atomic():
        obj=get_object_or_404(Listing.objects.select_for_update(),pk=pk,owner=request.user)
        if obj.status=='open' or obj.status=='resolved':
            obj.status='cancelled'; obj.save(update_fields=['status','updated_at'])
            if obj.kind=='ride':
                for b in obj.bookings.filter(status__in=['pending','confirmed','needs_reconfirm']).select_related('passenger','demand'):
                    b.status='cancelled'; b.save(update_fields=['status','updated_at'])
                    if b.demand_id and b.demand.status=='resolved':
                        b.demand.status='open'; b.demand.save(update_fields=['status','updated_at'])
                    notify(b.passenger,'Jízda byla zrušena','Řidič zrušil jízdu. Případná poptávka byla znovu otevřena.',P+'listing/'+str(pk)+'/')
    return redirect(P+'mine/')

@require_school
@require_POST
def request_seat(request,pk):
    with transaction.atomic():
        ride=get_object_or_404(Listing.objects.select_for_update(),pk=pk,kind='ride',status='open',departure__gte=timezone.now())
        if ride.owner_id==request.user.pk or ride.available<1:
            messages.error(request,'Místo není dostupné.'); return redirect(P+'listing/'+str(pk)+'/')
        if Booking.objects.filter(ride=ride,passenger=request.user,status__in=['pending','confirmed','needs_reconfirm']).exists():
            messages.info(request,'Na tuto jízdu už máš aktivní žádost.'); return redirect(P+'listing/'+str(pk)+'/')
        try: Booking.objects.create(ride=ride,passenger=request.user,initiated_by='passenger')
        except IntegrityError: pass
        else: notify(ride.owner,'Nová žádost o místo',request.user.get_full_name()+' žádá o místo.',P+'listing/'+str(pk)+'/')
    return redirect(P+'listing/'+str(pk)+'/')

@require_school
@require_POST
def propose(request,pk):
    demand=get_object_or_404(Listing,pk=pk,kind='demand',status='open',departure__gte=timezone.now())
    ride_id=request.POST.get('ride')
    with transaction.atomic():
        ride=get_object_or_404(Listing.objects.select_for_update(),pk=ride_id,owner=request.user,kind='ride',status='open',departure__gte=timezone.now())
        if not request.user.can_drive or demand.owner_id==request.user.pk or ride.available<1:
            messages.error(request,'Tuto jízdu nelze nabídnout.'); return redirect(P+'listing/'+str(pk)+'/')
        if Booking.objects.filter(ride=ride,passenger=demand.owner,status__in=['pending','confirmed','needs_reconfirm']).exists():
            messages.error(request,'Pro tuto jízdu už reakce existuje.'); return redirect(P+'listing/'+str(pk)+'/')
        Booking.objects.create(ride=ride,passenger=demand.owner,demand=demand,initiated_by='driver')
        notify(demand.owner,'Řidič nabídl jízdu',request.user.get_full_name()+' reagoval na tvoji poptávku.',P+'listing/'+str(pk)+'/')
    return redirect(P+'listing/'+str(pk)+'/')

@require_school
@require_POST
def booking_action(request,pk,action):
    if action not in ['accept','reject','cancel','reconfirm']: raise Http404
    with transaction.atomic():
        b=get_object_or_404(Booking.objects.select_related('ride','demand'),pk=pk)
        ride=Listing.objects.select_for_update().get(pk=b.ride_id)
        demand=Listing.objects.select_for_update().get(pk=b.demand_id) if b.demand_id else None
        b=Booking.objects.select_for_update().get(pk=pk)
        passenger=request.user.pk==b.passenger_id
        driver=request.user.pk==ride.owner_id
        if action=='accept':
            allowed=(b.initiated_by=='passenger' and driver) or (b.initiated_by=='driver' and passenger)
            if not allowed or b.status!='pending': raise Http404
            if ride.status!='open' or ride.departure<=timezone.now() or ride.available<1 or (demand and demand.status!='open'):
                messages.error(request,'Jízda nebo místo už není dostupné.'); return redirect(P+'listing/'+str(ride.pk)+'/')
            b.status='confirmed'; b.save(update_fields=['status','updated_at'])
            if demand:
                demand.status='resolved'; demand.save(update_fields=['status','updated_at'])
                Booking.objects.filter(demand=demand,status='pending').exclude(pk=b.pk).update(status='closed')
            notify(b.passenger if driver else ride.owner,'Rezervace potvrzena','Místo v jízdě bylo potvrzeno.',P+'listing/'+str(ride.pk)+'/')
        elif action=='reject':
            allowed=(b.initiated_by=='passenger' and driver) or (b.initiated_by=='driver' and passenger)
            if not allowed or b.status!='pending': raise Http404
            b.status='rejected'; b.save(update_fields=['status','updated_at'])
            notify(b.passenger if driver else ride.owner,'Reakce odmítnuta','Reakce na jízdu byla odmítnuta.',P+'listing/'+str(ride.pk)+'/')
        elif action=='reconfirm':
            if not passenger or b.status!='needs_reconfirm' or ride.status!='open': raise Http404
            b.status='confirmed'; b.save(update_fields=['status','updated_at'])
            notify(ride.owner,'Účast znovu potvrzena',b.passenger.get_full_name()+' potvrdil/a změněnou jízdu.',P+'listing/'+str(ride.pk)+'/')
        else:
            if (not passenger and not driver) or b.status not in ['pending','confirmed','needs_reconfirm'] or ride.status=='completed': raise Http404
            b.status='cancelled'; b.save(update_fields=['status','updated_at'])
            if demand and demand.status=='resolved':
                demand.status='open'; demand.save(update_fields=['status','updated_at'])
            notify(ride.owner if passenger else b.passenger,'Účast zrušena','Účast v jízdě byla zrušena.',P+'listing/'+str(ride.pk)+'/')
    return redirect(P+'listing/'+str(ride.pk)+'/')

@require_school
def mine(request):
    own=Listing.objects.filter(owner=request.user).order_by('departure')
    return render(request,'mine.html',{'listings':own.filter(status='open',departure__gte=timezone.now()),'history':own.filter(Q(status__in=['cancelled','completed','resolved'])|Q(departure__lt=timezone.now())).order_by('-departure')[:100],'bookings':Booking.objects.filter(passenger=request.user).select_related('ride','ride__owner').order_by('-created_at')[:100],'incoming':Booking.objects.filter(ride__owner=request.user,status='pending').select_related('passenger','ride','demand')})

@require_school
def profile(request):
    form=ProfileForm(request.POST or None,instance=request.user)
    if request.method=='POST' and form.is_valid(): form.save(); messages.success(request,'Profil je uložený.'); return redirect(P+'profile/')
    return render(request,'profile.html',{'form':form,'email_form':EmailChangeForm(request.user),'password_form':PasswordChangeForm(request.user)})

@require_school
@require_POST
def change_email(request):
    form=EmailChangeForm(request.user,request.POST)
    if form.is_valid():
        try: sent=send_token(request.user,'change',form.cleaned_data['email'],request)
        except Exception: sent=False
        if sent:
            request.user.pending_email=form.cleaned_data['email']; request.user.save(update_fields=['pending_email'])
            messages.success(request,'Na nový školní e-mail jsme poslali ověřovací odkaz. Do ověření platí původní adresa.')
        else: messages.error(request,'Ověřovací e-mail se nepodařilo odeslat; adresa zůstala beze změny.')
    else:
        for error in form.non_field_errors(): messages.error(request,error)
        for errors in form.errors.values():
            for error in errors: messages.error(request,error)
    return redirect(P+'profile/')

@require_school
@require_POST
def change_password(request):
    form=PasswordChangeForm(request.user,request.POST)
    if form.is_valid(): form.save(); update_session_auth_hash(request,request.user); messages.success(request,'Heslo bylo změněno.')
    else: messages.error(request,'Heslo se nepodařilo změnit. Zkontroluj formulář.')
    return redirect(P+'profile/')

@require_school
@require_POST
def driver_apply(request):
    u=request.user
    if u.driver_status in ['pending','approved']:
        messages.info(request,'Žádost o roli řidiče už evidujeme.'); return redirect(P+'profile/')
    if not u.adult: messages.error(request,'Řidičem může být pouze plnoletý uživatel. Vyplň datum narození v profilu.')
    else:
        u.driver_status='pending'; u.save(update_fields=['driver_status'])
        for admin in User.objects.filter(is_staff=True,is_active=True,verified_at__isnull=False): notify(admin,'Nová žádost řidiče',u.get_full_name()+' žádá o schválení řidiče.',P+'admin/')
        messages.success(request,'Žádost o roli řidiče byla odeslána správci.')
    return redirect(P+'profile/')

@require_school
def notices(request):
    items=Notice.objects.filter(user=request.user).order_by('-created_at')[:100]
    return render(request,'notices.html',{'items':items})

@require_school
@require_POST
def notice_read(request,pk):
    item=get_object_or_404(Notice,pk=pk,user=request.user); item.read_at=timezone.now(); item.save(update_fields=['read_at'])
    return redirect(item.link if item.link.startswith(P) else P)

@require_school
@require_POST
def report(request,pk):
    listing=get_object_or_404(Listing,pk=pk)
    desc=(request.POST.get('description') or '').strip()[:1000]
    if len(desc)<10: messages.error(request,'Popiš problém alespoň deseti znaky.')
    else:
        Report.objects.create(reporter=request.user,listing=listing,description=desc)
        for admin in User.objects.filter(is_staff=True,is_active=True,verified_at__isnull=False): notify(admin,'Nové nahlášení','Byl nahlášen problém s inzerátem.',P+'admin/')
        messages.success(request,'Nahlášení bylo odesláno správci.')
    return redirect(P+'listing/'+str(pk)+'/')

@require_school
def admin_panel(request):
    if not request.user.is_staff: raise Http404
    completed=Booking.objects.filter(completed_at__isnull=False).count()
    confirmed=Booking.objects.filter(status='confirmed',ride__status='open').count()
    return render(request,'admin_panel.html',{'drivers':User.objects.filter(driver_status='pending'),'reports':Report.objects.filter(status='open').select_related('reporter','listing'),'users':User.objects.order_by('-date_joined')[:100],'stats':{'completed':completed,'confirmed':confirmed,'rides':Listing.objects.filter(kind='ride',status='completed').count()}})

@require_school
@require_POST
def admin_action(request,kind,pk,action):
    if not request.user.is_staff: raise Http404
    if kind=='driver' and action in ['approve','reject']:
        u=get_object_or_404(User,pk=pk,driver_status='pending',verified_at__isnull=False)
        if not u.adult or not school_email(u.email) or not surname_matches(u.email,u.last_name): raise Http404
        u.driver_status='approved' if action=='approve' else 'rejected'; u.save(update_fields=['driver_status'])
        notify(u,'Role řidiče', 'Žádost o roli řidiče byla '+('schválena.' if action=='approve' else 'zamítnuta.'),P+'profile/')
    elif kind=='report' and action=='close':
        r=get_object_or_404(Report,pk=pk); r.status='closed'; r.save(update_fields=['status'])
    elif kind=='user' and action in ['disable','enable']:
        u=get_object_or_404(User,pk=pk)
        if u.pk==request.user.pk: raise Http404
        if action=='enable' and (not u.verified_at or not school_email(u.email) or not surname_matches(u.email,u.last_name)): raise Http404
        u.is_active=action=='enable'; u.save(update_fields=['is_active'])
    else: raise Http404
    return redirect(P+'admin/')

@require_school
@require_POST
def confirm_completion(request,pk):
    with transaction.atomic():
        b=get_object_or_404(Booking.objects.select_for_update(),pk=pk,passenger=request.user,status='confirmed',ride__status='completed')
        if not b.completed_at:
            b.completed_at=timezone.now(); b.save(update_fields=['completed_at','updated_at'])
            notify(b.ride.owner,'Účast potvrzena',request.user.get_full_name()+' potvrdil/a dokončenou jízdu.',P+'listing/'+str(b.ride_id)+'/')
    return redirect(P+'listing/'+str(b.ride_id)+'/')

@require_school
@require_POST
def complete_ride(request,pk):
    ride=get_object_or_404(Listing,pk=pk,kind='ride',owner=request.user,status='open',departure__lt=timezone.now())
    ride.status='completed'; ride.save(update_fields=['status','updated_at'])
    for b in ride.bookings.filter(status='confirmed'): notify(b.passenger,'Potvrď uskutečněnou jízdu','Řidič označil jízdu jako uskutečněnou. Potvrď svoji účast.',P+'listing/'+str(pk)+'/')
    return redirect(P+'listing/'+str(pk)+'/')

def public_coord(value): return round(value,2) if value is not None else None
@require_school
def map_tile(request,z,x,y):
    if not settings.GEOAPIFY_SERVER_KEY:
        return HttpResponse(status=503)
    if z > 19 or x >= 2**z or y >= 2**z:
        raise Http404
    tile_key=f'openride-tile:{z}:{x}:{y}'
    content=cache.get(tile_key)
    if content is None:
        try:
            response=requests.get(
                f'https://maps.geoapify.com/v1/tile/osm-bright/{z}/{x}/{y}.png',
                params={'apiKey':settings.GEOAPIFY_SERVER_KEY},timeout=8)
            response.raise_for_status()
            if not response.headers.get('content-type','').startswith('image/png') or len(response.content)>1024*1024:
                return HttpResponse(status=503)
            content=response.content
            cache.set(tile_key,content,86400)
        except requests.RequestException:
            return HttpResponse(status=503)
    result=HttpResponse(content,content_type='image/png')
    result['Cache-Control']='private, max-age=86400'
    return result

@require_school
def map_data(request,pk):
    obj=get_object_or_404(Listing,pk=pk)
    exact=obj.visible_to(request.user)
    coords=[]
    for lat,lon in [(obj.origin_lat,obj.origin_lon),(obj.destination_lat,obj.destination_lon)]:
        coords.append([lat if exact else public_coord(lat),lon if exact else public_coord(lon)] if lat is not None and lon is not None else None)
    stops=obj.stops if exact else [{'label':s.get('area','Zastávka'),'lat':public_coord(s.get('lat')),'lon':public_coord(s.get('lon'))} for s in obj.stops if isinstance(s,dict)]
    return JsonResponse({'kind':obj.kind,'origin':coords[0],'destination':coords[1],'stops':stops,'pickup':obj.pickup_private if exact else None,'destination_private':obj.destination_private if exact else None,'route':obj.route_geometry if exact and obj.kind=='ride' else None,'distance_m':obj.route_distance_m if obj.kind=='ride' else None,'duration_s':obj.route_duration_s if obj.kind=='ride' else None,'confirmed':obj.kind=='ride' and exact})

@require_school
def place_search(request):
    q=(request.GET.get('q') or '').strip()[:100]
    if not settings.GEOAPIFY_SERVER_KEY or len(q)<3: return JsonResponse({'results':[],'error':'Vyhledávání míst není nakonfigurované.' if not settings.GEOAPIFY_SERVER_KEY else ''})
    try:
        r=requests.get('https://api.geoapify.com/v1/geocode/autocomplete',params={'text':q,'filter':'countrycode:cz','limit':5,'apiKey':settings.GEOAPIFY_SERVER_KEY},timeout=5); r.raise_for_status()
        return JsonResponse({'results':[{'label':x['properties'].get('formatted',''),'lat':x['properties']['lat'],'lon':x['properties']['lon']} for x in r.json().get('features',[])]})
    except Exception: return JsonResponse({'results':[],'error':'Vyhledávání míst je dočasně nedostupné.'},status=503)

@require_school
def route_data(request,pk):
    obj=get_object_or_404(Listing,pk=pk)
    if obj.route_geometry and obj.visible_to(request.user) and obj.kind=='ride':
        return JsonResponse({'geometry':obj.route_geometry,'distance_m':obj.route_distance_m,'duration_s':obj.route_duration_s,'approximate':False})
    if not settings.GEOAPIFY_SERVER_KEY: return JsonResponse({'error':'Výpočet trasy není nakonfigurovaný.'},status=503)
    exact=obj.visible_to(request.user)
    if None in (obj.origin_lat,obj.origin_lon,obj.destination_lat,obj.destination_lon): return JsonResponse({'error':'Souřadnice cesty nejsou zadané.'},status=400)
    waypoints=[]
    points=[(obj.origin_lat,obj.origin_lon)]+[(s['lat'],s['lon']) for s in obj.stops if isinstance(s,dict) and s.get('lat') is not None and s.get('lon') is not None]+[(obj.destination_lat,obj.destination_lon)] if obj.kind=='ride' else [(obj.origin_lat,obj.origin_lon),(obj.destination_lat,obj.destination_lon)]
    for lat,lon in points:
        waypoints.append(f'{lat if exact else round(lat,2)},{lon if exact else round(lon,2)}')
    try:
        r=requests.get('https://api.geoapify.com/v1/routing',params={'waypoints':'|'.join(waypoints),'mode':'drive','apiKey':settings.GEOAPIFY_SERVER_KEY},timeout=8); r.raise_for_status()
        feature=r.json()['features'][0]
        prop=feature['properties']; geom=feature['geometry']
        if exact and obj.kind=='ride' and obj.owner_id==request.user.pk:
            Listing.objects.filter(pk=obj.pk).update(route_geometry=geom,route_distance_m=round(prop['distance']),route_duration_s=round(prop['time']))
        return JsonResponse({'geometry':geom,'distance_m':round(prop['distance']),'duration_s':round(prop['time']),'approximate':not exact or obj.kind=='demand'})
    except Exception: return JsonResponse({'error':'Výpočet trasy je dočasně nedostupný.'},status=503)


def resolve_stops(text):
    result=[]
    for name in [x.strip() for x in (text or '').splitlines() if x.strip()][:5]:
        stop={'area':name}
        if settings.GEOAPIFY_SERVER_KEY:
            try:
                r=requests.get('https://api.geoapify.com/v1/geocode/search',params={'text':name,'filter':'countrycode:cz','limit':1,'apiKey':settings.GEOAPIFY_SERVER_KEY},timeout=5);r.raise_for_status()
                prop=r.json()['features'][0]['properties'];stop.update(lat=prop['lat'],lon=prop['lon'])
            except Exception: pass
        result.append(stop)
    return result
