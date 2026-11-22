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


class AssistantAudit(models.Model):
    """Журнал помощника: кто спросил, какие инструменты вызваны, что отвечено."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='assistant_questions')
    question = models.CharField(max_length=500)
    mode = models.CharField(max_length=40)
    calls = models.JSONField(default=list)
    answer = models.TextField(blank=True)
    ok = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class AssistantChat(models.Model):
    """Чат с помощником: у каждого пользователя свои чаты, как в ИИ-чатах."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assistant_chats')
    title = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class AssistantMessage(models.Model):
    """Один обмен в чате: вопрос пользователя и ответ помощника с таблицами."""
    chat = models.ForeignKey(AssistantChat, on_delete=models.CASCADE, related_name='messages')
    question = models.CharField(max_length=500)
    text = models.TextField(blank=True)
    tables = models.JSONField(default=list)
    calls = models.JSONField(default=list)
    mode = models.CharField(max_length=40, blank=True)
    ok = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
