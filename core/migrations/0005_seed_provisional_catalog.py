from django.db import migrations


CATALOG_ROWS = (
    ('openai', 'GPT-5.6 Luna', 'gpt-5.6-luna', 'value', 1, 2),
    ('openai', 'GPT-5.6 Terra', 'gpt-5.6-terra', 'standard', 3, 6),
    ('openai', 'GPT-5.6 Sol', 'gpt-5.6-sol', 'premium', 9, 18),
    ('anthropic', 'Claude Haiku 4.5', 'claude-haiku-4.5', 'value', 1, 2),
    ('anthropic', 'Claude Sonnet 5.5', 'claude-sonnet-5.5', 'standard', 3, 6),
    ('anthropic', 'Claude Opus 5.5', 'claude-opus-5.5', 'premium', 9, 18),
    ('google', 'Gemini 3.1 Flash-Lite', 'gemini-3.1-flash-lite', 'value', 1, 2),
    ('google', 'Gemini 3.8 Flash', 'gemini-3.8-flash', 'standard', 3, 6),
    ('google', 'Gemini 3.1 Pro', 'gemini-3.1-pro', 'premium', 9, 18),
)


def seed_catalog(apps, schema_editor):
    catalog_model = apps.get_model('core', 'CatalogModel')
    manager = catalog_model.objects.using(schema_editor.connection.alias)

    for provider, display_name, model_id, tier, input_price, output_price in CATALOG_ROWS:
        manager.update_or_create(
            provider=provider,
            model_id=model_id,
            defaults={
                'display_name': display_name,
                'tier': tier,
                'input_credits_per_1k_tokens': input_price,
                'output_credits_per_1k_tokens': output_price,
                'is_active': True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0004_catalogmodel'),
    ]

    operations = [
        migrations.RunPython(seed_catalog, migrations.RunPython.noop),
    ]
