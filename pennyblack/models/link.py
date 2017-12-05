from django.contrib import admin
from django.core.urlresolvers import resolve
from django.db import models
from django.template import Context, Template
from django.utils.translation import ugettext_lazy as _

import hashlib
import random

try:
    from django.utils.timezone import now
except ImportError:
    from datetime import datetime
    now = datetime.now


#-----------------------------------------------------------------------------
# Link
#-----------------------------------------------------------------------------
def is_link(link_original, link_replaced):
    """
    Checks if link_replaced resolves to link_original
    """
    from pennyblack.models import Link
    if link_replaced == '':
        return False
    # try to find the link and compare it to the header_url but
    # replace the link if something goes wrong
    try:
        link_hash = resolve(link_replaced[len('{{base_url}}'):])[2]['link_hash']
        link = Link.objects.get(link_hash=link_hash)
        if link.link_target == link_original:
            return True
    except:
        pass
    return False


def check_if_redirect_url(url):
    """
    Checks if the url is a redirect url
    """
    if '{{base_url}}' == url[:len('{{base_url}}')]:
        try:
            result = resolve(url[len('{{base_url}}'):])
            if result[0].func_name == 'redirect_link':
                return True
        except:
            pass
    return False


class Link(models.Model):
    """
    Stores a link from a newsletter and generates a hash corresponding to the link.

    If there is a identifier set, then the link belongs to a view which is presented
    to the receiver via the proxy view. These links don't have a link_target.
    """
    job = models.ForeignKey('pennyblack.Job', related_name='links')
    identifier = models.CharField(max_length=100, default='')
    link_hash = models.CharField(max_length=32, verbose_name=_("link hash"), unique=True, blank=True)
    link_target = models.CharField(verbose_name=_("address"), max_length=500, default='')
    token = models.CharField(max_length=32, null=True)

    class Meta:
        verbose_name = _('link')
        verbose_name_plural = _('links')
        app_label = 'pennyblack'
        unique_together = (('job', 'token'))

    def __unicode__(self):
        return self.link_target

    def click_count(self):
        """
        Returns the total click count.
        """
        return self.clicks.count()
    click_count.short_description = 'Click count'

    def click(self, mail):
        """
        Creates a LinkClick and returns the link target
        """
        self.clicks.create(mail=mail)
        return self.get_target(mail)

    def get_target(self, mail):
        """
        gets the link target by evaluating the string using the email content
        """
        from pennyblack.models import Newsletter
        if self.identifier != '':
            return Newsletter.get_view_link(self.identifier)
        template = Template(self.link_target)
        return template.render(Context(mail.get_context()))

    def save(self, **kwargs):
        if self.link_hash == u'':
            self.link_hash = hashlib.md5(str(self.id) + str(random.random())).hexdigest()
        super(Link, self).save(**kwargs)


class LinkClick(models.Model):
    """
    Stores a click on a link.
    """
    link = models.ForeignKey('pennyblack.Link', related_name='clicks')
    mail = models.ForeignKey('pennyblack.Mail', related_name='clicks')
    date = models.DateTimeField(default=now)

    class Meta:
        app_label = 'pennyblack'


class LinkInline(admin.TabularInline):
    model = Link
    max_num = 0
    can_delete = False
    fields = ('link_target', 'link_hash',)
    readonly_fields = ('link_hash',)

    def get_queryset(self, request):
        """
        Don't show links with identifier because they aren't changable.
        """
        queryset = super(LinkInline, self).get_queryset(request)
        return queryset.filter(identifier='')
