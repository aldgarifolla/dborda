from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('catalog', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='GrantAudit',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('root_code', models.CharField(max_length=128)),
                ('action', models.CharField(choices=[('grant', 'Выдача'), ('revoke', 'Отзыв')], max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='performed_grant_actions', to=settings.AUTH_USER_MODEL)),
                ('target', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='received_grant_actions', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
