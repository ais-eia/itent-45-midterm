from django.db import migrations


TITLE_LIMIT = 80


def title_from_prompt(prompt):
    title = ' '.join((prompt or '').split())
    if not title:
        return 'Previous chat'
    if len(title) > TITLE_LIMIT:
        return title[:TITLE_LIMIT - 3].rstrip() + '...'
    return title


def backfill_conversations(apps, schema_editor):
    Conversation = apps.get_model('core', 'Conversation')
    ChatExchange = apps.get_model('core', 'ChatExchange')
    database = schema_editor.connection.alias

    for exchange in ChatExchange.objects.using(database).order_by('created_at', 'pk').iterator():
        conversation = Conversation.objects.using(database).create(
            user_id=exchange.user_id,
            title=title_from_prompt(exchange.prompt),
            created_at=exchange.created_at,
            last_activity_at=exchange.created_at,
        )
        ChatExchange.objects.using(database).filter(pk=exchange.pk).update(
            conversation_id=conversation.pk,
        )


def detach_conversations(apps, schema_editor):
    ChatExchange = apps.get_model('core', 'ChatExchange')
    database = schema_editor.connection.alias
    ChatExchange.objects.using(database).all().update(conversation_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0007_conversation_chatexchange_conversation_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_conversations, detach_conversations),
    ]
