from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


def seed_demo_user(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    user_model = apps.get_model(app_label, model_name)
    user_model.objects.using(schema_editor.connection.alias).get_or_create(
        username='demo',
        defaults={'password': make_password('demo12345')},
    )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_demo_user, migrations.RunPython.noop),
    ]
