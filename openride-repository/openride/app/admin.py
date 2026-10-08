from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User,Listing,Booking,Report,Notice,EmailToken
@admin.register(User)
class SchoolUserAdmin(UserAdmin):
    list_display=('email','first_name','last_name','verified_at','driver_status','is_active','is_staff')
    search_fields=('email','first_name','last_name')
    readonly_fields=('email','verified_at','pending_email')
    def has_add_permission(self,request): return False
    fieldsets=UserAdmin.fieldsets+(("OpenRide",{'fields':('verified_at','driver_status','birth_date','parental_consent_recorded','parental_consent_note','pending_email')}),)
@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display=('id','kind','owner','origin_area','destination_area','departure','status')
    list_filter=('kind','status','direction')
@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display=('id','ride','passenger','status','completed_at')
    list_filter=('status',)
@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display=('id','reporter','listing','status','created_at')
    list_filter=('status',)
admin.site.register(Notice)
admin.site.register(EmailToken)
