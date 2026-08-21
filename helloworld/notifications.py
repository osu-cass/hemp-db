from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User, Group

# Django Emails: https://docs.djangoproject.com/en/5.1/topics/email/

def email_admins(action: str, company_name: str, pending_change_id: int, request_host: str) -> None:
    """
    Sends an email notification to Admins and SrAdmins when a company has been created, edited, or deleted.

    Note that if the company name is a part of the edit, the new name will appear in the email.
    
    Parameters:
    action (str): Can only be 'created', 'edited', or 'deleted' depending on the action.
    company_name (str): Name of the company
    pending_change_id (int): ID of the pending change
    request_host (str): the host that made the request (e.g. 'hemp-db.cass.oregonstate.edu')
    """

    # If DEBUG is True, this email will be logged to the console, NOT sent (settings.py)
    if not settings.DEBUG:                              # Email will be sent
        if settings.PRODUCTION_URL not in request_host: # Request wansn't made from prod
            return                                      # Don't send email

    # Invalid action
    if action not in ['created', 'edited', 'deleted']:
        return

    subject = f'[HempDB] Company {action} (Pending Review)'
    
    # Plaintext
    text_message = f"""
    A company called "{company_name}" has been {action} and is now pending review.
    
    View pending changes at: {settings.EMAIL_LINK}/changes
    """

    # HTML (clickable links)
    html_message = f"""
    <p>A company called "{company_name}" has been {action} and is now pending review.</p>
    
    <p>View pending changes <a href="{settings.EMAIL_LINK}/changes">here</a>.</p>
    """

    # Group IDs from auth_group containing 'admin' (case insensitive)
    admin_groups = Group.objects.filter(name__icontains='admin')
    admin_group_ids = admin_groups.values_list('id', flat=True)

    # Get list of emails for all users that are some form of admin
    admin_emails = list(User.objects.filter(groups__id__in=admin_group_ids).values_list('email', flat=True).distinct())

    send_mail(
        subject=subject,
        message=text_message,
        from_email=None,    # Uses DEFAULT_FROM_EMAIL
        html_message=html_message,
        recipient_list=admin_emails,
        fail_silently=True
    )
