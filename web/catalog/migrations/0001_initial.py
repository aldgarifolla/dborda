from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='UserRole', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('role', models.CharField(choices=[('viewer','Viewer'),('manager','Manager')], default='viewer', max_length=16)),
            ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='demo_role', to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name='UnitGrant', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('root_code', models.CharField(max_length=128)),
            ('is_active', models.BooleanField(default=True)),
            ('granted_at', models.DateTimeField(auto_now_add=True)),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='unit_grants', to=settings.AUTH_USER_MODEL)),
        ], options={'constraints':[models.UniqueConstraint(fields=['user','root_code'], name='unique_demo_scope_grant')]})
    ]
