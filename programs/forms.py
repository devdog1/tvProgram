import re
from django import forms
from .models import (
    Program,
    Category,
    Community,
    SourceCode,
    ShareOption,
    Series,
    CustomField,
    ProgramAttachment,
    EventHook,
    SMTPSettings,
)


class ProgramForm(forms.ModelForm):
    category = forms.ChoiceField(required=False, widget=forms.Select(attrs={"class": "form-select"}))
    source_code = forms.ChoiceField(required=False, widget=forms.Select(attrs={"class": "form-select"}))
    community = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": "6"}),
    )
    share = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": "4"}),
    )

    class Meta:
        model = Program
        fields = [
            "title",
            "owner_group",
            "date_recorded",
            "expiry_date",
            "producer",
            "length",
            "category",
            "source_code",
            "community",
            "share",
            "series",
            "season_number",
            "episode_number",
            "part_number",
            "filename",
            "comments",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "required": "required"}),
            "owner_group": forms.Select(attrs={"class": "form-select"}),
            "date_recorded": forms.DateInput(attrs={"class": "form-control", "placeholder": "YYYY-MM-DD", "required": "required"}),
            "expiry_date": forms.DateInput(attrs={"class": "form-control", "placeholder": "YYYY-MM-DD"}),
            "producer": forms.TextInput(attrs={"class": "form-control", "required": "required"}),
            "length": forms.TextInput(attrs={"class": "form-control", "placeholder": "HH:MM:SS", "required": "required"}),
            "series": forms.Select(attrs={"class": "form-select"}),
            "season_number": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "episode_number": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "part_number": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "filename": forms.TextInput(attrs={"class": "form-control", "required": "required"}),
            "comments": forms.TextInput(attrs={"class": "form-control", "maxlength": "255"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filter series selector to only show series visible to that user based on their permissions
        from django.contrib.auth.models import Group
        if user:
            can_view_all_s = user.is_superuser or user.has_perm("programs.view_all_series")
            if can_view_all_s:
                self.fields["series"].queryset = Series.objects.all()
            else:
                user_groups = user.groups.all()
                self.fields["series"].queryset = Series.objects.filter(owner_group__in=user_groups)

            # Limit owner_group choices: if superuser or has view_all_programs, can choose any group;
            # otherwise, only groups the user belongs to.
            can_view_all_p = user.is_superuser or user.has_perm("programs.view_all_programs")
            if can_view_all_p:
                self.fields["owner_group"].queryset = Group.objects.all()
            else:
                self.fields["owner_group"].queryset = user.groups.all()
                if not self.instance.pk and user.groups.exists():
                    self.initial["owner_group"] = user.groups.first()

        # Populate Category dropdown
        cat_choices = [("", "-")] + [
            (c.name, c.display_name or c.name) for c in Category.objects.filter(is_enabled=True)
        ]
        if self.instance and self.instance.pk and self.instance.category:
            if not any(c[0] == self.instance.category for c in cat_choices):
                cat_choices.append((self.instance.category, self.instance.category))
        self.fields["category"].choices = cat_choices

        # Populate SourceCode dropdown
        sc_choices = [("", "-")] + [
            (s.name, s.name) for s in SourceCode.objects.filter(is_enabled=True)
        ]
        if self.instance and self.instance.pk and self.instance.source_code:
            if not any(s[0] == self.instance.source_code for s in sc_choices):
                sc_choices.append((self.instance.source_code, self.instance.source_code))
        self.fields["source_code"].choices = sc_choices

        # Populate Community dropdown
        comm_choices = [(c.name, c.name) for c in Community.objects.filter(is_enabled=True)]
        self.fields["community"].choices = comm_choices

        # Populate Share dropdown
        share_choices = [(s.name, s.name) for s in ShareOption.objects.filter(is_enabled=True)]
        self.fields["share"].choices = share_choices

        # Initial values for multiselects
        if self.instance and self.instance.pk:
            if self.instance.community:
                self.initial["community"] = [c.strip() for c in self.instance.community.split(",") if c.strip()]
            if self.instance.share:
                self.initial["share"] = [s.strip() for s in self.instance.share.split(",") if s.strip()]

    def clean_length(self):
        length = self.cleaned_data.get("length", "").strip()
        if not re.match(r"^\d{2}:\d{2}:\d{2}$", length):
            raise forms.ValidationError("Length must be in HH:MM:SS format.")
        return length

    def clean_filename(self):
        filename = self.cleaned_data.get("filename", "").strip()
        if not re.match(r'^[^\\/:*?"<>|]+\.[a-zA-Z0-9]{1,5}$', filename):
            raise forms.ValidationError("Filename must be valid with an extension (e.g., myfile.mp4).")
        return filename

    def clean_comments(self):
        comments = self.cleaned_data.get("comments") or ""
        if len(comments) > 255:
            raise forms.ValidationError("Comments must be under 255 characters.")
        return comments

    def save(self, commit=True):
        instance = super().save(commit=False)
        comm_list = self.cleaned_data.get("community") or []
        instance.community = ",".join(comm_list) if comm_list else ""
        share_list = self.cleaned_data.get("share") or []
        instance.share = ",".join(share_list) if share_list else ""
        if commit:
            instance.save()
        return instance


class SeriesForm(forms.ModelForm):
    class Meta:
        model = Series
        fields = ["title", "owner_group", "series_type", "description"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "required": "required"}),
            "owner_group": forms.Select(attrs={"class": "form-select"}),
            "series_type": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth.models import Group
        if user:
            can_view_all_s = user.is_superuser or user.has_perm("programs.view_all_series")
            if can_view_all_s:
                self.fields["owner_group"].queryset = Group.objects.all()
            else:
                self.fields["owner_group"].queryset = user.groups.all()
                if not self.instance.pk and user.groups.exists():
                    self.initial["owner_group"] = user.groups.first()


class CustomFieldForm(forms.ModelForm):
    class Meta:
        model = CustomField
        fields = [
            "target_element",
            "label",
            "name",
            "field_type",
            "choices",
            "description",
            "default_value",
            "required",
            "is_active",
        ]
        widgets = {
            "target_element": forms.Select(attrs={"class": "form-select", "required": "required"}),
            "label": forms.TextInput(attrs={"class": "form-control", "required": "required"}),
            "name": forms.TextInput(attrs={"class": "form-control", "required": "required"}),
            "field_type": forms.Select(attrs={"class": "form-select", "id": "fieldTypeSelect"}),
            "choices": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Comma or newline separated options for enum list (e.g. Red, Blue, Green)",
                "id": "choicesField",
            }),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "default_value": forms.TextInput(attrs={"class": "form-control"}),
            "required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "display_name", "is_enabled"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "display_name": forms.TextInput(attrs={"class": "form-control"}),
            "is_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class CommunityForm(forms.ModelForm):
    class Meta:
        model = Community
        fields = ["name", "is_enabled"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "is_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class SMTPSettingsForm(forms.ModelForm):
    class Meta:
        model = SMTPSettings
        fields = [
            "host",
            "port",
            "username",
            "password",
            "use_tls",
            "use_ssl",
            "timeout",
            "from_address",
            "envelope_from",
            "is_active",
        ]
        widgets = {
            "host": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. postfix.internal or smtp.relay.com"}),
            "port": forms.NumberInput(attrs={"class": "form-control"}),
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "password": forms.PasswordInput(attrs={"class": "form-control"}, render_value=True),
            "use_tls": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "use_ssl": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "timeout": forms.NumberInput(attrs={"class": "form-control"}),
            "from_address": forms.EmailInput(attrs={"class": "form-control", "placeholder": "wcgtv@wcgtv.local"}),
            "envelope_from": forms.EmailInput(attrs={"class": "form-control", "placeholder": "postfix-bounce@wcgtv.local (defaults to from address if blank)"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class BulkProgramImportForm(forms.Form):
    csv_file = forms.FileField(
        required=False,
        label="Upload CSV File",
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".csv,text/csv"}),
        help_text="Upload a .csv file containing programs metadata",
    )
    csv_text = forms.CharField(
        required=False,
        label="Or Paste CSV Data",
        widget=forms.Textarea(
            attrs={
                "class": "form-control font-monospace",
                "rows": 10,
                "placeholder": 'id,created,title,dateRecorded,expiryDate,producer,length,category,community,sourceCode,share,filename,comments\n1,"2015-03-10 16:47:28",Title,2015-02-02,,fred,01:02:03,sports,,,,asfhnafuopsgdhosgdu90sgd.mp4,',
            }
        ),
        help_text="Paste CSV content directly here. Must include header row.",
    )
    preserve_ids = forms.BooleanField(
        required=False,
        initial=False,
        label="Preserve existing IDs if provided (and not colliding)",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="If checked and ID does not already exist, the program will be created with the specified ID.",
    )
    skip_errors = forms.BooleanField(
        required=False,
        initial=True,
        label="Skip invalid rows and continue importing valid ones",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="If unchecked, the entire import will fail if any row has validation errors.",
    )

    def clean(self):
        cleaned_data = super().clean()
        csv_file = cleaned_data.get("csv_file")
        csv_text = cleaned_data.get("csv_text")
        if not csv_file and not (csv_text and csv_text.strip()):
            raise forms.ValidationError("Please upload a CSV file or paste CSV content.")
        return cleaned_data


class EventHookForm(forms.ModelForm):
    class Meta:
        model = EventHook
        fields = [
            "name",
            "event_type",
            "action_type",
            "is_active",
            "recipient_emails",
            "email_subject",
            "email_body",
            "webhook_url",
            "webhook_secret",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "required": "required"}),
            "event_type": forms.Select(attrs={"class": "form-select"}),
            "action_type": forms.Select(attrs={"class": "form-select", "id": "actionTypeSelect"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "recipient_emails": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "ops@wcgtv.ca, producer@wcgtv.ca"}),
            "email_subject": forms.TextInput(attrs={"class": "form-control"}),
            "email_body": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "webhook_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://api.example.com/webhooks/wcgtv"}),
            "webhook_secret": forms.TextInput(attrs={"class": "form-control"}),
        }


class SourceCodeForm(forms.ModelForm):
    class Meta:
        model = SourceCode
        fields = ["name", "is_enabled"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "is_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ShareOptionForm(forms.ModelForm):
    class Meta:
        model = ShareOption
        fields = ["name", "is_enabled"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "is_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
