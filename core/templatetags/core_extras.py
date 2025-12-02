from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Permite acceder a dicts en templates."""
    if isinstance(mapping, dict):
        return mapping.get(key)
    return None
