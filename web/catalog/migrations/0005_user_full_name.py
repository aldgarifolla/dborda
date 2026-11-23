from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('catalog', '0004_assistantchat')]
    operations = [
        migrations.AddField(model_name='userrole', name='full_name',
                            field=models.CharField(blank=True, max_length=150, verbose_name='ФИО полностью')),
        migrations.AlterField(model_name='userrole', name='role',
                              field=models.CharField(choices=[('viewer', 'Наблюдатель'), ('manager', 'Менеджер')],
                                                     default='viewer', max_length=16)),
        migrations.AlterField(model_name='grantaudit', name='action',
                              field=models.CharField(choices=[('grant', 'Выдача'), ('revoke', 'Отзыв'),
                                                              ('create', 'Создание пользователя'), ('disable', 'Отключение'),
                                                              ('enable', 'Включение')], max_length=12)),
    ]
