from django import template
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse

register = template.Library()


@register.simple_tag
def admin_users_changelist_url():
    user_model = get_user_model()
    app_label = user_model._meta.app_label
    model_name = user_model._meta.model_name
    try:
        return reverse(f"admin:{app_label}_{model_name}_changelist")
    except NoReverseMatch:
        return ""


@register.simple_tag
def recent_admin_users(limit=6):
    user_model = get_user_model()
    try:
        return user_model.objects.order_by("-date_joined")[:limit]
    except Exception:
        return []
