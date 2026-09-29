from django.conf import settings
from django.db import migrations


def seed_initial_wallets(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    user_model = apps.get_model(app_label, model_name)
    wallet_model = apps.get_model('core', 'Wallet')
    transaction_model = apps.get_model('core', 'WalletTransaction')
    database = schema_editor.connection.alias

    for user_id in user_model.objects.using(database).values_list('pk', flat=True).iterator():
        wallet, created = wallet_model.objects.using(database).get_or_create(
            user_id=user_id,
            defaults={'balance': 100},
        )
        if created:
            transaction_model.objects.using(database).create(
                wallet_id=wallet.pk,
                amount=100,
                transaction_type='signup_bonus',
            )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(seed_initial_wallets, migrations.RunPython.noop),
    ]
