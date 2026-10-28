## Django
from django.urls import path
from django.contrib.auth import views as auth_views
## Views
from . import views

urlpatterns = [
    # Root
    path("", views.index, name="index"),

    # About
    path("about/", views.about),

    # Contribute
    path("contribute/", views.contribute),
    
    # File Upload
    path("upload/", views.upload_file, name="upload"),
    path("upload_wizard", views.upload_wizard, name="upload-wizard"),
    
    # Hemp Map
    path("map/", views.map),

    # Companies
    path('companies/', views.companies, name="companies"),
    path('companies/<int:id>', views.view_company, name='company-view'),
    path('companies_pending/<int:id>', views.view_company_pending, name='company-view-pending'),
    path('companies_approve/<int:id>', views.view_company_approve, name='company-pending-approve'),
    path('companies_reject/<int:id>', views.view_company_reject, name='company-pending-reject'),
    path('companies/search/', views.companies_filtered, name='company-filtered'),
    path('remove_companies/<int:id>', views.remove_companies, name='remove-company'),
    path('export_companies/', views.export_companies, name='export-companies'),
    path('companies/edit/<int:id>', views.edit_company, name='edit-company'),

    # Categories
    path('categories/', views.categories, name="categories"),
    path('remove_categories/<int:id>', views.remove_categories),
    path('export_categories/', views.export_categories, name='export-categories'),

    # Solutions 
    path('solutions/', views.solutions, name="solutions"),
    path('remove_solutions/<int:id>', views.remove_solutions),
    path('export_solutions/', views.export_solutions, name='export-solutions'),

    # Stakeholder Groups
    path('stakeholder-groups/', views.StakeholderGroups, name="StakeholderGroups"),
    path('remove_stakeholder_groups/<int:id>', views.remove_stakeholder_groups),
    path('export_stakeholder_groups/', views.export_stakeholder_groups, name='export-stakeholder_groups'),

    # Stage
    path('stages/', views.stages, name="stages"),
    path('remove_stages/<int:id>', views.remove_stages),
    path('export_stages/', views.export_stages, name='export-stages'),

    # Product Group
    path('product-groups/', views.productGroups, name="productGroups"),
    path('remove_product_group/<int:id>', views.remove_product_groups),
    path('export_product_groups/', views.export_product_groups, name='export-product_groups'),

    # Status
    path('status/', views.status, name="status"),
    path('remove_status/<int:id>', views.remove_status),
    path('export_status/', views.export_status, name='export-status'),

    # Grower
    path('grower/', views.grower, name="grower"),
    path('remove_grower/<int:id>', views.remove_grower),
    path('export_grower/', views.export_grower, name='export-grower'),

    # Industry
    path('industry/', views.industry, name="industry"),
    path('remove_industry/<int:id>', views.remove_industry),
    path('export_industry/', views.export_industry, name='export-industry'),

    # User Registration
    path('user/register', views.register),
    
    # User Authentication
    path('activate/<uidb64>/<token>', views.activate, name='activate'),
    
    # Password Reset: https://docs.djangoproject.com/en/5.1/topics/auth/default/#changing-passwords
    path('password_reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    # Changes
    path('changes/', views.dbChanges),
    path('my_changes/', views.myChanges, name='my_changes'),
]
