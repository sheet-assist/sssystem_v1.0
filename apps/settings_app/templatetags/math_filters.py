from django import template

register = template.Library()


@register.filter
def multiply(value, arg):
    """Multiply the value by arg."""
    try:
        return int(value) * int(arg)
    except:
        return 0


@register.filter
def divide(value, arg):
    """Divide value by arg."""
    try:
        return int(value) / int(arg)
    except:
        return 0
