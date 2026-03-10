from django.contrib import admin
from .models import Clinic, DoctorInvitation, Membership, StripeWebhookEvent


@admin.register(Clinic)
class ClinicAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'owner',
        'subscription_plan',
        'account_status',
        'seat_limit',
        'scheduled_seat_limit',
        'updated_at',
    )
    search_fields = ('name', 'owner__email', 'stripe_customer_id', 'stripe_subscription_id')
    list_filter = ('subscription_plan', 'account_status')


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('account', 'user', 'role', 'updated_at')
    search_fields = ('account__name', 'user__email')
    list_filter = ('role',)


@admin.register(DoctorInvitation)
class DoctorInvitationAdmin(admin.ModelAdmin):
    list_display = ('clinic', 'email', 'status', 'created_at', 'expires_at')
    search_fields = ('clinic__name', 'email')
    list_filter = ('status',)


@admin.register(StripeWebhookEvent)
class StripeWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('event_id', 'event_type', 'livemode', 'processed_at')
    search_fields = ('event_id', 'event_type')
    list_filter = ('event_type', 'livemode')
