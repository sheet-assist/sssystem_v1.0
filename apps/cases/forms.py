from django import forms


class ConvertProspectForm(forms.Form):
    contract_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    contract_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows':4}))
    assigned_to = forms.IntegerField(required=False, widget=forms.HiddenInput())
