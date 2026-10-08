from django.urls import path
from . import views as v
from django.contrib.auth import views as auth_views
urlpatterns=[
 path('reset/<uidb64>/<token>/',auth_views.PasswordResetConfirmView.as_view(template_name='reset_confirm.html',success_url='/openride/login/')),path('health/',v.health),path('',v.marketplace),path('register/',v.register),path('verify/<str:token>/',v.verify),path('login/',v.signin),path('logout/',v.signout),path('resend/',v.resend),path('reset/',v.reset_password),
 path('listing/new/<str:kind>/',v.listing_new),path('listing/<int:pk>/',v.listing_detail),path('listing/<int:pk>/edit/',v.listing_edit),path('listing/<int:pk>/cancel/',v.listing_cancel),path('listing/<int:pk>/request/',v.request_seat),path('listing/<int:pk>/propose/',v.propose),path('listing/<int:pk>/report/',v.report),path('listing/<int:pk>/complete/',v.complete_ride),
 path('booking/<int:pk>/completed/',v.confirm_completion),path('booking/<int:pk>/<str:action>/',v.booking_action),path('mine/',v.mine),path('profile/',v.profile),path('profile/email/',v.change_email),path('profile/password/',v.change_password),path('profile/driver/',v.driver_apply),path('notices/',v.notices),path('notice/<int:pk>/read/',v.notice_read),path('admin/',v.admin_panel),path('admin/<str:kind>/<int:pk>/<str:action>/',v.admin_action),path('map/<int:pk>/',v.map_data),path('route/<int:pk>/',v.route_data),path('places/',v.place_search),path('tiles/<int:z>/<int:x>/<int:y>.png',v.map_tile),
]
