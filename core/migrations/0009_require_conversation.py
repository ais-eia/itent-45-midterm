import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0008_backfill_legacy_conversations'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chatexchange',
            name='conversation',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='exchanges',
                to='core.conversation',
            ),
        ),
    ]
