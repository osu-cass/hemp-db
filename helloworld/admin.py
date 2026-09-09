from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse

from django.contrib import admin

from django.contrib.admin.models import LogEntry

from .models import Company
from .models import PendingCompany
from .models import PendingChanges
from .models import Resources
from .models import Solution
from .models import Category
from .models import stakeholderGroups
from .models import Stage
from .models import ProductGroup
from .models import Status
from .models import Industry
from .models import Grower

from .forms import ResourceForm

# Customize Django Administration header/title
admin.site.site_header = "HempDB Administration"
admin.site.site_title = "HempDB Admin Portal"
# admin.site.index_title = "HempDB Admin"

# Enables the Log Entries ModelAdmin object for viewing
admin.site.register(LogEntry)

# Register DB models here for staff access

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["Name", "id"]
    search_fields = ["Name"]

@admin.register(PendingCompany)
class PendingCompanyAdmin(admin.ModelAdmin):
    pass

@admin.register(PendingChanges)
class PendingChangesAdmin(admin.ModelAdmin):
    list_display = ["company_link", "changeType", "author", "colored_status", "created_at_pst"]
    
    search_fields = ['author__username', 'author__first_name', 'author__last_name']

    # Creates the hyperlink based off the change type.
    # e.i. create types only have pending_company foreign keys
    # edit and deletion types relate with a company foreign key
    def company_link(self, obj):
        try:
            if obj.changeType == "create" and obj.pending_company:
                url = reverse('admin:helloworld_pendingcompany_change', args=[obj.pending_company.id])
                name = str(obj.pending_company.Name)

            elif (obj.changeType == "edit" or obj.changeType == "deletion") and obj.company:
                url = reverse('admin:helloworld_company_change', args=[obj.company.id])
                name = str(obj.company.Name)

            else:
                return "-"
            
            return format_html('<a href="{}">{}</a>', url, name)
        
        except Exception as e:
            return f"Error: {e}"
        
    company_link.short_description = "Company"

    def colored_status(self, obj):
        if obj.status == PendingChanges.PendingStatus.PENDING:
            color = 'orange'
        elif obj.status == PendingChanges.PendingStatus.APPROVED:
            color = 'green'
        elif obj.status == PendingChanges.PendingStatus.REJECTED:
            color = 'red'
        else:
            color = 'gray'
    
        return format_html('<span style="color: {};">{}</span>', color, obj.get_status_display())
    
    colored_status.short_description = "Status"

    def created_at_pst(self, obj):
        local_dt = timezone.localtime(obj.created_at, timezone.get_fixed_timezone(-480)) # UTC-8 (PST)
        return local_dt.strftime('%Y-%m-%d %H:%M:%S')

    created_at_pst.short_description = "Created at (PST)"

@admin.register(Resources)
class ResourcesAdmin(admin.ModelAdmin):
    form = ResourceForm
    list_display = ["type", "title"]

@admin.register(Solution)
class SolutionAdmin(admin.ModelAdmin):
    pass

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    pass

@admin.register(stakeholderGroups)
class stakeholderGroupsAdmin(admin.ModelAdmin):
    pass

@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    pass

@admin.register(ProductGroup)
class ProductGroupAdmin(admin.ModelAdmin):
    pass

@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    pass

@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    pass

@admin.register(Grower)
class GrowerAdmin(admin.ModelAdmin):
    pass