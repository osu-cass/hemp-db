from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from helloworld.models import Company
from datetime import datetime, timedelta
from django.utils.timezone import now, localtime
import pandas as pd

class Command(BaseCommand):
    help = "Audits companies and flags missing/old data"

    """
    handle() is required for any django management commands

    this function is designed to audit the database to identify any records that have not been edited in the last 6 months or are lacking the following fields:

    field                   sql_alias
    -------------------------------------------
    Name                    Name
    Status                  Status
    Industry                Industry
    Stakeholder Category    Category
    Stakeholder Group       stakeholderGroup
    Development Stage       Stage
    Product Group           productGroup
    Description             Description
    Solution                Solutions


    """
    def handle(self, *args, **kwargs):

        print("Starting Database Auditing Process, this will take a while")
        
        # Initialize the dictionary with empty lists for each field
        df = pd.DataFrame(columns=['id', 'company_name', 'reasons'])

        # Query for companies with missing fields
        missing_data = Company.objects.filter(
            Q(Name__isnull=True) | Q(Name="") | 
            Q(Status__isnull=True) |
            Q(Industry__isnull=True) |
            Q(Description__isnull=True) | Q(Description="") |
            # Many to Many fields
            ~Q(Category__id__isnull=False) |
            ~Q(stakeholderGroup__id__isnull=False) |
            ~Q(Stage__id__isnull=False) |
            ~Q(productGroup__id__isnull=False) |
            ~Q(Solutions__id__isnull=False)
        ).distinct()

        # Iterate over the companies and map their IDs to the corresponding missing field
        for company in missing_data:

            # Check if the company has not been updated in the last 6 months using configured timezone
            six_months_ago = localtime(now() - timedelta(days=6*30))  # Approximate 6 months
            outdated = company.lastUpdated < six_months_ago if company.lastUpdated else True

            reasons = []

            if outdated:
                reasons.append('Outdated Entry')

            if not company.Name:
                reasons.append('Missing Name')

            if not company.Status:
                reasons.append('Missing Status')

            if not company.Industry:
                reasons.append('Missing Industry')

            if not company.Description:
                reasons.append('Missing Description')

            # Many to Many fields, exists() checks for at least 1 entry in the field
            if not company.Category.exists():
                reasons.append('Missing Category')

            if not company.stakeholderGroup.exists():
                reasons.append('Missing Stakeholder Group')

            if not company.Stage.exists():
                reasons.append('Missing Stage')

            if not company.productGroup.exists():
                reasons.append('Missing Product Group')

            if not company.Solutions.exists():
                reasons.append('Missing Solution Information')

            # Only add to DataFrame if there are reasons
            if reasons:
                new_row = pd.DataFrame([{'id': company.id, 'company_name': company.Name, 'reasons': ', '.join(reasons)}])
                df = pd.concat([df, new_row], ignore_index=True)

        today = datetime.now().strftime("%Y-%m-%d")

        file = f"data_audit_{today}.csv"
        path = Path(settings.AUDIT_LOG_DIR)
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / file

        df.to_csv(file_path, index=False)

        print(f"Data saved to {path}")
