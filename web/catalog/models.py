from django.conf import settings
from django.db import models


class UserRole(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='demo_role')
    role = models.CharField(max_length=16, choices=[('viewer', 'Viewer'), ('manager', 'Manager')], default='viewer')


class UnitGrant(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='unit_grants')
    root_code = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'root_code'], name='unique_demo_scope_grant')]


class GrantAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='performed_grant_actions')
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='received_grant_actions')
    root_code = models.CharField(max_length=128)
    action = models.CharField(max_length=12, choices=[('grant', 'Выдача'), ('revoke', 'Отзыв')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
