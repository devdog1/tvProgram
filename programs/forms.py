import re
from django import forms
from .models import Program, Category, Community, SourceCode, ShareOption

DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_REGEX = re.compile(r"^\d{2}:\d{2}:\d{2}$")
FILENAME_REGEX = re.compile(r'^[^\\/:*?"<>|]+\.[a-zA-Z0-9]{1,5}$')


class ProgramForm(forms.ModelForm):
    category = forms.ChoiceField(required=False, choices=[("", "-")])
    community = forms.MultipleChoiceField(required=False, choices=[])
    source_code = forms.ChoiceField(required=False, choices=[("", "-")])
    share = forms.MultipleChoiceField(required=False, choices=[])

    class Meta:
        model = Program
        fields = [
            "title",
            "date_recorded",
            "expiry_date",
            "producer",
            "length",
            "category",
            "community",
            "source_code",
            "share",
            "filename",
            "comments",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "id": "title", "required": "required"}),
            "date_recorded": forms.TextInput(attrs={"class": "form-control", "id": "dateRecorded", "required": "required", "placeholder": "YYYY-MM-DD"}),
            "expiry_date": forms.TextInput(attrs={"class": "form-control", "id": "expiryDate", "placeholder": "YYYY-MM-DD"}),
            "producer": forms.TextInput(attrs={"class": "form-control", "id": "producer", "required": "required"}),
            "length": forms.TextInput(attrs={"class": "form-control", "id": "length", "required": "required", "placeholder": "HH:MM:SS"}),
            "filename": forms.TextInput(attrs={"class": "form-control", "id": "filename", "required": "required"}),
            "comments": forms.TextInput(attrs={"class": "form-control", "id": "comments", "maxlength": "255"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Dynamic choices for Category from active options
        categories = Category.objects.filter(is_enabled=True)
        cat_choices = [("", "-")] + [(c.name, c.display_name or c.name) for c in categories]
        # If editing and current value is disabled, preserve it
        if self.instance and self.instance.pk and self.instance.category:
            if not any(c[0] == self.instance.category for c in cat_choices):
                cat_choices.append((self.instance.category, self.instance.category))
        self.fields["category"].choices = cat_choices
        self.fields["category"].widget.attrs.update({"class": "form-select", "id": "category"})

        # Dynamic choices for Community
        communities = Community.objects.filter(is_enabled=True)
        comm_choices = [(c.name, c.name) for c in communities]
        if self.instance and self.instance.pk and self.instance.community:
            existing = self.instance.community_list
            for c_val in existing:
                if not any(c[0] == c_val for c in comm_choices):
                    comm_choices.append((c_val, c_val))
        self.fields["community"].choices = comm_choices
        self.fields["community"].widget.attrs.update({"class": "form-select", "id": "community", "size": "5", "multiple": "multiple"})

        # Dynamic choices for SourceCode
        sources = SourceCode.objects.filter(is_enabled=True)
        src_choices = [("", "-")] + [(s.name, s.name) for s in sources]
        if self.instance and self.instance.pk and self.instance.source_code:
            if not any(s[0] == self.instance.source_code for s in src_choices):
                src_choices.append((self.instance.source_code, self.instance.source_code))
        self.fields["source_code"].choices = src_choices
        self.fields["source_code"].widget.attrs.update({"class": "form-select", "id": "sourceCode"})

        # Dynamic choices for Share
        shares = ShareOption.objects.filter(is_enabled=True)
        share_choices = [(s.name, s.name) for s in shares]
        if self.instance and self.instance.pk and self.instance.share:
            existing_shares = self.instance.share_list
            for s_val in existing_shares:
                if not any(s[0] == s_val for s in share_choices):
                    share_choices.append((s_val, s_val))
        self.fields["share"].choices = share_choices
        self.fields["share"].widget.attrs.update({"class": "form-select", "id": "share", "size": "5", "multiple": "multiple"})

        # Set initial values for multiselects if instance exists
        if self.instance and self.instance.pk:
            if self.instance.community:
                self.initial["community"] = self.instance.community_list
            if self.instance.share:
                self.initial["share"] = self.instance.share_list

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if not title:
            raise forms.ValidationError("Title is required.")
        return title

    def clean_producer(self):
        producer = self.cleaned_data.get("producer", "").strip()
        if not producer:
            raise forms.ValidationError("Producer is required.")
        return producer

    def clean_date_recorded(self):
        date_recorded = self.cleaned_data.get("date_recorded")
        raw_val = self.data.get("date_recorded", "").strip()
        if not raw_val or not DATE_REGEX.match(raw_val):
            raise forms.ValidationError("Date Recorded must be in YYYY-MM-DD format.")
        return date_recorded

    def clean_expiry_date(self):
        expiry_date = self.cleaned_data.get("expiry_date")
        raw_val = self.data.get("expiry_date", "").strip()
        if raw_val:
            if not DATE_REGEX.match(raw_val):
                raise forms.ValidationError("Expiry Date must be in YYYY-MM-DD format.")
        return expiry_date

    def clean_length(self):
        length = self.cleaned_data.get("length", "").strip()
        if not TIME_REGEX.match(length):
            raise forms.ValidationError("Length must be in HH:MM:SS format.")
        return length

    def clean_filename(self):
        filename = self.cleaned_data.get("filename", "").strip()
        if not FILENAME_REGEX.match(filename):
            raise forms.ValidationError("Filename must be valid with an extension (e.g., myfile.mp4).")
        return filename

    def clean_comments(self):
        comments = self.cleaned_data.get("comments") or ""
        comments = comments.strip()
        if len(comments) > 255:
            raise forms.ValidationError("Comments must be under 255 characters.")
        return comments

    def save(self, commit=True):
        instance = super().save(commit=False)
        comm_list = self.cleaned_data.get("community") or []
        instance.community = ",".join([c for c in comm_list if c]) if comm_list else ""
        share_list = self.cleaned_data.get("share") or []
        instance.share = ",".join([s for s in share_list if s]) if share_list else ""
        if commit:
            instance.save()
        return instance


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
