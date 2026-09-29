from django import forms


class TopUpForm(forms.Form):
    amount = forms.IntegerField(min_value=1, label='Credits to add')
