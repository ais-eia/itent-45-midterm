from django import forms

from .models import CatalogModel, WalletTransaction


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


class UsageHistoryFilterForm(forms.Form):
    model = forms.ModelChoiceField(
        queryset=CatalogModel.objects.none(),
        required=False,
        empty_label='All models',
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='From date',
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Through date',
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        model_ids = WalletTransaction.objects.filter(
            wallet=user.wallet,
            transaction_type=WalletTransaction.Type.USAGE,
            exchange__user=user,
            exchange__conversation__user=user,
        ).order_by().values('exchange__model_id')
        self.fields['model'].queryset = CatalogModel.objects.filter(
            pk__in=model_ids,
        ).order_by('provider', 'tier', 'display_name')

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', 'Through date must be on or after the from date.')
        return cleaned_data
