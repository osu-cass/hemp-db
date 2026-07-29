from django.db.models.signals import m2m_changed
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.contrib.auth.models import User, Group
from .models import Company, Industry, Category, stakeholderGroups, Stage, ProductGroup



# Triggers when a user's group is updated.
# e.g. When a SrAdmin gives a user the Admin group, it will automatically give them is_staff
# so the new admin user may access the Django Administration dashboard. 
# If the user is removed from the group, it will also automatically remove is_staff.
#
# Any group which has the substring "admin" in the group name is considered a staff group
@receiver(m2m_changed, sender=User.groups.through)
def update_is_staff_on_group_change(sender, instance, action, reverse, model, pk_set, **kwargs):
    # Ensure instance is User object to avoid bug when changing m2m data of companies
    if not isinstance(instance, User):
        return

    # Check if the action is 'post_add' (user was added to a group)
    # Enabled is_staff
    if action == "post_add":
        for group_id in pk_set:
            try:
                group = Group.objects.get(id=group_id)
            except Group.DoesNotExist: # Group could not exist if m2m_changed is from a non-group related m2m table
                continue
            if "admin" in group.name.lower():
                instance.is_staff = True
                instance.save()
                break
    
    # Check if the action is 'post_remove' (user was removed from a group)
    # Disables is_staff
    elif action == "post_remove":
        for group_id in pk_set:
            try:
                group = Group.objects.get(id=group_id)
                if "admin" in group.name.lower(): # if the user was removed from an admin group
                    
                    # If the user is no longer in any STAFF_GROUPS, remove is_staff
                    if not any("admin" in g.name.lower() for g in instance.groups.all()):
                        instance.is_staff = False
                        instance.save()
                        break
            except Group.DoesNotExist: # Group could not exist if m2m_changed is from a non-group related m2m table
                continue

"""
Cached map data needs to be invalidated every time data
displayed on the map page is created, edited, or deleted.

The below section will invalidate any cached map data when any model from
map_models is created, edited, or updated. For the Company model, invalidations
will happen when changes are approved, not created. For the other 4 models,
invalidations will happen on creates/deletes since you can't edit these.
"""
# Model instances, that when created, updated, or deleted, 
# should trigger a map_data cache invalidation for the map view
map_models = [Company, Industry, Category, stakeholderGroups, Stage, ProductGroup]

def invalidate_map_cache(sender, **kwargs):
    """
    Invalidates the map_data cache for both production and development environments
    """
    cache.delete('production_map_data')
    cache.delete('development_map_data')

# Connect the signal handler to all models and signal types
for model in map_models:
    post_save.connect(invalidate_map_cache, sender=model)
    post_delete.connect(invalidate_map_cache, sender=model)
