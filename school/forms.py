from django.contrib.auth.forms import PasswordChangeForm


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        text_input_attrs = {
            'class': 'mt-2 block w-full rounded-3xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100',
            'autocomplete': 'off',
        }

        self.fields['old_password'].widget.attrs.update(text_input_attrs)
        self.fields['new_password1'].widget.attrs.update(text_input_attrs)
        self.fields['new_password2'].widget.attrs.update(text_input_attrs)
