from datetime import date,timedelta
from unittest.mock import patch,Mock
from django.test import TestCase,TransactionTestCase,Client,override_settings
from django.db import close_old_connections,connections
from django.utils import timezone
from django.urls import reverse
from .models import User,Listing,Booking,EmailToken,surname_matches,school_email
from .forms import ListingForm
from .school import SCHOOL_ADDRESS,SCHOOL_LAT,SCHOOL_LON
from .services import send_token

P='/openride/'
def user(email,first='Test',last='Novák',driver=False,staff=False,active=True):
    u=User.objects.create_user(username=email,email=email,password='StrongPassword123!',first_name=first,last_name=last,is_active=active,is_staff=staff,verified_at=timezone.now() if active else None,birth_date=date(1990,1,1),driver_status='approved' if driver else 'none')
    return u
def listing(owner,kind='ride',capacity=2):
    return Listing.objects.create(owner=owner,kind=kind,direction='to',origin_area='Praha',destination_area='Babice',pickup_private='Soukromá 12',destination_private='Brána školy',origin_lat=50.1,origin_lon=14.4,destination_lat=49.95,destination_lon=14.6,departure=timezone.now()+timedelta(days=2),capacity=capacity)
class SchoolPrefillTests(TestCase):
    def test_new_ride_and_demand_prefill_school_destination(self):
        for kind in ('ride','demand'):
            with self.subTest(kind=kind):
                form=ListingForm(kind=kind)
                self.assertEqual(form.initial['direction'],'to')
                self.assertEqual(form.initial['destination_area'],SCHOOL_ADDRESS)
                self.assertEqual(form.initial['destination_lat'],SCHOOL_LAT)
                self.assertEqual(form.initial['destination_lon'],SCHOOL_LON)
                self.assertNotIn('origin_area',form.initial)
                if kind=='ride': self.assertEqual(form.initial['destination_private'],SCHOOL_ADDRESS)
        driver=user('novak@opengate.cz',driver=True)
        self.client.force_login(driver)
        for kind in ('ride','demand'):
            with self.subTest(page=kind):
                response=self.client.get(P+'listing/new/'+kind+'/')
                self.assertEqual(response.status_code,200)
                self.assertContains(response,SCHOOL_ADDRESS)

    def test_edit_keeps_saved_route(self):
        driver=user('novak@opengate.cz',driver=True)
        ride=listing(driver)
        form=ListingForm(instance=ride,kind='ride')
        self.assertEqual(form['destination_area'].value(),'Babice')
        self.assertEqual(form['destination_lat'].value(),49.95)
        self.assertEqual(form['destination_private'].value(),'Brána školy')

class IdentityTests(TestCase):
    def test_examples_and_boundaries(self):
        yes=[('20bouska@opengate.cz','Bouška'),('20bouska@opengate.cz','BOUSKA'),('21novak@opengate.cz','Novák'),('24bolcek@opengate.cz','Bolcek'),('24dbolcek@opengate.cz','Bolcek'),('24debolcek@opengate.cz','Bolcek'),('24debolcek@opengate.cz','Bolček')]
        no=[('24dbolcek@opengate.cz','Novák'),('24bolcekova@opengate.cz','Bolcek'),('20bouska@opengate.cz','Bouš'),('20bouska@gmail.com','Bouška'),('24abcbolcek@opengate.cz','Bolcek'),('24bolcekx@opengate.cz','Bolcek'),('123@opengate.cz','Novák'),('novak@opengate.cz',''),('novak@opengate.cz.example.com','Novák')]
        for email,name in yes:
            with self.subTest(email=email,name=name): self.assertTrue(surname_matches(email,name))
        for email,name in no:
            with self.subTest(email=email,name=name): self.assertFalse(surname_matches(email,name))
        self.assertTrue(school_email('NOVAK@OPENGATE.CZ'))
    def test_registration_stays_inactive_without_mail(self):
        with override_settings(BREVO_API_KEY='',BREVO_FROM_EMAIL=''):
            r=self.client.post(P+'register/',{'first_name':'Jan','last_name':'Novák','email':'21novak@opengate.cz','password1':'StrongPassword123!','password2':'StrongPassword123!'})
        self.assertEqual(r.status_code,302)
        u=User.objects.get(email='21novak@opengate.cz')
        self.assertFalse(u.is_active)
        self.assertIsNone(u.verified_at)
        self.assertEqual(self.client.post(P+'login/',{'username':u.email,'password':'StrongPassword123!'}).status_code,200)
    def test_direct_identity_bypass_denied(self):
        u=user('novak@opengate.cz',active=True)
        User.objects.filter(pk=u.pk).update(email='novak@opengate.cz.example.com',username='novak@opengate.cz.example.com')
        self.assertFalse(self.client.login(username='novak@opengate.cz.example.com',password='StrongPassword123!'))
        User.objects.filter(pk=u.pk).update(email='novak@opengate.cz',username='novak@opengate.cz',last_name='Špatně')
        self.assertFalse(self.client.login(username='novak@opengate.cz',password='StrongPassword123!'))
    def test_email_change_revalidates(self):
        u=user('novak@opengate.cz')
        self.client.force_login(u)
        r=self.client.post(P+'profile/email/',{'email':'novak@gmail.com'})
        u.refresh_from_db(); self.assertEqual(u.pending_email,'')
        r=self.client.post(P+'profile/',{'first_name':'Test','last_name':'Špatně','birth_date':'1990-01-01'})
        u.refresh_from_db(); self.assertEqual(u.last_name,'Novák')

class BookingTests(TestCase):
    def setUp(self):
        self.driver=user('novak@opengate.cz',driver=True)
        self.p1=user('bouska@opengate.cz',last='Bouška')
        self.p2=user('bolcek@opengate.cz',last='Bolček')
        self.ride=listing(self.driver,capacity=1)
    def test_passenger_flow_and_idempotent_cancel(self):
        self.client.force_login(self.p1)
        self.client.post(P+f'listing/{self.ride.pk}/request/')
        self.client.post(P+f'listing/{self.ride.pk}/request/')
        self.assertEqual(Booking.objects.count(),1)
        b=Booking.objects.get()
        self.client.force_login(self.driver)
        self.client.post(P+f'booking/{b.pk}/accept/')
        self.client.post(P+f'booking/{b.pk}/accept/')
        self.ride.refresh_from_db();self.assertEqual(self.ride.available,0)
        self.client.force_login(self.p1)
        self.client.post(P+f'booking/{b.pk}/cancel/')
        self.client.post(P+f'booking/{b.pk}/cancel/')
        self.assertEqual(self.ride.available,1)
    def test_driver_proposal_closes_others(self):
        demand=listing(self.p1,'demand')
        d2=user('hruska@opengate.cz',last='Hruška',driver=True)
        r2=listing(d2)
        self.client.force_login(self.driver);self.client.post(P+f'listing/{demand.pk}/propose/',{'ride':self.ride.pk})
        self.client.force_login(d2);self.client.post(P+f'listing/{demand.pk}/propose/',{'ride':r2.pk})
        self.assertEqual(Booking.objects.filter(status='pending').count(),2)
        b=Booking.objects.get(ride=self.ride)
        self.client.force_login(self.p1);self.client.post(P+f'booking/{b.pk}/accept/')
        demand.refresh_from_db();self.assertEqual(demand.status,'resolved')
        self.assertEqual(Booking.objects.get(ride=r2).status,'closed')
        self.assertEqual(self.ride.available,0)
        self.client.post(P+f'booking/{b.pk}/cancel/')
        demand.refresh_from_db();self.assertEqual(demand.status,'open')
    def test_role_and_private_map(self):
        self.client.force_login(self.p1)
        self.assertEqual(self.client.post(P+'listing/new/ride/',{}).status_code,302)
        data=self.client.get(P+f'map/{self.ride.pk}/').json()
        self.assertIsNone(data['pickup']);self.assertEqual(data['origin'],[50.1,14.4])
        self.assertNotContains(self.client.get(P+f'listing/{self.ride.pk}/'),'Soukromá 12')
        self.client.post(P+f'listing/{self.ride.pk}/request/')
        b=Booking.objects.get();self.client.force_login(self.driver);self.client.post(P+f'booking/{b.pk}/accept/')
        self.client.force_login(self.p1)
        data=self.client.get(P+f'map/{self.ride.pk}/').json();self.assertEqual(data['pickup'],'Soukromá 12')
    def test_changed_ride_needs_reconfirmation(self):
        b=Booking.objects.create(ride=self.ride,passenger=self.p1,initiated_by='passenger',status='confirmed')
        self.client.force_login(self.driver)
        d={'direction':'to','origin_area':'Praha 4','destination_area':'Babice','pickup_private':'Soukromá 12','destination_private':'Brána školy','origin_lat':'50.1','origin_lon':'14.4','destination_lat':'49.95','destination_lon':'14.6','departure_0':(timezone.localdate()+timedelta(days=3)).isoformat(),'departure_1':'10:00','capacity':'1','note':'','conditions':''}
        self.client.post(P+f'listing/{self.ride.pk}/edit/',d)
        b.refresh_from_db();self.assertEqual(b.status,'needs_reconfirm')
        self.assertEqual(self.ride.available,0)
        self.client.force_login(self.p1);self.client.post(P+f'booking/{b.pk}/reconfirm/')
        b.refresh_from_db();self.assertEqual(b.status,'confirmed')
    @override_settings(GEOAPIFY_SERVER_KEY='test')
    @patch('app.views.requests.get')
    def test_map_provider_outage(self,get):
        get.side_effect=TimeoutError('offline')
        self.client.force_login(self.p1)
        self.assertEqual(self.client.get(P+f'route/{self.ride.pk}/').status_code,503)
        self.assertEqual(self.client.get(P+'places/?q=Praha').status_code,503)

class ConcurrentBookingTests(TransactionTestCase):
    reset_sequences=True
    def test_last_seat(self):
        import threading
        driver=user('novak@opengate.cz',driver=True)
        p1=user('bouska@opengate.cz',last='Bouška')
        p2=user('bolcek@opengate.cz',last='Bolček')
        ride=listing(driver,capacity=1)
        b1=Booking.objects.create(ride=ride,passenger=p1,initiated_by='passenger')
        b2=Booking.objects.create(ride=ride,passenger=p2,initiated_by='passenger')
        out=[]
        def accept(bid):
            close_old_connections();c=Client();c.force_login(driver)
            out.append(c.post(P+f'booking/{bid}/accept/').status_code)
            connections.close_all()
        t1=threading.Thread(target=accept,args=(b1.pk,));t2=threading.Thread(target=accept,args=(b2.pk,));t1.start();t2.start();t1.join();t2.join()
        self.assertEqual(Booking.objects.filter(status='confirmed').count(),1)
        self.assertEqual(ride.available,0)

class VerificationTests(TestCase):
    @override_settings(BREVO_API_KEY='fake',BREVO_FROM_EMAIL='noreply@example.com')
    @patch('app.services.send_mail')
    def test_activation_requires_link_and_change_requires_reverification(self,send):
        import re
        r=self.client.post(P+'register/',{'first_name':'Jan','last_name':'Novák','email':'novak@opengate.cz','password1':'StrongPassword123!','password2':'StrongPassword123!'})
        u=User.objects.get(email='novak@opengate.cz')
        self.assertFalse(u.is_active)
        self.assertFalse(self.client.login(username=u.email,password='StrongPassword123!'))
        link=re.search(r'/openride/verify/[^/]+/',send.call_args.args[1]).group(0)
        self.client.get(link)
        u.refresh_from_db();self.assertTrue(u.is_active);self.assertIsNotNone(u.verified_at)
        self.assertTrue(self.client.login(username='NOVAK@OPENGATE.CZ',password='StrongPassword123!'))
        with patch('app.views.send_token') as token:
            token.return_value=True
            self.client.post(P+'profile/email/',{'email':'21novak@opengate.cz'})
        u.refresh_from_db();self.assertEqual(u.email,'novak@opengate.cz');self.assertEqual(u.pending_email,'21novak@opengate.cz')
        self.client.post(P+'profile/email/',{'email':'novak@gmail.com'})
        u.refresh_from_db();self.assertEqual(u.pending_email,'21novak@opengate.cz')
    def test_admin_cannot_approve_unverified_driver(self):
        admin=user('novak@opengate.cz',driver=True,staff=True)
        candidate=user('bouska@opengate.cz',last='Bouška',active=False)
        candidate.driver_status='pending';candidate.save()
        self.client.force_login(admin)
        self.assertEqual(self.client.post(P+f'admin/driver/{candidate.pk}/approve/').status_code,404)
        candidate.refresh_from_db();self.assertEqual(candidate.driver_status,'pending')
    def test_direct_api_cannot_impersonate_driver(self):
        driver=user('novak@opengate.cz',driver=True)
        passenger=user('bouska@opengate.cz',last='Bouška')
        ride=listing(driver);demand=listing(passenger,'demand')
        self.client.force_login(passenger)
        self.client.post(P+f'listing/{demand.pk}/propose/',{'ride':ride.pk})
        self.assertEqual(Booking.objects.count(),0)
        Booking.objects.create(ride=ride,passenger=passenger,initiated_by='passenger')
        self.assertEqual(self.client.post(P+'booking/1/accept/').status_code,404)

class RouteAndStatsTests(TestCase):
    def setUp(self):
        self.driver=user('novak@opengate.cz',driver=True,staff=True)
        self.passenger=user('bouska@opengate.cz',last='Bouška')
        self.ride=listing(self.driver)
    @override_settings(GEOAPIFY_SERVER_KEY='fake')
    @patch('app.views.requests.get')
    def test_route_result_and_private_coordinate_rounding(self,get):
        self.ride.origin_lat=50.123456;self.ride.origin_lon=14.456789;self.ride.save()
        response=Mock();response.json.return_value={'features':[{'properties':{'distance':12340,'time':1240},'geometry':{'type':'MultiLineString','coordinates':[[[14.46,50.12],[14.6,49.95]]]}}]};response.raise_for_status.return_value=None;get.return_value=response
        self.client.force_login(self.passenger)
        public=self.client.get(P+f'map/{self.ride.pk}/').json()
        self.assertEqual(public['origin'],[50.12,14.46]);self.assertIsNone(public['pickup'])
        route=self.client.get(P+f'route/{self.ride.pk}/').json()
        self.assertTrue(route['approximate'])
        self.assertIn('50.12,14.46',get.call_args.kwargs['params']['waypoints'])
        self.client.force_login(self.driver)
        route=self.client.get(P+f'route/{self.ride.pk}/').json()
        self.assertFalse(route['approximate'])
        self.assertIn('50.123456,14.456789',get.call_args.kwargs['params']['waypoints'])
        self.ride.refresh_from_db();self.assertEqual(self.ride.route_distance_m,12340)
    def test_completed_stats_need_passenger_confirmation(self):
        b=Booking.objects.create(ride=self.ride,passenger=self.passenger,initiated_by='passenger',status='confirmed')
        self.ride.departure=timezone.now()-timedelta(hours=1);self.ride.save()
        self.client.force_login(self.driver);self.client.post(P+f'listing/{self.ride.pk}/complete/')
        r=self.client.get(P+'admin/');self.assertEqual(r.context['stats']['completed'],0)
        self.client.force_login(self.passenger);self.client.post(P+f'booking/{b.pk}/completed/')
        self.client.force_login(self.driver);r=self.client.get(P+'admin/')
        self.assertEqual(r.context['stats']['completed'],1)

class TileProxyTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.account=user('novak@opengate.cz')

    @override_settings(GEOAPIFY_SERVER_KEY='private-test-key')
    @patch('app.views.requests.get')
    def test_tiles_require_school_login_and_hide_key(self,get):
        url=P+'tiles/10/552/346.png'
        self.assertEqual(self.client.get(url).status_code,302)
        get.assert_not_called()
        self.client.force_login(self.account)
        upstream=Mock(content=b'\x89PNGtest',headers={'content-type':'image/png'})
        upstream.raise_for_status.return_value=None
        get.return_value=upstream
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,b'\x89PNGtest')
        self.assertEqual(get.call_args.kwargs['params']['apiKey'],'private-test-key')
        self.client.get(url)
        self.assertEqual(get.call_count,1)
        page=self.client.get(P+'listing/new/demand/')
        self.assertNotIn(b'private-test-key',page.content)

    @override_settings(GEOAPIFY_SERVER_KEY='private-test-key')
    @patch('app.views.requests.get')
    def test_tile_outage_and_invalid_coordinates(self,get):
        import requests
        self.client.force_login(self.account)
        get.side_effect=requests.Timeout()
        self.assertEqual(self.client.get(P+'tiles/10/552/346.png').status_code,503)
        self.assertEqual(self.client.get(P+'tiles/10/1024/346.png').status_code,404)

class IdentityChangeTests(TestCase):
    def test_direct_model_email_change_deactivates(self):
        u=user('novak@opengate.cz')
        u.email='21novak@opengate.cz';u.save()
        u.refresh_from_db()
        self.assertFalse(u.is_active)
        self.assertIsNone(u.verified_at)
    @override_settings(BREVO_API_KEY='fake',BREVO_FROM_EMAIL='noreply@example.com')
    @patch('app.services.send_mail')
    def test_email_change_finishes_only_after_link(self,send):
        import re
        u=user('novak@opengate.cz');self.client.force_login(u)
        self.client.post(P+'profile/email/',{'email':'21novak@opengate.cz'})
        u.refresh_from_db();self.assertEqual(u.email,'novak@opengate.cz')
        link=re.search(r'/openride/verify/[^/]+/',send.call_args.args[1]).group(0)
        self.client.get(link)
        u.refresh_from_db();self.assertEqual(u.email,'21novak@opengate.cz')
        self.assertTrue(u.is_active)
        self.assertIsNotNone(u.verified_at)
        self.assertFalse(self.client.login(username='novak@opengate.cz',password='StrongPassword123!'))
        self.assertTrue(self.client.login(username='21novak@opengate.cz',password='StrongPassword123!'))

class WebSecurityTests(TestCase):
    def test_csrf_blocks_direct_post(self):
        u=user('novak@opengate.cz')
        client=Client(enforce_csrf_checks=True);client.force_login(u)
        self.assertEqual(client.post(P+'listing/new/demand/',{'origin_area':'Praha'}).status_code,403)
    def test_untrusted_note_is_escaped(self):
        driver=user('novak@opengate.cz',driver=True)
        passenger=user('bouska@opengate.cz',last='Bouška')
        ride=listing(driver);ride.note='<script>alert(1)</script>';ride.save()
        self.client.force_login(passenger)
        response=self.client.get(P+f'listing/{ride.pk}/')
        self.assertContains(response,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')
    def test_login_attempt_limit(self):
        u=user('novak@opengate.cz')
        for _ in range(5): self.client.post(P+'login/',{'username':u.email,'password':'bad'})
        response=self.client.post(P+'login/',{'username':u.email,'password':'StrongPassword123!'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Příliš mnoho pokusů')

class CancellationTests(TestCase):
    def test_whole_ride_cancellation_reopens_demand_once(self):
        driver=user('novak@opengate.cz',driver=True)
        passenger=user('bouska@opengate.cz',last='Bouška')
        ride=listing(driver,capacity=1)
        demand=listing(passenger,'demand');demand.status='resolved';demand.save()
        b=Booking.objects.create(ride=ride,passenger=passenger,demand=demand,initiated_by='driver',status='confirmed')
        self.client.force_login(driver)
        self.client.post(P+f'listing/{ride.pk}/cancel/')
        self.client.post(P+f'listing/{ride.pk}/cancel/')
        ride.refresh_from_db();demand.refresh_from_db();b.refresh_from_db()
        self.assertEqual(ride.status,'cancelled')
        self.assertEqual(demand.status,'open')
        self.assertEqual(b.status,'cancelled')
        self.assertEqual(ride.available,1)
        self.assertEqual(passenger.notices.filter(title='Jízda byla zrušena').count(),1)

class AdminBootstrapTests(TestCase):
    def test_only_verified_school_account_can_be_admin(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        import io
        pending=user('bouska@opengate.cz',last='Bouška',active=False)
        with self.assertRaises(CommandError): call_command('promote_admin',pending.email,stdout=io.StringIO())
        valid=user('novak@opengate.cz')
        call_command('promote_admin',valid.email,stdout=io.StringIO())
        valid.refresh_from_db();self.assertTrue(valid.is_staff);self.assertTrue(valid.is_superuser)

class BrevoEmailTests(TestCase):
    @override_settings(BREVO_API_KEY='test-key', BREVO_FROM_EMAIL='overena@example.com', EMAIL_BACKEND='app.email_backend.BrevoBackend')
    @patch('app.email_backend.requests.post')
    def test_brevo_payload_and_header(self, post):
        from django.core.mail import send_mail
        post.return_value.status_code = 201
        sent = send_mail('Ověření', 'Odkaz', 'OpenRide <overena@example.com>', ['novak@opengate.cz'])
        self.assertEqual(sent, 1)
        self.assertEqual(post.call_args.args[0], 'https://api.brevo.com/v3/smtp/email')
        self.assertEqual(post.call_args.kwargs['headers']['api-key'], 'test-key')
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['sender']['email'], 'overena@example.com')
        self.assertEqual(payload['to'], [{'email': 'novak@opengate.cz'}])
        self.assertEqual(payload['textContent'], 'Odkaz')
    @override_settings(BREVO_API_KEY='test-key', BREVO_FROM_EMAIL='overena@example.com', EMAIL_BACKEND='app.email_backend.BrevoBackend')
    @patch('app.email_backend.requests.post')
    def test_brevo_failure_does_not_activate_account(self, post):
        import requests
        post.side_effect = requests.Timeout()
        response = self.client.post(P+'register/', {'first_name':'Jan','last_name':'Novák','email':'novak@opengate.cz','password1':'StrongPassword123!','password2':'StrongPassword123!'})
        self.assertEqual(response.status_code, 302)
        account = User.objects.get(email='novak@opengate.cz')
        self.assertFalse(account.is_active)
        self.assertFalse(EmailToken.objects.filter(user=account).exists())
