from django.db.models.signals import post_save, post_delete
from django.core.cache import cache
from .models import Company, Industry, Category, stakeholderGroups, Stage, ProductGroup

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
    for key in ('production_map_data', 'development_map_data'):
        try:
            cache.delete(key)
        except Exception:
            # Cache availability must not block a database write.
            continue

# Connect the signal handler to all models and signal types
for model in map_models:
    post_save.connect(invalidate_map_cache, sender=model)
    post_delete.connect(invalidate_map_cache, sender=model)
