from django.core.validators import EmailValidator

from pennyblack.module.subscriber.models import NewsletterSubscriber, SubscriberGroup


def add_subscriber(email, groups=[], **kwargs):
    """
    Adds a subscriber to the given groups
    """
    valid_email = EmailValidator()
    if not valid_email(email):
        return False
    subscriber = NewsletterSubscriber.objects.get_or_add(email, **kwargs)
    for group_name in groups:
        group = SubscriberGroup.objects.get_or_add(group_name)
        if group not in subscriber.groups.all():
            subscriber.groups.add(group)
    return subscriber
