from django.conf.urls import patterns, url
from django.contrib.contenttypes import generic
from django.core import mail
from django.core.context_processors import csrf
from django.core.urlresolvers import reverse
from django.db import models
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.utils import translation
from django.utils.translation import ugettext_lazy as _

from pennyblack import settings

import datetime

try:
    from django.utils import timezone
except ImportError:
    now = datetime.datetime.now
else:
    now = timezone.now


#-----------------------------------------------------------------------------
# Job
#-----------------------------------------------------------------------------
class Job(models.Model):
    """A bunch of participants which receive a newsletter"""
    newsletter = models.ForeignKey('pennyblack.Newsletter', related_name="jobs", null=True)
    status = models.IntegerField(choices=settings.JOB_STATUS, default=1)
    date_created = models.DateTimeField(verbose_name=_("created"), default=now)
    date_deliver_start = models.DateTimeField(blank=True, null=True, verbose_name=_("started delivering"), default=None)
    date_deliver_finished = models.DateTimeField(blank=True, null=True, verbose_name=_("finished delivering"), default=None)

    content_type = models.ForeignKey('contenttypes.ContentType', null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    group_object = generic.GenericForeignKey('content_type', 'object_id')
    collection = models.TextField(blank=True)

    #ga tracking
    utm_campaign = models.SlugField(verbose_name=_("utm campaign"), blank=True)

    public_slug = models.SlugField(verbose_name=_("slug"), unique=True, 
            help_text=_("Unique slug to allow public access to the newsletter"),
            blank=True, null=True)

    class Meta:
        ordering = ('-date_created',)
        verbose_name = _("newsletter delivery task")
        verbose_name_plural = _("newsletter delivery tasks")
        app_label = 'pennyblack'

    def __unicode__(self):
        return (self.newsletter.subject if self.newsletter is not None else "unasigned delivery task")

    def delete(self, *args, **kwargs):
        """
        If the job refers to a inactive Newsletter delete it.
        """
        if not self.newsletter.active:
            self.newsletter.delete()
        super(Job, self).delete(*args, **kwargs)

    @property
    def public_url(self):
        return self.newsletter.get_base_url() + reverse('pennyblack.views.view_public', args=(self.public_slug,))


    @property
    def count_mails_total(self):
        return self.mails.count()

    @property
    def count_mails_sent(self):
        return self.mails.filter(sent=True).count()

    @property
    def percentage_mails_sent(self):
        if self.count_mails_total == 0:
            return 0
        return round(float(self.count_mails_sent) / float(self.count_mails_total) * 100, 1)

    @property
    def count_mails_viewed(self):
        return self.mails.exclude(viewed=None).count()

    @property
    def count_mails_delivered(self):
        return self.count_mails_sent - self.count_mails_bounced

    @property
    def percentage_mails_viewed(self):
        if self.count_mails_delivered == 0:
            return 0
        return round(float(self.count_mails_viewed) / self.count_mails_delivered * 100, 1)

    @property
    def count_mails_bounced(self):
        return self.mails.filter(bounced=True).count()

    @property
    def count_mails_clicked(self):
        return self.mails.filter(clicks__isnull=False).count()

    @property
    def percentage_mails_clicked(self):
        if self.count_mails_delivered == 0:
            return 0
        return round(float(self.count_mails_clicked) / float(self.count_mails_delivered) * 100, 1)

    @property
    def percentage_mails_bounced(self):
        if self.count_mails_sent == 0:
            return 0
        return round(float(self.count_mails_bounced) / float(self.count_mails_sent) * 100, 1)

    # fields
    def field_mails_sent(self):
        return self.count_mails_sent
    field_mails_sent.short_description = _('# of mails sent')

    def field_opening_rate(self):
        return '%s%%' % self.percentage_mails_viewed
    field_opening_rate.short_description = _('opening rate')

    def field_mails_total(self):
        return self.count_mails_total
    field_mails_total.short_description = _('# of mails')

    def can_send(self):
        """
        Is used to determine if a send button should be displayed.
        """
        if not self.status in settings.JOB_STATUS_CAN_SEND:
            return False
        return self.is_valid()

    def can_view_public(self):
        """
        Used to determine if a job's newsletter can be viewed publically
        """
        if not self.status in settings.JOB_STATUS_CAN_VIEW_PUBLIC:
            return False
        return self.is_valid()

    def is_valid(self):
        if self.newsletter is None or not self.newsletter.is_valid():
            return False
        return True

    def create_mails(self, queryset):
        """
        Create mails for every NewsletterReceiverMixin in queryset.
        """
        if hasattr(queryset, 'iterator') and callable(queryset.iterator):
            for receiver in queryset.iterator():
                self.create_mail(receiver)
        else:
            for receiver in queryset:
                self.create_mail(receiver)

    def create_mail(self, receiver):
        """
        Creates a single mail. This is also used in workflow mail send process.
        receiver has to implement all the methods from NewsletterReceiverMixin
        """
        return self.mails.create(person=receiver)

    def add_link(self, link, identifier=''):
        """
        Adds a link and returns a replacement link
        """
        if identifier != '':
            try:
                return self.links.get(identifier=identifier)
            except self.links.model.DoesNotExist:
                return self.links.create(link_target='', identifier=identifier)
        # clean link from htmlentities
        for old, new in (('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"')):
            link = link.replace(old, new)
        link = self.links.create(link_target=link)
        link.save()
        return '{{base_url}}' + reverse('pennyblack.redirect_link', kwargs={'mail_hash': '{{mail.mail_hash}}', 'link_hash': link.link_hash}).replace('%7B', '{').replace('%7D', '}')

    def start_sending(self):
        self.status = 11
        self.save()
        try:
            from pennyblack.tasks import SendJobTask
        except ImportError:
            pass
        else:
            SendJobTask.delay(self.id)

    def send(self):
        """
        Sends every pending e-mail in the job.
        """
        self.newsletter = self.newsletter.create_snapshot()
        self.newsletter.replace_links(self)
        self.newsletter.prepare_to_send()
        self.status = 21
        self.date_deliver_start = now()
        self.save()
        try:
            translation.activate(self.newsletter.language)
            connection = mail.get_connection()
            connection.open()
            for newsletter_mail in self.mails.filter(sent=False).iterator():
                connection.send_messages([newsletter_mail.get_message()])
                newsletter_mail.mark_sent()
            connection.close()
        except:
            self.status = 41
            raise
        else:
            self.status = 31
            self.date_deliver_finished = now()
        self.save()


class JobStatistic(Job):
    class Meta:
        proxy = True
        verbose_name = _("statistic")
        verbose_name_plural = _("statistics")
        app_label = 'pennyblack'



