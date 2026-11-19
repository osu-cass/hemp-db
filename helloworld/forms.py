from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Company
from .models import PendingCompany
from .models import Category
from .models import Solution
from .models import stakeholderGroups
from .models import Stage
from .models import ProductGroup
from .models import Grower
from .models import Industry
from .models import Status
from .models import Resources
from .locations import US_COUNTRY_ALIASES, US_STATE_CHOICES, US_STATES, clean_location, is_us_country
from .validators import HTTPS_URL_MESSAGE


# Company form sections in display order (AB#5402). Each editable field appears once.
COMPANY_FIELD_SECTIONS = (
    ("Identity", (
        "Name", "Industry", "Status", "Grower", "Website", "Description", "Founded",
        "Employees", "parentCompany", "pubPriv", "Ticker", "Naics",
    )),
    ("Location", (
        "Headquarters", "Address", "City", "State", "ZIP", "Country", "Latitude", "Longitude",
    )),
    ("Sales and products", (
        "Sales", "Product", "Products", "ProductsPageUrl", "productName", "SKU", "onMarket",
        "productGroup",
    )),
    ("Classification", ("Category", "stakeholderGroup", "Stage", "Solutions")),
    ("Contact", ("Phone", "Email", "Principal", "Stakeholder", "sasContact")),
    ("Operations", ("processingFocus", "facilitySize", "biomassCap", "extractionType", "GMP")),
    ("Notes", ("Notes", "news", "reviews")),
    ("Record", ("SrcKey", "dateCreated")),
)


class StateWidget(forms.TextInput):
    """Render State as a USPS dropdown for USA companies and free text otherwise."""

    template_name = "widgets/us_state.html"

    def __init__(self, attrs=None):
        super().__init__(attrs)
        self.us_country = False

    def get_context(self, name, value, attrs):
        """Add the USPS choices and which control starts active."""
        context = super().get_context(name, value, attrs)
        widget = context["widget"]
        value = widget["value"] or ""
        widget.update(
            field_id=widget["attrs"].pop("id", ""),
            us_country=self.us_country,
            choices=US_STATE_CHOICES,
            # Keep an unmapped value selected so an edit never blanks it silently
            unmapped=value if value not in US_STATES else "",
            us_countries="|".join(sorted(US_COUNTRY_ALIASES)),
        )
        return context


class ResourceForm(forms.ModelForm):
    CHOICES = (
        ('about', 'About Page Text'),
        ('contribute', 'Contribute Text'),
        ('contribute_contact', 'Contribute Contact'),
        ('article', 'Article'),
        ('home_text', 'Home Page Text'),
        ('home_title', 'Home Page Title')
    )

    type = forms.ChoiceField(choices=CHOICES,
                             widget=forms.RadioSelect,
                             required = True)
    text = forms.CharField(widget=forms.Textarea, required=False)

    class Meta:
        model = Resources
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class UploadFileForm(forms.Form):
    file = forms.FileField()
    
class FilterStatusForm(forms.Form):
    status = forms.ModelMultipleChoiceField(queryset=Status.objects.all(),
                                              widget=forms.CheckboxSelectMultiple,
                                              required=True)
    
class FilterIndustryForm(forms.Form):
    industry = forms.ModelMultipleChoiceField(queryset=Industry.objects.all(),
                                              widget=forms.CheckboxSelectMultiple,
                                              required=True)

class FilterCategoryForm(forms.Form):
    category = forms.ModelMultipleChoiceField(queryset=Category.objects.all(),
                                              widget=forms.CheckboxSelectMultiple,
                                              required=True)

class FilterStakeholderGroupForm(forms.Form):
    stakeholder_groups = forms.ModelMultipleChoiceField(queryset=stakeholderGroups.objects.all(),
                                              widget=forms.CheckboxSelectMultiple,
                                              required=True)

class FilterStageForm(forms.Form):
    stage = forms.ModelMultipleChoiceField(queryset=Stage.objects.all(),
                                              widget=forms.CheckboxSelectMultiple,
                                              required=True)

class FilterProductGroupForm(forms.Form):
    product_group = forms.ModelMultipleChoiceField(queryset=ProductGroup.objects.all(),
                                              widget=forms.CheckboxSelectMultiple,
                                              required=True)

class FilterSolutionForm(forms.Form):
    solution = forms.ModelMultipleChoiceField(queryset=Solution.objects.all(),
                                              widget=forms.CheckboxSelectMultiple,
                                              required=True)
    
class FilterStateForm(forms.Form):
    # site.js turns this into an "Add" dropdown with removable chips
    state = forms.MultipleChoiceField(
        widget=forms.SelectMultiple(attrs={"data-chip-placeholder": "Add a state"}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # US states that have at least one company; other countries' regions are free text
        used = {
            state.upper()
            for state in Company.objects.filter(State__in=US_STATES).values_list("State", flat=True)
        }
        self.fields["state"].choices = [
            choice for choice in US_STATE_CHOICES if choice[0] in used
        ]

class SearchForm(forms.Form):
    q = forms.CharField(label='Search', max_length=100, widget=forms.TextInput(attrs={'placeholder': 'Search by Name'}))

class CompanyForm(forms.ModelForm):
    required_css_class = 'required'

    class Meta:
        model = Company
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class PendingCompanyForm(forms.ModelForm):
    required_css_class = 'required'
    Solutions = forms.ModelMultipleChoiceField(
            queryset=Solution.objects.all(),
            widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '8', 'style': 'margin-bottom: 10px;'}),
            required=False)
    Category = forms.ModelMultipleChoiceField(
            queryset=Category.objects.all(),
            widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '8', 'style': 'margin-bottom: 10px;'}),
            required=False)
    stakeholderGroup = forms.ModelMultipleChoiceField(
            queryset=stakeholderGroups.objects.all(),
            widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '8', 'style': 'margin-bottom: 10px;'}),
            required=False)
    Stage = forms.ModelMultipleChoiceField(
            queryset=Stage.objects.all(),
            widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '8', 'style': 'margin-bottom: 10px;'}),
            required=False)
    productGroup = forms.ModelMultipleChoiceField(
            queryset=ProductGroup.objects.all(),
            widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '8', 'style': 'margin-bottom: 10px;'}),
            required=False)

    class Meta:
        model = PendingCompany
        fields = "__all__"
        # One message whether the form field or the model validator rejects it.
        error_messages = {"ProductsPageUrl": {"invalid": HTTPS_URL_MESSAGE}}
        widgets = {"State": StateWidget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['Latitude'].label = "Latitude (Up to 6 decimals)"
        self.fields['Longitude'].label = "Longitude (Up to 6 decimals)"
        self.fields['State'].label = "State"
        self.fields['State'].widget.us_country = is_us_country(self['Country'].value())

    def sections(self):
        """Return (title, bound fields) pairs in display order."""
        return [(title, [self[name] for name in names]) for title, names in COMPANY_FIELD_SECTIONS]

    def clean(self):
        """Store a USPS State code and check ZIP format for USA companies."""
        cleaned_data = super().clean()
        state, zip_code, errors = clean_location(
            cleaned_data.get("Country"),
            cleaned_data.get("State"),
            cleaned_data.get("ZIP"),
            allow_state_names=False,
        )
        for field_name, value in (("State", state), ("ZIP", zip_code)):
            if field_name in cleaned_data:
                cleaned_data[field_name] = value
        for field_name, message in errors.items():
            self.add_error(field_name, message)
        return cleaned_data

class CategoryForm(forms.ModelForm): 
    
    class Meta:
        model = Category
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class SolutionForm(forms.ModelForm): 

    class Meta:
        model = Solution
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class stakeholderGroupsForm(forms.ModelForm): 

    class Meta:
        model = stakeholderGroups
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class StageForm(forms.ModelForm): 

    class Meta:
        model = Stage
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class ProductGroupForm(forms.ModelForm): 

    class Meta:
        model = ProductGroup
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()
    full_name = forms.CharField(max_length = 100)
    username = forms.CharField(max_length = 100)
    class Meta:
        model = User
        fields = ['username', 'email', 'full_name', 'password1', 'password2']

class GrowerForm(forms.ModelForm): 

    class Meta:
        model = Grower
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class StatusForm(forms.ModelForm): 

    class Meta:
        model = Status
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class IndustryForm(forms.ModelForm): 

    class Meta:
        model = Industry
        fields = "__all__"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)