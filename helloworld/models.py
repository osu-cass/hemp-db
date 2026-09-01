from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

# Django strongly encourages using lowercase table names using MySQL
# https://docs.djangoproject.com/en/5.1/ref/models/options/
# This will also restrict us to using snake_case so words are preserved.
# For consistency, singular names will also be implemented.

# TODO / Nice to have: Update Django model class and field names to also 
# follow these naming conventions. Will need carefully reviewed
# Django migrations to prevent data loss.
# 
# Naming Convention Rules:
# lowercase
# snake_case
# singular 

class UploadIndex(models.Model):
    pendingID = models.CharField(max_length=255)

    class Meta:
        db_table = "upload_index"

        verbose_name = "Upload Index"
        verbose_name_plural = "Upload Indexes"

class Resources(models.Model):
    type = models.CharField(max_length=255)
    title = models.CharField(max_length=255, blank=True)
    url = models.CharField(max_length=1024, blank=True)
    text = models.CharField(max_length=2048, blank=True)
    image = models.CharField(max_length=1024, blank=True)
    priority = models.SmallIntegerField(blank=True, null=True)

    class Meta:
        db_table = "resource"

        verbose_name = "Resource"
        verbose_name_plural = "Resources"

class Solution(models.Model):
    solution = models.CharField(max_length=1024)
    
    def __str__(self):
        return self.solution

    class Meta:
        db_table = "solution"

        verbose_name = "Solution"
        verbose_name_plural = "Solutions"

class Category(models.Model):
    category = models.CharField(max_length=1024)

    def __str__(self):
        return self.category

    class Meta:
        db_table = "category"

        verbose_name = "Category"
        verbose_name_plural = "Categories"

class stakeholderGroups(models.Model):
    stakeholderGroup = models.CharField(max_length=1024)
    category = models.IntegerField()

    def __str__(self):
        return self.stakeholderGroup
    
    class Meta:
        db_table = "stakeholder_group"

        verbose_name = "Stakeholder Group"
        verbose_name_plural = "Stakeholder Groups"

class Stage(models.Model):
    stage = models.CharField(max_length=1024)

    def __str__(self):
        return self.stage

    class Meta:
        db_table = "stage"

        verbose_name = "Stage"
        verbose_name_plural = "Stages"

class ProductGroup(models.Model):
    productGroup = models.CharField(max_length=1024)

    def __str__(self):
        return self.productGroup

    class Meta:
        db_table = "product_group"

        verbose_name = "Product Group"
        verbose_name_plural = "Product Groups"

class Status(models.Model):
    status = models.CharField(max_length=250)

    def __str__(self):
        return "Status: " + self.status

    class Meta:
        db_table = "status"

        verbose_name = "Status"
        verbose_name_plural = "Statuses"

class Industry(models.Model):
    industry = models.CharField(max_length=250)

    def __str__(self):
        return "Industry: " + self.industry

    class Meta:
        db_table = "industry"

        verbose_name = "Industry"
        verbose_name_plural = "Industries"

class Grower(models.Model):
    grower = models.CharField(max_length=250)

    def __str__(self):
        return "Grower: " + self.grower

    class Meta:
        db_table = "grower"

        verbose_name = "Grower"
        verbose_name_plural = "Growers"

# Abstract base model for company-data related models.
# Altering this model will effect all models that inherit it,
# allowing for simpler implementation of features that allow staff users ways to
# manipulate (add/edit/delete) data fields through an interface (not programmatically)
#
# Also allows for easier development, avoiding redundant, duplicate code.
class CompanyDetail(models.Model):
    SrcKey = models.CharField(max_length=128, default=None, blank=True)
    Name = models.CharField(max_length=250)
    Industry = models.ForeignKey(Industry, null=True, on_delete=models.SET_NULL)
    Status = models.ForeignKey(Status, null=True, on_delete=models.SET_NULL)
    Grower = models.ForeignKey(Grower, null=True, on_delete=models.SET_NULL)
    Headquarters = models.CharField(max_length=255, blank=True)
    Address = models.CharField(max_length=512, default=None, blank=True)
    Sales = models.CharField(max_length=255, blank=True)
    Product = models.CharField(max_length=255, blank=True)
    City = models.CharField(max_length=250, blank=True)
    State = models.CharField(max_length=250, blank=True)
    Country = models.CharField(max_length=250)
    Latitude = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True)
    Longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    Website = models.CharField(max_length=512, blank=True)
    Solutions = models.ManyToManyField(Solution, blank=True)
    Category = models.ManyToManyField(Category, blank=True)
    stakeholderGroup = models.ManyToManyField(stakeholderGroups, blank=True)
    Stage = models.ManyToManyField(Stage, blank=True)
    productGroup = models.ManyToManyField(ProductGroup, blank=True)
    Products = models.CharField(max_length=250, blank=True)
    sasContact = models.CharField(max_length=250, blank=True)
    Description = models.CharField(max_length=2048, blank=True)
    pubPriv = models.CharField(max_length=128, blank=True)
    Ticker = models.CharField(max_length=128, blank=True)
    Naics = models.CharField(max_length=250, blank=True)
    Phone = models.CharField(max_length=250, blank=True)
    Email = models.CharField(max_length=250, blank=True)
    Stakeholder = models.CharField(max_length=250, blank=True)
    Principal = models.CharField(max_length=250, blank=True)
    Founded = models.CharField(max_length=250, blank=True)
    Employees = models.CharField(max_length=250, blank=True)
    parentCompany = models.CharField(max_length=250, blank=True)
    onMarket = models.CharField(max_length=250, blank=True)
    productName = models.CharField(max_length=250, blank=True)
    SKU = models.CharField(max_length=250, blank=True)
    Notes = models.CharField(max_length=1024, blank=True)
    processingFocus = models.CharField(max_length=1024, blank=True)
    facilitySize = models.CharField(max_length=250, blank=True)
    biomassCap = models.CharField(max_length=250, blank=True)
    extractionType = models.CharField(max_length=1024, blank=True)
    GMP = models.CharField(max_length=250, blank=True)
    news = models.CharField(max_length=1024, blank=True)
    reviews = models.CharField(max_length=512, blank=True)
    dateCreated = models.DateTimeField(default=timezone.now, blank=False) # default set to 1/1/2024 (12/31/2023 4pm PST); arbitrary date to fill the entry
    lastUpdated = models.DateTimeField(auto_now=True, blank=False)

    def shared_concrete_field_values(self, target_model, *, excluded_fields=()):
        """Return non-primary-key values shared with another company model."""
        target_field_names = {
            field.attname for field in target_model._meta.concrete_fields
        }
        return {
            field.attname: getattr(self, field.attname)
            for field in self._meta.concrete_fields
            if not field.primary_key
            and field.name not in excluded_fields
            and field.attname in target_field_names
        }

    #
    # Overriding the save function
    # Necessary to autofill entries missing 'lastUpdated' field with the 'dateCreated' field
    #
    def save(self, *args, **kwargs):
        if not self.lastUpdated:
            self.lastUpdated = self.dateCreated
        else:
            self.lastUpdated = timezone.now()
        super().save(*args, **kwargs) # DOES NOT SAVE UPDATES WITHOUT THIS LINE #

    class Meta:
        abstract = True

class PendingCompany(CompanyDetail):

    # Correlation token for bulk-imported rows; cleared once an import commits.
    import_batch_id = models.UUIDField(null=True, blank=True, db_index=True, editable=False)

    class Meta:
        db_table = "pending_company"

        verbose_name = "Pending Company"
        verbose_name_plural = "Pending Companies"

class Company(CompanyDetail):
    pendingChanges = models.ManyToManyField(PendingCompany, through="PendingChanges")
    class Meta:
        db_table = "company"
        indexes = [models.Index(fields=["Name"], name="company_name_idx")]

        verbose_name = "Company"
        verbose_name_plural = "Companies"

class PendingChanges(models.Model):
    # If a company is deleted, delete all of its associated pending changes
    company = models.ForeignKey(Company, null=True, on_delete=models.CASCADE)
    pending_company = models.ForeignKey(PendingCompany, null=True, on_delete=models.CASCADE)

    # If a user is deleted, don't necessarily delete their proposed changes
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    
    created_at = models.DateTimeField(default=now)
    changeType = models.CharField(max_length=250)

    # Marks if a pending change is either pending, approved, or rejected
    # ["Pending", "Approved", "Rejected"]
    class PendingStatus(models.TextChoices):
        PENDING = "P", _("Pending")
        APPROVED = "A", _("Approved")
        REJECTED = "R", _("Rejected")

    status = models.CharField(max_length=250, choices=PendingStatus.choices, default=PendingStatus.PENDING)

    class Meta:
        db_table = "pending_change"

        verbose_name = "Pending Change"
        verbose_name_plural = "Pending Changes"
