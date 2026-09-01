from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User

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
from .models import CompanyUploadBatch

from .forms import ResourceForm


class HempAdminSite(admin.AdminSite):
    """Admin site restricted to active staff superusers."""

    def has_permission(self, request):
        """Require all built-in administrator flags."""
        user = request.user
        return user.is_active and user.is_staff and user.is_superuser


admin_site = HempAdminSite(name="admin")
admin.site = admin_site
admin_site.register(User, UserAdmin)
admin_site.register(Group, GroupAdmin)

# Customize Django Administration header/title
admin_site.site_header = "HempDB Administration"
admin_site.site_title = "HempDB Admin Portal"
# admin.site.index_title = "HempDB Admin"

# Enables the Log Entries ModelAdmin object for viewing
admin_site.register(LogEntry)

# Register DB models here for Django admin users with model permissions

@admin.register(Company, site=admin_site)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["Name", "id"]
    search_fields = ["Name"]

@admin.register(PendingCompany, site=admin_site)
class PendingCompanyAdmin(admin.ModelAdmin):
    pass

@admin.register(PendingChanges, site=admin_site)
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


@admin.register(CompanyUploadBatch, site=admin_site)
class CompanyUploadBatchAdmin(admin.ModelAdmin):
    """Expose upload batches to superusers for operational inspection."""

    list_display = ["id", "original_filename", "uploader", "status", "created_at", "reviewer"]
    list_filter = ["status", "review_mode"]
    search_fields = ["original_filename", "uploader__username", "reviewer__username"]
    readonly_fields = [
        "id",
        "uploader",
        "original_filename",
        "status",
        "review_mode",
        "created_at",
        "reviewed_at",
        "reviewer",
    ]

    def has_add_permission(self, request):
        """Keep upload batches created by the upload workflow."""
        return False

    def has_change_permission(self, request, obj=None):
        """Allow inspection without allowing batch metadata changes."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deleting batches from the administration site."""
        return False

@admin.register(Resources, site=admin_site)
class ResourcesAdmin(admin.ModelAdmin):
    form = ResourceForm
    list_display = ["type", "title"]

@admin.register(Solution, site=admin_site)
class SolutionAdmin(admin.ModelAdmin):
    pass

@admin.register(Category, site=admin_site)
class CategoryAdmin(admin.ModelAdmin):
    pass

@admin.register(stakeholderGroups, site=admin_site)
class stakeholderGroupsAdmin(admin.ModelAdmin):
    pass

@admin.register(Stage, site=admin_site)
class StageAdmin(admin.ModelAdmin):
    pass

@admin.register(ProductGroup, site=admin_site)
class ProductGroupAdmin(admin.ModelAdmin):
    pass

@admin.register(Status, site=admin_site)
class StatusAdmin(admin.ModelAdmin):
    pass

@admin.register(Industry, site=admin_site)
class IndustryAdmin(admin.ModelAdmin):
    pass

@admin.register(Grower, site=admin_site)
class GrowerAdmin(admin.ModelAdmin):
    pass
