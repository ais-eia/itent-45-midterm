from django import forms

from .models import CatalogModel


class CatalogModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, model):
        return (
            f'{model.get_provider_display()} / {model.display_name} '
            f'({model.get_tier_display()}; input '
            f'{model.input_credits_per_1k_tokens}, output '
            f'{model.output_credits_per_1k_tokens} credits per 1k)'
        )


class TopUpForm(forms.Form):
    amount = forms.IntegerField(min_value=1, label='Credits to add')


class ChatForm(forms.Form):
    model = CatalogModelChoiceField(
        queryset=CatalogModel.objects.none(),
        label='Active model',
    )
    prompt = forms.CharField(
        strip=True,
        widget=forms.Textarea(attrs={'rows': 4}),
        label='Message',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['model'].queryset = CatalogModel.objects.filter(is_active=True)


class ConversationTitleForm(forms.Form):
    title = forms.CharField(max_length=80, strip=True, label='Conversation title')


class ConversationTitleForm(forms.Form):
    title = forms.CharField(max_length=80, strip=True, label='Conversation title')
